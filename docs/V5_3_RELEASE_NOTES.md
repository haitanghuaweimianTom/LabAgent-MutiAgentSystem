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
