# LabAgent v8.2

> 全自动多智能体学术论文生产平台，支持 CCF-A 顶会、数学建模竞赛、课程作业、金融分析报告。

[English](README.md)

---

## 目录

- [概述](#概述)
- [快速开始](#快速开始)
- [功能特性](#功能特性)
- [系统架构](#系统架构)
- [防死亡螺旋机制](#防死亡螺旋机制)
- [API 参考](#api-参考)
- [配置说明](#配置说明)
- [开发指南](#开发指南)
- [故障排查](#故障排查)
- [版本历史](#版本历史)

---

## 概述

LabAgent 自动化整个学术论文生产流程：

1. **问题分析** — 将复杂问题分解为子问题
2. **文献检索** — 从 arXiv + Semantic Scholar 搜索真实论文
3. **数学建模** — 选择合适的模型和算法
4. **代码生成与执行** — 生成 Python 代码，沙箱执行，自动修复错误
5. **实验执行** — GPU 支持、Baseline 对比、消融实验
6. **论文写作** — LaTeX 论文逐章生成，术语一致
7. **同行评议** — 4 维评分 + 可复现性检查
8. **事实核查** — 数值与执行结果交叉验证
9. **合规审查** — 金融报告投顾话术过滤
10. **交付物打包** — LaTeX + 图表 + 代码打包为可提交 ZIP

### v8.2 新特性

| 特性 | 说明 |
|------|------|
| **组件化注入** | 受限模式下 Coder 只生成 nn.Module/Loss 组件，自动注入 Base Template |
| **AST 安全壳** | 自动包裹 try-except + cuda.empty_cache() + gc.collect()，防止沙箱崩溃 |
| **渐进式越狱熔断** | 动态调整执行模式：restricted → jailbreak，熔断阈值自适应 |
| **SHA-256 数据溯源** | 全链路数据哈希追踪，确保结果不可篡改 |
| **AST 防造假** | 检测硬编码指标（`accuracy = 0.95`），拦截伪造输出 |
| **代码质量修复** | 修复 debug 端点、统一版本号、添加 CI/CD、速率限制 |
| **Bug Finder Agent** | Qwen2.5-Coder-1.5B QLoRA 微调，本地推理代码错误诊断（11类，准确率100%） |
| **ML 训练模块** | 完整的模型训练流水线：数据收集 → 增强 → QLoRA 训练 → 评估 |

---

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 20+（Web UI）
- LLM API Key（OpenAI、Anthropic、Kimi、DeepSeek 或任何兼容 Provider）

### 1. 安装依赖

```bash
# 后端
cd backend
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

### 2. 配置 LLM Provider

创建 `backend/.env`：

```bash
# 方案 A：OpenAI
OPENAI_API_KEY=sk-...

# 方案 B：Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# 方案 C：Kimi（Anthropic 兼容）
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
ANTHROPIC_AUTH_TOKEN=sk-kimi-...

# 方案 D：通过 Web UI 设置页添加任意 Provider
```

### 3. 启动系统

```bash
# 终端 1：后端
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# 终端 2：前端
cd frontend
npm run dev
```

### 4. 打开 Web UI

访问 **http://localhost:3000**：

1. 进入 **设置** 页 → 添加 LLM Provider → 设为默认
2. 进入 **任务执行** 页 → 选择模板 → 输入问题描述 → 提交
3. 实时查看任务进度
4. 完成后进入 **PDF** 页 → 生成 Camera-Ready → 下载 ZIP

---

## 功能特性

### 论文模板（8 个内置 + 可扩展）

| 模板 | 用途 | 级别 |
|------|------|------|
| `math_modeling` | 数学建模竞赛（CUMCM） | — |
| `neurips_2024` | NeurIPS 2024 | **CCF-A** |
| `acm_sigconf` | ACM SIG Conference | **CCF-A** |
| `ieee_conference` | IEEE Conference | **CCF-A** |
| `springer_lncs` | Springer LNCS | CCF-B |
| `research_survey` | 文献综述/调研报告 | — |
| `coursework` | 课程作业 | — |
| `financial_analysis` | 金融分析报告 | — |

新增模板：将 JSON + `.cls/.sty` 文件放入 `backend/app/core/paper_templates/templates/`。

### Agent 团队（15 个 Agent）

| Agent | 角色 | 核心能力 |
|-------|------|---------|
| analyzer | 分析师 | 问题分解、类型识别 |
| data | 数据分析师 | 文件解析、特征提取 |
| research | 研究员 | arXiv + Semantic Scholar 搜索 |
| innovation | 创新发现专家 | 研究空白识别 |
| modeler | 建模师 | 数学建模 |
| algorithm_engineer | 算法工程师 | CCF-A 算法设计 |
| financial_analyst | 金融分析师 | 金融建模、风险分析 |
| solver | 求解器 | 真实代码执行、自动修复 |
| writer | 写作专家 | 逐章 LaTeX 生成 |
| peer_review | 审稿人 | 4 维评分 + 可复现性检查 |
| experimentation | 实验设计专家 | 实验设计 + 自动迭代 |
| summary | 总结专家 | 任务总结 + 经验提取 |
| debugger | 调试专家 | 智能错误分析 |
| compliance | 合规审查 | 金融报告合规检查 |
| coordinator | 协调者 | 工作流编排 |

### 零幻觉架构

```
代码生成 → AST 审计 → 安全壳 → 沙箱执行 → 结果验证 → 事实核查
   ↓          ↓          ↓          ↓            ↓           ↓
LLM 写代码  检测伪造   try-except  真实 Python   范围检查    LaTeX 数字
            硬编码指标  + cuda 保护   执行         + 加总      vs 实际
```

### 防死亡螺旋架构（v8.2）

所有经过 `iterative_solver` 的模板都接入 AST 安全壳 + 沙箱错误统计保护。

| 模板 | 流程 | 组件化注入 | 越狱熔断 |
|------|------|-----------|---------|
| math_modeling | iterative_solver → ast_audit → sandbox → figure | — | — |
| coursework | iterative_solver → ast_audit → sandbox → figure | — | — |
| financial_analysis | iterative_solver → ast_audit → sandbox → figure | — | — |
| neurips_2024 | iterative_solver → coder → ast_audit → sandbox → reviewer → figure | Yes | Yes |
| ieee_conference | iterative_solver → coder → ast_audit → sandbox → reviewer → figure | Yes | Yes |
| acm_sigconf | iterative_solver → coder → ast_audit → sandbox → reviewer → figure | Yes | Yes |
| springer_lncs | iterative_solver → coder → ast_audit → sandbox → reviewer → figure | Yes | Yes |
| research_survey | 直接进入 writer（无代码执行） | — | — |

### 知识库系统

- **混合检索**：语义（sentence-transformers）+ BM25 关键词检索
- **作用域隔离**：全局（跨项目共享）+ 项目级
- **来源追踪**：每条检索结果标记来源文档
- **自动分类**：按类型/领域/方法/质量自动分类

### GPU 支持（可选）

- **GPUExecutor**：统一 GPU 训练/推理生命周期
- **VRAMMonitor**：实时 GPU 显存监控（85% 预警，95% OOM 保护）
- **CheckpointManager**：自动保存/恢复训练检查点
- 无 GPU 时自动降级为 CPU

### ML 训练模块（v8.2 新增）

**Bug Finder Agent** — 本地推理代码错误诊断，零 API 成本

| 能力 | 说明 |
|------|------|
| 错误分类 | 11 种错误类型：IndexError, KeyError, ValueError, ZeroDivisionError, TypeError, AttributeError, FileNotFoundError, ImportError, RuntimeError, LogicError, OOM |
| 错误定位 | 行级定位，准确率 100% |
| 修复建议 | 结构化 JSON 输出，包含 root_cause 和 fix_suggestion |
| 推理延迟 | ~560ms（RTX 4060），可通过 INT4 量化优化 |

**训练流水线**：

```bash
# 数据收集与增强
python ml/collect_data.py --problems 20

# QLoRA 训练 (RTX 4060 8GB)
python ml/train_bug_finder.py --config ml/configs/bug_finder_qlora.yaml

# 评估
python ml/evaluation/eval_bug_finder.py \
    --model ml/checkpoints/bug_finder \
    --data ml/collected_data/bug_finder_eval_v2.json
```

**与其他模块协同**：

```
Solver(大模型) → 生成代码 → Sandbox 执行 → 失败
    │
    ▼
Bug Finder Agent (本地推理，零API成本)
    ├── 错误分类 (OOM/Syntax/Logic/...)
    ├── 定位错误代码行
    └── 生成修复建议
    │
    ▼
Solver(大模型) 根据结构化诊断 → 精准修复
```

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Web UI (Next.js 14 + Zustand)                                  │
│  10 个标签页：任务执行 / 数据 / PDF / 历史 / 设置                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────────────────────┐
│  FastAPI Backend (app.main)                                      │
│  ├─ LangGraph 编排器 (StateGraph)                                │
│  │   需求分解 → 预检 → 问题分析                                   │
│  │   → 并行分析 [数据+文献+创新]                                  │
│  │   → 讨论 → 建模 → 实验 → 求解                                 │
│  │   → [v8.2] 代码生成 → AST 审计 → 沙箱 → 反思                  │
│  │   → 写作 → 同行评议 → 事实核查 → 合规审查                      │
│  │   → 总结 → END                                                │
│  ├─ Agent 层（15 个 Agent）                                      │
│  ├─ 核心模块                                                     │
│  │   ├─ code_audit.py        (AST 分析 + 防造假)                  │
│  │   ├─ safety_shell.py      (AST 安全壳变换器)                   │
│  │   ├─ reference_verifier.py (DOI/arXiv 验真)                   │
│  │   ├─ symbolic_auditor.py  (统计验证)                           │
│  │   ├─ data_provenance.py   (SHA-256 追踪)                      │
│  │   ├─ sandbox.py           (代码执行)                           │
│  │   ├─ gpu_executor.py      (GPU 训练)                          │
│  │   └─ memory.py            (三级记忆)                           │
│  └─ 服务层                                                       │
│      ├─ fact_checker.py      (数值验证)                           │
│      ├─ camera_ready.py      (ZIP 打包)                           │
│      ├─ preflight.py         (问题分析)                           │
│      └─ reference_verifier.py                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 数据流

1. 用户提交问题 → 预检分析问题类型
2. 分析师分解为子问题
3. 并行：数据分析 + 文献检索 + 创新发现
4. Agent 讨论方案（投票系统）
5. 建模师建立数学模型
6. **[v8.2]** 代码生成 → AST 审计 → 沙箱执行 → 反思
7. 写作专家逐章生成 LaTeX
8. 审稿人评分并建议修改（自动迭代最多 3 轮）
9. 事实核查对比数值
10. 合规审查过滤投顾话术
11. 交付物打包为可提交 ZIP

---

## 防死亡螺旋机制

### 机制 1：组件化注入

**问题**：Coder 生成的完整训练脚本容易包含多种错误，导致沙箱反复失败。

**方案**：受限模式下，Coder 只能生成 nn.Module 和 Loss 组件，系统自动注入到预置的 Base Template 中。

```python
# 受限模式：Coder 只输出组件
# COMPONENT: nn.Module
class MyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(784, 10)

# COMPONENT: loss
def my_loss(pred, target):
    return F.cross_entropy(pred, target)
```

### 机制 2：AST 安全壳

**问题**：沙箱中的未捕获异常（特别是 CUDA OOM）导致整个流程崩溃。

**方案**：SafetyShellTransformer 对代码进行 AST 变换，自动注入防护层。

```python
# 原始代码
model = MyModel().cuda()
output = model(data)

# 安全壳注入后
try:
    model = MyModel().cuda()
    output = model(data)
    torch.cuda.empty_cache()  # 自动注入
except Exception as _safety_exc:
    traceback.print_exc()
finally:
    gc.collect()  # 自动注入
```

### 机制 3：渐进式越狱熔断

**问题**：受限模式可能陷入"模板瓶颈"——代码能运行但指标无法提升。

**方案**：Reviewer Agent 监控指标趋势，动态调整执行模式。

| 状态 | 条件 | 动作 |
|------|------|------|
| 正常运行 | error_count < 3 | 保持当前模式 |
| 死亡螺旋 | error_count >= 3 | 降级为 restricted，熔断阈值=3 |
| 模板瓶颈 | 指标连续 2 次未提升 | 升级为 jailbreak，熔断阈值=1 |
| 最大重试 | restricted 模式下仍连续失败 | 进入论文生成（带降级标记） |

---

## API 参考

基础 URL：`http://localhost:8001/api/v1`

### 任务管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/tasks/submit` | POST | 提交新任务 |
| `/tasks/` | GET | 列出所有任务 |
| `/tasks/{id}/status` | GET | 获取任务状态 |
| `/tasks/{id}/stream` | GET | SSE 事件流 |
| `/tasks/{id}/result` | GET | 任务结果 |
| `/tasks/{id}/camera-ready` | POST | 生成 Camera-Ready ZIP |
| `/tasks/{id}/pause` | POST | 暂停任务 |
| `/tasks/{id}/resume` | POST | 恢复任务 |
| `/tasks/{id}/cancel` | POST | 取消任务 |
| `/tasks/{id}/rerun` | POST | 重新运行任务 |

### 提交任务示例

```bash
curl -X POST http://localhost:8001/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "problem_text": "基于 2024 年数据预测 2030 年 GDP...",
    "project_name": "my_project",
    "options": {"template": "math_modeling"}
  }'
```

---

## 配置说明

### 环境变量

```bash
# LLM Provider（选一个）
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# 可选
LABAGENT_API_KEY=your-secret-key    # 启用 API 认证
CUDA_VISIBLE_DEVICES=0               # GPU 选择
NEXT_PUBLIC_API_URL=http://localhost:8001  # 后端 URL
```

### 运行时配置（`backend/app/config.py`）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `auto_mode_enabled` | True | 全自动模式 |
| `max_concurrent_tasks` | 3 | 最大并发任务数 |
| `task_timeout_seconds` | 7200 | 任务超时（2 小时） |
| `experiment_max_iterations` | 3 | 实验迭代上限 |

### Docker 部署

```bash
docker compose up -d    # 启动后端 + Redis
```

---

## 开发指南

### 项目结构

```
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── agents/          # Agent 实现
│   │   │   ├── base.py      # BaseAgent 基类
│   │   │   ├── claude_code.py # Claude Code CLI 集成
│   │   │   └── mcp_tools.py # MCP 工具定义
│   │   ├── core/            # 核心模块
│   │   ├── routers/         # API 路由
│   │   └── services/        # 业务逻辑
│   └── tests/               # 后端测试
├── frontend/                # Next.js 前端
├── ml/                      # ML 训练模块
│   ├── train_bug_finder.py  # Bug Finder 训练脚本
│   ├── configs/             # 训练配置 (QLoRA/DPO)
│   ├── collected_data/      # 训练数据 (v1-v7 迭代)
│   ├── checkpoints/         # 模型检查点
│   ├── evaluation/          # 评估脚本
│   └── models/              # 基础模型 (Qwen2.5-Coder-1.5B)
├── config/                  # 配置文件
├── scripts/                 # 工具脚本
├── .github/workflows/       # CI/CD 流水线
├── CONTRIBUTING.md          # 贡献指南
├── CHANGELOG.md             # 版本历史
└── requirements-dev.txt     # 开发依赖
```

### 运行测试

```bash
# 后端
cd backend
python -m pytest tests/ -v

# 前端
cd frontend
npm test
```

### 代码质量

```bash
# Linting
ruff check backend/
ruff format backend/

# Pre-commit hooks
pre-commit install
pre-commit run --all-files
```

---

## 故障排查

### 任务卡在求解器

- 求解器生成代码 → 沙箱执行 → 自动修复错误（最多 3 次重试）
- **v8.2**：死亡螺旋时自动降级为 restricted 模式
- 查看 `backend/app.log` 获取错误详情

### GPU OOM

- **v8.2**：安全壳在 CUDA 调用后自动注入 `torch.cuda.empty_cache()`
- 系统自动估算 batch size，但 LLM 生成的代码可能忽略
- 查看 VRAMMonitor 日志获取显存使用情况

### 任务中断

- 任务自动保存检查点到 `backend/data/tasks/`
- 通过 `POST /tasks/{id}/resume` 恢复

---

## 版本历史

### v8.2（2026-07）— 防死亡螺旋架构 + ML 训练模块
- 组件化注入：受限模式 Coder 只生成 nn.Module/Loss 组件
- AST 安全壳：自动注入 try-except + cuda.empty_cache() + gc.collect()
- 渐进式越狱熔断：基于指标趋势的动态模式切换
- AST 双重职责审计：防造假 + 防崩溃一次完成
- **Bug Finder Agent**：Qwen2.5-Coder-1.5B QLoRA 微调，11类错误诊断准确率100%
- **ML 训练流水线**：数据收集 → 增强 → QLoRA 训练 → 评估完整流程
- 项目更名为 **LabAgent**
- 代码质量：修复 debug 端点、统一版本号、添加 CI/CD、速率限制
- 重构 BaseAgent：提取 claude_code.py 和 mcp_tools.py 模块

### v8.0（2026-07）— 零幻觉架构
- AST 代码审计检测硬编码指标
- 参考文献验真（CrossRef/arXiv API）
- 符号审计统计验证
- Debugger Agent 智能错误分析
- SHA-256 数据溯源
- 合规审查过滤投顾话术

### v7.4（2026-07）— 安全加固
- 输入验证、路径穿越防护、Prompt 注入防御

### v7.0（2026-07）— 全自动 AI 科学家
- 需求分解、创新发现、多 Agent 讨论

### v6.0（2026-06）— 5 大研究能力
- NAS、自动损失函数设计、跨论文差距识别、代码演化、AutoML

---

## 许可证

仅供学术研究和教育使用。请遵守目标会议/期刊的投稿规范。
