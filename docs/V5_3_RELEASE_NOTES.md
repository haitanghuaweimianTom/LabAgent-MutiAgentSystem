# v5.3 新增模块（独立、可选用）

本文档记录最近新增的三个独立模块。这些模块设计为**无副作用、可单独启用**，
不依赖其他未提交的改动，可以独立 git pull 使用。

---

## 1. ContextCompressor — 主动上下文压缩（模仿 Claude Code /compact）

**位置**：`backend/app/core/context_compressor.py`

**问题**：长程 CCF-A 任务（50+ 篇论文、20+ 子问题、5+ baseline）会让累积
context 暴涨（80K-200K tokens），触发 LLM API "prompt too long" 错误或质量下降。

**设计**：
- **三级压缩**：
  - **L0 软压缩**：丢弃 droappable 字段（`_contract` / `raw_response` / `trace` /
    `raw_log` / `raw_data`），截断超长字符串（>6000 字符）
  - **L1 LLM 摘要**：对超大 Agent 输出用 LLM 摘要（80 tokens 内）
  - **L2 硬截断**：再不行就字段值截断到 800 字符
- **保护关键字段永不丢**：`latex_code` / `title` / `abstract` /
  `sub_problem_models` / `citations` / `key_findings` / `numerical_results`
- **触发条件**：累计 > 30K tokens（可配置）
- **降级策略**：LLM 摘要失败自动降级 L2；保护字段永远不受影响
- **可观测**：`CompressionStats` 报告原/压后 token、节省数、压缩级别、影响 Agent

**使用方式**：
```python
from app.core.context_compressor import get_compressor

compressor = get_compressor()
stats = compressor.maybe_compress(
    task_id="task_xxx",
    results={"research_agent": {...}, "modeler_agent": {...}, ...},
    llm_caller=agent.call_llm,  # 可选；缺省时只用 L0 + L2
)
print(f"saved {stats.saved_tokens} tokens, level={stats.level_used}")
```

**测试**：`backend/tests/test_context_compressor.py`（15 个全过）
- estimate_tokens 准确性
- soft_compress 丢弃/截断规则
- 三级压缩触发条件与降级
- protected 字段保护
- 长程 CCF-A 模拟（80 篇论文 + 20 子问题 + 50 baseline）

---

## 2. ConsistencyChecker — 跨章节一致性验证

**位置**：`backend/app/services/consistency_checker.py`

**问题**：多章节论文容易出现术语不一致、模型名混乱、结论与摘要数字矛盾、
孤立 bib 条目等"不一致"问题，肉眼检查困难。

**设计**：纯规则检查（不调 LLM），6 类问题：

| 类型 | 严重度 | 示例 |
|------|--------|------|
| **terminology** | medium | "神经网络" vs "深度学习模型" 混用 |
| **model_name** | low | paper_memory 登记但 LaTeX 没提及 |
| **conclusion** | medium | 摘要说"42.0"，结论没呼应 |
| **citation** | low | bib 中的 key 从未 `\cite{}` |
| **symbol** | - | 预留接口 |
| **number** | low | solver 数值未在 LaTeX 出现 |

**使用方式**：
```python
from app.services.consistency_checker import get_consistency_checker

checker = get_consistency_checker()
report = checker.check(
    task_id="task_xxx",
    latex_code=paper.latex_code,
    chapter_summaries=paper.chapters,
    paper_memory=paper.paper_memory,
    bib_entries=paper.citations,
    solver_numerical_results=solver_output,
)
# report.issue_count / report.issues / report.stats / report.passed
```

**测试**：`backend/tests/test_consistency_checker.py`（12 个全过）

---

## 3. CircuitBreaker — LLM 调用熔断器（防 key 刷爆）

**位置**：`backend/app/core/circuit_breaker.py`

**问题**：当 LLM API key 失效/欠费/限流时，系统可能无限重试 + 调用
`_mock_response` 兜底（生成假数据），用户既浪费钱又得到假结果。

**设计**：状态机熔断器（CLOSED → OPEN → HALF_OPEN）

| 状态 | 行为 |
|------|------|
| **CLOSED** | 正常：每次调用记账 |
| **OPEN** | 拒绝所有请求（抛 `CircuitOpenError`） |
| **HALF_OPEN** | 冷却时间到后允许 1 次试探 |

**默认配置**：
- `failure_threshold=10`：连续 10 次失败触发熔断
- `window_seconds=1800`（30 分钟）：只统计窗口内失败
- `open_duration_seconds=300`（5 分钟）：冷却时间
- 任务级隔离：每个 task_id 独立熔断器

**使用方式**（需要配合 BaseAgent 修改）：
```python
from app.core.circuit_breaker import get_breaker, CircuitOpenError

breaker = get_breaker("task_xxx")
try:
    breaker.check_or_raise()  # OPEN 时抛 CircuitOpenError
    result = await call_llm()
    breaker.record_success()
except Exception:
    breaker.record_failure()
    raise
```

**回调机制**：触发熔断时调用 `on_open_callback(breaker)`，
让上层（Orchestrator）标记 task failed 并通知用户。

### v5.3.1：CircuitBreaker 已接入 BaseAgent.call_llm

**位置**：`backend/app/agents/base.py`

修复了**两个关键 bug**：

**Bug 1：失败被吞 + 返回假数据**

之前 `_call_llm_once` 在 LLM 失败时返回 `self._mock_response(messages)` —
**生成看起来合理的假 JSON**，让论文"能跑"出来但内容全是幻觉。
这正是你之前问"key 被不停调用"的核心原因——失败被静默吞掉，调用栈不停循环。

```python
# 旧代码（9 处）：
except httpx.HTTPStatusError as e:
    ...
    return self._mock_response(messages)  # ← 失败被吞！
```

```python
# 新代码（v5.3）：
except httpx.HTTPStatusError as e:
    ...
    raise RuntimeError(f"HTTP {e.response.status_code}: {err_text}")  # ← 真抛
```

**Bug 2：没 API key 时 fallback mock_response**

旧代码：
```python
if not self.api_key:
    return self._mock_response(messages)  # ← 无 key 也假装能跑
```

新代码：直接抛错，熔断器会正确计数。

### 完整接入点

`BaseAgent.call_llm` 末尾：
```python
# ===== v5.3: CircuitBreaker 包装 =====
task_id = (context or {}).get("task_id") if context else None
breaker = get_breaker(task_id) if task_id else None
if breaker:
    breaker.check_or_raise()  # OPEN 时直接抛 CircuitOpenError

try:
    result = await self._call_llm_once(messages, temperature)
except Exception:
    if breaker:
        breaker.record_failure()
    raise
else:
    if breaker:
        breaker.record_success()
    return result
```

### 触发流程

1. **第 1 次失败** → `_call_llm_once` 抛 RuntimeError
2. **熔断器 record_failure** → 计数 +1
3. **第 10 次连续失败** → 熔断器 OPEN
4. **第 11 次调用** → `breaker.check_or_raise()` 抛 `CircuitOpenError`
5. **BaseAgent.call_llm** 直接抛 `CircuitOpenError`
6. **Orchestrator**（如果你也接入）捕获后标记 task failed

### 用户立即能看到的效果

- API key 失效时，**第 11 次**开始任务直接停止
- 聊天室里广播：`⛔ API key 异常，已暂停任务：...`
- 不再产生假数据、不再刷爆 key

---

## 关键修复总结（v5.3 全套）

| 问题 | 之前 | 现在 |
|------|------|------|
| LLM 失败 | 返回 mock_response（假数据） | 抛 RuntimeError → 熔断器计数 |
| API key 失效 | 用 mock_response 假装能跑 | 立即报错，停止任务 |
| key 被无限刷 | 失败被吞，无限重试 | 第 10 次失败后熔断 |

---

## 修复后的项目状态

跑完整测试套件：

```
271 passed in 63s
```

（包含原有 228 个回归 + 43 个 v5.3 新模块测试）

---

## 如何进一步利用 CircuitBreaker

如果你想**让任务失败时优雅通知前端**，可以在 Orchestrator 加：

```python
except CircuitOpenError as e:
    task_step.status = TaskStatus.FAILED
    task_step.error = f"⛔ API key 异常：{e}"
    room.post("coordinator", task_step.error, "broadcast")
```

这个我没集成（避免再被 linter 还原），但你随时可以在 orchestrator 里加上。

---

## v5.3.2：CircuitOpenError 已接入 Orchestrator（v5.3.2）

**位置**：`backend/app/agents/orchestrator.py`

实现了上面的"如何进一步利用 CircuitBreaker"——但做得更完整：

### 触发流程

1. LLM 第 11 次调用失败 → BaseAgent 抛 `CircuitOpenError`
2. Orchestrator 的 `except Exception as e:` 接住
3. 检测 `isinstance(e, CircuitOpenError)` → 走熔断分支
4. **task_step.status = FAILED**（修复了原代码无条件 COMPLETED 的 bug）
5. **聊天室广播友好消息**：
   ```
   ⛔ 任务已暂停：API key 调用连续失败触发熔断
   原因：[CircuitBreaker:task_xxx] OPEN: 10 consecutive failures (retry in 300s)
   建议：检查 API key 是否有效/欠费/限流，修复后点击「重新执行」
   ```
6. **持久化 metadata**：`status="failed"` + `error="⛔..."` + `current_step="已暂停（API key 异常）"`
7. 前端轮询 `GET /tasks/{id}/status` 立即看到 failed 状态
8. 用户看到聊天室的友好提示，按指引修复 key → 点击「重新执行」

### 关键 bug 修复

**Bug**：之前 `if self.task_history[task_id]: self.task_history[task_id][-1].status = TaskStatus.COMPLETED`
**永远把最后一步设为 COMPLETED**，即使 writer 抛 CircuitOpenError 也覆盖为 COMPLETED！
**修复**：用 `writer_failed` 标志：
```python
self.task_history[task_id][-1].status = (
    TaskStatus.FAILED if writer_failed else TaskStatus.COMPLETED
)
```

### 测试覆盖（3 个新集成测试）

`backend/tests/test_circuit_breaker_integration.py`：

1. ⭐ `test_orchestrator_circuit_open_marks_task_failed_and_broadcasts`
   - 注入 CircuitOpenError → 验证：
     - 聊天室广播包含 ⛔ + 熔断 + API key + 重新执行
     - task_step.status = FAILED
     - task_step.error 含 ⛔ 友好消息
     - metadata.status = failed
     - metadata.current_step = "已暂停（API key 异常）"
2. `test_normal_exception_does_not_trigger_circuit_handling`
   - 普通 RuntimeError 不应触发熔断器友好消息
3. `test_real_circuit_breaker_triggers_via_consecutive_failures`
   - 真实 10 次连续失败 → 第 11 次抛 CircuitOpenError

---

## v5.3.2 完整状态

测试结果：
```
274 passed in 127s
```

包含：
- 原有 228 个回归
- v5.3 新模块（ContextCompressor / ConsistencyChecker / CircuitBreaker）共 43 个
- v5.3.2 新集成（Orchestrator 集成）3 个

---

## 用户完整使用流程

1. **任务跑到一半，API key 失效**：
   - 第 11 次 LLM 调用 → CircuitOpenError
   - Orchestrator 标记 task failed + 聊天室广播 ⛔
   - 前端 SSE 推送 status="failed"，current_step="已暂停（API key 异常）"

2. **用户在聊天室看到提示**：
   ```
   ⛔ 任务已暂停：API key 调用连续失败触发熔断
   原因：[CircuitBreaker:task_xxx] OPEN: 10 consecutive failures
   建议：检查 API key 是否有效/欠费/限流，修复后点击「重新执行」
   ```

3. **用户修复 key，点击「重新执行」**：
   - 任务重启，新 task_id
   - CircuitBreaker 是按 task_id 隔离的，新任务独立计数
   - 不再无限刷老 key

**测试**：`backend/tests/test_circuit_breaker.py`（16 个全过）
- CLOSED → OPEN 转换
- 成功重置窗口
- OPEN → HALF_OPEN 冷却
- HALF_OPEN 试探成功/失败
- 滑动窗口
- 任务级隔离
- 手动 reset
- 异步并发
- 真实 key 失效场景模拟

---

## 测试覆盖

```
271 passed in 84s
```

| 模块 | 测试文件 | 通过数 |
|------|---------|-------|
| ContextCompressor | test_context_compressor.py | 15 |
| ConsistencyChecker | test_consistency_checker.py | 12 |
| CircuitBreaker | test_circuit_breaker.py | 16 |
| 其他回归（camera_ready / peer_review / langgraph / phase2 等） | — | 228 |
| **合计** | — | **271** |

---

## 启用建议

| 模块 | 何时启用 |
|------|---------|
| ContextCompressor | 跑长程 CCF-A / deep_research 任务时 |
| ConsistencyChecker | 跑论文/调研报告任务时（用户对质量敏感） |
| CircuitBreaker | **强烈建议所有任务启用**（保护 API key） |

每个模块都是**独立的**，不需要同时启用。
