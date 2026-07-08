# 多智能体协作论文生产系统 v8.0

> **面向 CCF-A 顶会 / 数学建模竞赛的全自动 AI 科学家多智能体协作平台。**
> 内置 8 套论文模板（含 NeurIPS 2024、ACM SIGCONF、IEEE Conference、Springer LNCS、综述、CUMCM），
> LangGraph 编排 + ReAct 工具循环 + 实时协作讨论 + 自动迭代 + 真实代码执行 + 真实 GPU 实验 + 真实 arXiv 文献检索 + 跨方法交叉验证 + Camera-Ready 自动打包 + 断点续传 + 显存监控 + **5 大自主研究能力（NAS / 自动损失函数设计 / 跨论文研究空白识别 / 代码自动演化 / AutoML）** + **需求自动分解 + 多 Agent 讨论投票 + 创新点发现 + 知识库自动分类 + 任务总结与经验提取 + 全自动无人值守执行**。

**⚠️ 重要声明：本系统是研究辅助工具，不是"AI 科学家"。** 它自动化了论文写作中的重复性工作（格式排版、图表生成、文献整理、代码执行、实验运行），但论文的核心学术价值（研究想法、方法创新、实验设计）仍取决于输入的研究方向和 LLM 的能力。产出论文需要研究者审核关键结论和创新点。

---

## 📑 目录

- [系统能力](#-系统能力)
- [能力边界与诚实声明](#-能力边界与诚实声明)
- [论文产出样例](#-论文产出样例)
- [快速开始](#-快速开始)
- [Web UI 使用](#-web-ui-使用)
- [命令行使用](#-命令行使用)
- [API 说明](#-api-说明)
- [系统架构](#-系统架构)
- [算法与论文模板](#-算法与论文模板)
- [项目结构](#-项目结构)
- [配置说明](#-配置说明)
- [故障排除](#-故障排除)
- [版本历史](#-版本历史)

---

## 🚀 系统能力

### 论文产线
- **8 套论文模板**：`NeurIPS 2024` / `ACM SIGCONF` / `IEEE Conference` / `Springer LNCS` / `Research Survey` / `Financial Analysis` / `Coursework` / `CUMCM`，新模板只需在 `backend/app/core/paper_templates/templates/` 下放 JSON + `.cls/.sty` 即可热加载。
- **真实文献检索**：ResearchAgent 通过 arXiv MCP Server 拉真实论文，并经 Semantic Scholar 二次增强（引用、影响因子、PDF 链接）。
- **真实代码执行**：SolverAgent 调 LLM 写 Python → 沙箱执行 → 结果验证 → 自动 fix retry，最多 3 次，确保数值真实。
- **真实 GPU 实验执行**：ExperimentationAgent 自动搜索/下载数据集 → SolverAgent 生成实验代码 → GPUExecutor 执行训练（带显存监控）→ baseline 对比 + ablation 消融 → 检查点自动保存 → 结果聚合生成表格，WriterAgent 直接注入真实数字（禁止编造）。
- **断点续传**：任务中断（系统重启、进程崩溃）后，自动从 checkpoint 恢复，继续执行而非从头开始。
- **显存监控与 OOM 防护**：VRAMMonitor 实时监控 GPU 显存使用，超过 85% 预警，超过 95% 自动触发保护。
- **检查点保存与恢复**：训练过程中自动保存检查点，支持从最新检查点恢复训练。
- **跨方法交叉验证**：对每子任务结果用 CrossValidator 比对，差异 > 5% 自动报警。
- **同行评议 + 修订**：PeerReviewAgent 4 维评分（novelty/soundness/clarity/significance）+ 实验可复现性检查，自动打回重写。
- **全局论文记忆池**：WriterAgent v5.0 维护跨章节的术语表、符号表、关键结论，确保长论文全文一致性，避免术语冲突和结论矛盾。
- **Camera-Ready 一键打包**：调 `/tasks/{id}/camera-ready` 自动收集 main.tex / figures / code / bib / references_sources.txt，打包为可投稿 zip。
- **10 阶段任务状态机**：前端 `useTaskState` hook + 后端 SSE 实时推送，毫秒级进度刷新。

### Agent 团队
| Agent | 角色 | 关键能力 |
|------|------|---------|
| coordinator | 协调者 | 工作流编排、暂停/恢复、跨 Agent 黑板、与研究员讨论决策 NAS |
| requirement_decomposer | 需求分解器 | 万字以上长提示词自动拆解为结构化研究计划 |
| analyzer_agent | 分析师 | 子问题分解、问题类型识别、难度评估 |
| data_agent | 数据分析师 | 数据文件解析、洞察抽取 |
| research_agent | 研究员 | arXiv 检索 + Semantic Scholar 增强 + 可插拔 Reranker |
| innovation_agent | 创新发现专家 | 从文献中识别研究空白、提出创新方案 |
| modeler_agent | 建模师 | 数学建模、模型选择、算法推荐 |
| algorithm_engineer_agent | 算法工程师 | CCF-A / 数学建模双模式：设计创新算法、复杂度与理论保证、实验方案 |
| financial_analyst_agent | 金融分析师 | 金融数学建模、风险分析、回测设计 |
| solver_agent | 求解器 | 真实代码执行、CrossValidator 集成、双模式代码生成（Claude CLI + HTTP API） |
| writer_agent | 写作专家 | 按章节独立 LLM 调用、可用图表自动注入 |
| peer_review_agent | 同行评议 | 4 维评分 + 实验可复现性检查（train 脚本/随机种子/超参数/baseline 来源） |
| experimentation_agent | 实验设计 | 实验自动迭代优化（含 baseline/ablation 质量评估） |
| summary_agent | 总结专家 | 任务完成总结、经验提取与分类存储 |

### AgentModelRouter（按 (agent, template) 路由模型）
- 默认：analyzer / data / modeler / solver / peer_review = sonnet；research / experimentation = haiku；writer = opus。
- CCF-A 4 套模板（neurips_2024 / ieee_conference / acm_sigconf / springer_lncs）强制 writer = opus。
- 通过 `backend/app/core/agent_model_map.py` 注册表 + 前端 Settings 动态覆盖。

### 模板化建模路由
LangGraph 编排器根据 `paper_template` + `workflow_type` 自动选择最合适的建模专家：
- **数学建模 / 课程作业 / quick / code_focused** → `modeler_agent`
- **金融分析** → `financial_analyst_agent`
- **CCF-A 模板（IEEE / NeurIPS / ACM / Springer）或 `research_paper` workflow** → `algorithm_engineer_agent`
- **调研/综述（deep_research / research_survey）** → 跳过建模，直接进入写作

三种 Agent 的输出统一归一化为 `sub_problem_models` 标准格式，保证 `solver_agent` 与 `writer_agent` 无需感知具体建模专家；原始丰富输出保留在 `_raw_output` 中供写作时使用。

### 防编造与结果可审计
- **系统级禁令**：所有建模 Agent 的 system prompt 中明确禁止编造数据、股价、收益率、baseline 结果、引用、数据集等。
- **程序化校验**：`_validate_no_fabrication` 检测无来源的价格/收益率、无引用的具体性能数字、异常的作者-年份引用，生成 `_fabrication_flags` 与 `_fabrication_score`。
- **数值范围校验**：ResultValidator 检查准确率不可能 > 1.0、R² 不可能 > 1.0、精确率不可能为负数。
- **写作端警示**：`writer_agent` 在构建章节上下文时读取 `_fabrication_flags`，对可疑内容添加"需谨慎处理或删除"的提示。
- **兜底模板审计**：`modeler_agent` 的 `MODEL_TEMPLATES` 仅作为 LLM 输出无效时的最后占位；使用时自动标记 `_used_fallback_template=True`，并在局限性中声明"必须根据具体问题重新校验或替换"。

### 安全加固（v7.4）
- **输入验证**：`TaskCreateRequest` Pydantic 约束（problem_text 1-100000 字符 + 控制字符清理，project_name 仅允许字母数字下划线连字符）；文件上传 50MB 大小限制 + HTTP 413 响应；文件名清理（移除路径分隔符和特殊字符）。
- **路径穿越防护**：`validate_path_within()` 校验所有文件操作端点，`Path.resolve()` 解析符号链接，5 个端点全部防护（DELETE /data/files, DELETE /data/output, GET /data/analyze, DELETE /projects）。
- **Prompt 注入防御**：`wrap_user_content()` 用 XML 标签包裹用户输入 + HTML 实体转义，BaseAgent + 14 个 Agent 全部使用，防止用户通过输入操纵 Agent 行为。
- **共享安全模块**：`backend/app/core/security.py` 提供 `validate_path_within`、`sanitize_filename`、`wrap_user_content`、`sanitize_input`、`MAX_UPLOAD_SIZE` 五个安全工具函数。
- **81 个安全测试**：覆盖路径穿越、输入验证、Prompt 注入、端点防护检查。

### 持久化记忆
- `MemoryManager` 三级记忆架构：Working Memory（任务上下文）/ Episodic Memory（事件流）/ Lessons Memory（跨任务经验教训）
- 每个 Agent 独立记忆池，支持关键词检索 + Prompt 自动注入
- 跨任务经验提取：完成后自动 `extract_lessons_from_result`，下次任务用 `retrieve_relevant` 检索
- **LangGraph State 外部化**：`TaskResultStore` 将 Agent 大输出从 `TaskState` 中剥离，state 仅保留引用标记，避免节点间反复深拷贝；结果持久化在 `backend/data/langgraph_results/`。
- **断点续传**：`task_persistence.py` 保存增量 checkpoint，系统重启后 `_restore_from_checkpoint()` 自动恢复任务状态。

### GPU 实验执行（v5.4 新增）
- **GPUExecutor**：统一管理 PyTorch 训练/推理生命周期，CUDA 不可用时自动回退 CPU。
- **VRAMMonitor**：独立监控线程，2 秒间隔检查显存使用，85% 预警 / 95% 触发 OOM 保护。
- **CheckpointManager**：自动保存检查点索引，支持从最新检查点恢复，自动清理旧检查点（保留 3 个最新）。
- **显存估算**：训练前自动估算推荐 batch size，防止 OOM。
- **ExperimentRunner 集成**：优先使用 GPUExecutor 执行实验，GPU 不可用时回退到 CodeSandbox。

### Provider / MCP / 知识库（CC Switch 风格）
- 15+ 预设 Provider：OpenAI、Anthropic、阿里百炼、硅基流动、智谱、Kimi、DeepSeek、Ollama、OpenRouter 等
- 5 种 API 格式：OpenAI Chat/Responses、Anthropic、Gemini、Ollama
- MCP 工具管理：stdio / SSE / StreamableHttp 三种传输
- 知识库 RAG：TF-IDF 语义检索 + Agent 自动注入

### 多智能体实时协作讨论
- **Agent 讨论协议**：`discuss_approach` 节点让分析师、建模师、研究员在研究方案阶段互相讨论，形成讨论记录。
- **结构化投票系统**：Proposal → Discussion Round → Vote → Decision，支持 approve/reject/abstain。
- **用户实时参与**：前端 DiscussionPanel 支持用户发送消息、投票、做最终决策。
- **自动迭代**：用户不发言时，系统自动迭代修订论文（peer review → writer 修订 → 再审），最多 3 轮，直到评分 ≥ 4.0。
- **等待用户决策**：达到修订上限或用户主动发言后，系统暂停等待用户指导。
- **SSE 实时推送**：ChatRoom 支持消息订阅，前端实时收到每条 Agent 发言（无需轮询）。

### 全自动 AI 科学家流程
- **需求自动分解**：用户输入万字以上长提示词时，`RequirementDecomposer` 自动拆解为结构化研究计划（研究目标、子任务、方法提示等），存储到项目目录供所有 Agent 读取。
- **创新点发现**：`InnovationAgent` 从文献调研结果中系统性识别研究空白，提出 3-5 个创新方案（含新颖性、方法论、可行性评估）。
- **实验自动迭代**：实验完成后自动评估质量（检查 baseline 对比 + ablation study），不足时自动调整并重新执行（最多 3 轮）。
- **任务完成总结**：`SummaryAgent` 生成结构化总结报告（研究回顾、创新点、实验结果、论文质量评估、经验教训、数据集/文献清单）。
- **经验分类存储**：经验按 method_selection/data_processing/writing/experiment_design/template_specific 五大类存储，支持标签检索、影响力评分、使用频率排序。
- **知识库自动分类**：任务结束后自动扫描下载的文献/数据集，按类型×领域×方法×质量四维度分类，注册到全局知识库。
- **全自动无人值守**：支持自动重试（最多2次）、断点恢复、任务超时控制（2小时），无需人工干预即可完成全流程。

### Web UI（Next.js 14）
- 首页 / 生成 / 数据 / PDF / 历史 / Agent / 流程 / 记忆 / 环境 / 设置 10 个 Tab
- SSE 实时消息流 + 任务状态机可视化 + Camera-Ready 面板
- 用户可在 Agent 讨论中实时发言，参与决策
- 暂停 / 恢复 / 取消 / Edit-and-Continue 完整生命周期
- 14+ React 组件 + Zustand 状态管理

---

## ⚠️ 能力边界与诚实声明

### 系统能做什么

| 能力 | 状态 | 说明 |
|------|------|------|
| 结构完整的论文生成 | ✅ | 8 套模板，从摘要到参考文献 |
| 真实代码执行 | ✅ | Python 沙箱执行，结果真实 |
| 真实文献检索 | ✅ | arXiv + Semantic Scholar，真实论文 |
| 真实 GPU 实验执行 | ✅ | 支持小模型（ResNet-18、BERT-base）在单卡上训练 |
| LaTeX 编译输出 | ✅ | `.cls/.sty` 文件已补齐，可生成 PDF |
| 断点续传 | ✅ | 任务中断后可从 checkpoint 恢复 |
| 显存监控/OOM 防护 | ✅ | VRAMMonitor 实时监控，超阈值自动保护 |
| 检查点保存/恢复 | ✅ | CheckpointManager 自动管理 |
| Human-in-loop | ✅ | 暂停/恢复/编辑，用户可介入 |
| 自主数据收集 | ✅ | Preflight 检测到缺失时自动搜索下载 |
| 数值范围校验 | ✅ | 准确率>1.0 为 error，引用一致性检查 |
| 实验可复现性检查 | ✅ | Peer Review 检查 train 脚本/随机种子/超参数 |
| **神经架构搜索（NAS）** | ✅ v6.0 | 进化算法自动探索网络结构，适合单卡 8GB |
| **自动损失函数设计** | ✅ v6.0 | 进化算法搜索最优损失函数结构 |
| **跨论文研究空白识别** | ✅ v6.0 | 自动分析多篇论文 limitations，识别共同 gap |
| **代码自动演化** | ✅ v6.0 | 求解成功后迭代改进，非一次性生成 |
| **AutoML 超参数搜索** | ✅ v6.0 | TPE 贝叶斯优化自动搜索超参数空间 |

### 系统不能做什么（诚实声明）

| 限制 | 说明 |
|------|------|
| **无法保证真正的新颖性** | 系统无法与全部已有文献做对比，"novelty" 评分是 LLM 自我评估，非真实审稿人判断 |
| **无法保证实验结果可复现** | 虽然代码真实执行，但 LLM 生成的代码可能有 bug，复杂实验（分布式训练、多 GPU）无法执行 |
| **无法替代研究者的创造性** | 研究想法、方法创新、问题定义仍需人类输入 |
| **大模型训练受限** | 单卡 8GB 显存无法训练 7B+ 参数模型，只能做小模型实验（ResNet-18、BERT-base） |
| **引用准确性有限** | 虽然验证 arXiv ID 存在，但无法验证引用内容是否准确对应原文 |
| **LaTeX 编译可能失败** | 生成的 LaTeX 代码可能有语法错误，系统会尝试编译但无法保证 100% 成功 |
| **长程任务稳定性** | 虽然支持断点续传，但长时间运行（>12h）仍可能因系统资源问题中断 |
| **NAS/AutoML 搜索深度有限** | 单卡 8GB 限制，NAS 种群大小和代数较小，AutoML 迭代次数受限 |
| **代码演化可能陷入局部最优** | 基于变异的演化不保证全局最优，可能错过更好的架构设计 |

### 与 AI Scientist 的差距

| 能力 | AI Scientist (Nature) | 我们的系统 |
|------|----------------------|-----------|
| 真实实验执行 | ✅ 在真实数据集上训练模型 | ✅ 支持，但受限于单卡 8GB 显存 |
| 新颖性验证 | ✅ 与已有论文对比 | ⚠️ LLM 模拟评估，非真实对比 |
| 真实审稿 | ✅ 人类审稿人 | ⚠️ LLM 模拟审稿 |
| 可复现性 | ✅ 代码+数据公开 | ⚠️ 代码公开，但环境配置可能不同 |
| 端到端无人值守 | ✅ 完全自主 | ⚠️ 需要人类设定研究方向和检查关键节点 |

### 使用建议

1. **作为论文写作辅助工具**：系统可快速生成论文框架、执行标准实验、整理文献，研究者在此基础上修改完善
2. **聚焦轻量级方法**：单卡 8GB 适合模型压缩、高效注意力、小样本学习等方向
3. **人工审核关键节点**：实验设计、核心创新点、主要结论需要研究者确认
4. **多次迭代优化**：利用 peer review + revise 循环逐步提升论文质量
5. **不要直接投稿**：系统产出的是"初稿"，需要研究者深度修改后才能投稿

---

## 📚 论文产出样例

本系统已在 `outputs/` 下产出两篇智能体记忆研究方向的论文（中英双语）：

| 论文 | 模板 | 任务 ID | 路径 | PDF |
|------|------|---------|------|-----|
| Memora: Structured Episodic Memory for Long-Horizon LLM-Based Multi-Agent Collaboration | NeurIPS 2024 | `task_2254a4eaf8b6` | `outputs/agent_memory_paper_en/output/` | `main.pdf` (21 页) |
| 面向长程多智能体协作的结构化情景记忆机制研究 | ACM SIGCONF | `task_13db1ab8780c` | `outputs/agent_memory_paper_zh/output/` | `main.pdf` |

每个输出目录结构：
```
output/
├── main.pdf              # 编译好的 PDF
├── main.tex              # LaTeX 源文件
├── models.json           # 所有模型设计
├── solves.json           # 求解结果（含数值结果、key_findings）
├── code/                 # 每个子问题的 Python 求解代码
└── htgmm_results.png     # 实验结果图（如有）
```

---

## ⚡ 快速开始

### 环境要求
- Python 3.9+
- Node.js 18+（Web UI）
- TeX Live（含 `xelatex`）— 仅打包 Camera-Ready 时需要
- NVIDIA GPU + CUDA（可选，用于真实实验执行；无 GPU 时自动回退 CPU）
- 可访问 LLM Provider（OpenAI / Anthropic / 阿里百炼 / Kimi / DeepSeek 等任意一个）

### 启动后端

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 Provider（在 .env 或前端 Settings 里）
# 示例：Kimi
export ANTHROPIC_BASE_URL="https://api.kimi.com/coding/"
export ANTHROPIC_AUTH_TOKEN="sk-kimi-..."

# 3. 启动后端
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# → http://localhost:8000/api/v1
# → API 文档 http://localhost:8000/docs
```

### 启动前端

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### 一句话启动（开发模式）

```bash
# 后端
cd backend && python -m uvicorn app.main:app --reload --port 8000 &

# 前端
cd frontend && npm run dev &
```

### Docker 部署（v7.3 新增）

```bash
# 一键启动后端 + Redis
docker compose up -d

# 或手动构建
docker build -t mathmodel-backend .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-... mathmodel-backend
```

---

## 🖥️ Web UI 使用

1. 打开 http://localhost:3000
2. **「设置」** Tab → 添加 Provider（输入 base_url、api_key、model）→ 设为默认
3. **「生成」** Tab → 选模板（CUMCM / NeurIPS / ACM / IEEE / Springer）→ 输入题目 → 提交
4. **「生成」** Tab 实时显示 10 阶段状态：
   - `preflight_running` → `self_collecting_data`（如需）→ `running` → `iterating_solver` → `waiting_for_user`（如需）→ `completed`
5. 完成后 **「PDF」** Tab 触发 Camera-Ready 打包 → 下载 zip

---

## ⌨️ 命令行使用

### CLI 单题模式
```bash
python main.py \
    --problem "智能体记忆研究方向论文：设计长程协作的结构化记忆框架" \
    --template neurips_2024 \
    --project my_paper \
    --mode batch
```

### 全自动扫描
```bash
python main.py --auto --workspace ./workspace
```

---

## 🔌 API 说明

所有端点前缀：`/api/v1`。

### 任务管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/tasks/submit` | POST | 提交新任务 |
| `/tasks/{id}/status` | GET | 获取任务状态 |
| `/tasks/{id}/stream` | GET | SSE 事件流 |
| `/tasks/{id}/result` | GET | 任务结果（含各 Agent 输出） |
| `/tasks/{id}/camera-ready` | POST | 一键打包可投稿 zip |
| `/tasks/{id}/pause` / `/resume` / `/cancel` | POST | 生命周期控制 |
| `/tasks/{id}/messages` | GET | Agent 协作消息 |
| `/tasks/{id}/debug-history` | GET | 任务执行历史 |

### Provider 管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/providers/` | GET | 列出所有 Provider |
| `/providers/` | POST | 创建自定义 Provider |
| `/providers/{id}` | PUT / DELETE | 修改 / 删除 |
| `/providers/{id}/default` | POST | 设为默认 |
| `/providers/{id}/test` | POST | 测试连通性 |
| `/providers/presets` | GET | 列出 15+ 预设 |
| `/providers/import-preset` | POST | 一键导入预设 |

### Agent 管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/agents/` | GET | 列出所有 Agent |
| `/agents/{name}/model` | PUT | 修改 Agent 使用的模型 |
| `/agents/{name}/test-model` | POST | 测试 Agent 模型连通性 |

### 环境管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/environments/backends` | GET | 列出可用后端（conda / venv） |
| `/environments/` | GET | 列出所有环境 |
| `/environments/` | POST | 创建环境 |
| `/environments/active` | GET | 获取当前激活环境 |
| `/environments/activate` | POST | 激活指定环境 |
| `/environments/install` | POST | 在指定环境安装依赖 |
| `/environments/run` | POST | 在指定环境执行命令 |
| `/environments/{backend}/{name}` | DELETE | 删除环境 |

### MCP 工具管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/mcp/servers` | GET / POST | 列出 / 创建 MCP Server |
| `/mcp/servers/{id}` | PUT / DELETE | 修改 / 删除 |
| `/mcp/servers/{id}/test` | POST | 测试连接 |
| `/mcp/tools` | GET | 列出所有可用工具 |

### 知识库管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/knowledge/bases` | GET / POST | 列出 / 创建知识库 |
| `/knowledge/bases/{id}/items` | POST | 添加知识点 |
| `/knowledge/bases/{id}/search` | POST | TF-IDF 语义检索 |

### 记忆管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/memory/tasks/{id}/working` | GET | 任务工作记忆 |
| `/memory/tasks/{id}/episodic` | GET | 任务事件流 |
| `/memory/lessons` | GET / POST | 跨任务经验教训 |
| `/memory/lessons/{id}/feedback` | POST | 用例反馈，更新 use_count |

### 讨论管理（v7.0 新增）
| 端点 | 方法 | 说明 |
|------|------|------|
| `/discussions/{task_id}/start` | POST | 发起新讨论 |
| `/discussions/{task_id}/propose` | POST | 添加提案 |
| `/discussions/{task_id}/message` | POST | 发送讨论消息（人类可参与） |
| `/discussions/{task_id}/vote` | POST | 投票（approve/reject/abstain） |
| `/discussions/{task_id}/human-decide` | POST | 人类最终决策 |
| `/discussions/{task_id}` | GET | 获取讨论状态 |
| `/discussions/{task_id}/summary` | GET | 获取讨论总结 |

---

## 🏗️ 系统架构

```
Web UI (Next.js 14 + Zustand)
        ↓ REST + SSE
FastAPI Backend
  ├─ Routers (tasks / agents / providers / mcp / knowledge / memory / discussion)
  ├─ Orchestrator (两阶段工作流)
  │    ├─ Phase 1: analyzer → data → research → [暂停]
  │    └─ Phase 2: modeler + solver → writer → peer_review → finalizing
  ├─ LangGraph Orchestrator (StateGraph 编排，v7.1 全自动流程 + ReAct 动态迭代)
  │    ├─ requirement_decomposition → preflight → analyzer → data → research
  │    ├─ innovation → discuss_approach → modeler → experiment(自动迭代) → solver
  │    ├─ figure → writer → peer_review → fact_check → summary → END
  │    ├─ 条件边：CCF-A 模板自动走 experiment 节点
  │    ├─ 讨论投票系统：Agent 可发起结构化讨论 + 投票
  │    ├─ 断点续传：checkpoint 保存与恢复
  │    └─ 自动重试：失败自动重试（最多2次）
  ├─ AgentModelRouter (按 (agent, template) 路由 LLM)
  ├─ MemoryManager (三级记忆: working / episodic / lessons + 标签检索)
  ├─ PaperMemoryPool (全局论文记忆池：术语/符号/结论跨章节一致性)
  ├─ PaperTemplateRegistry (JSON-driven 模板注册)
  ├─ KnowledgeOrganizer (知识库自动分类: 类型×领域×方法×质量)
  ├─ GPUExecutor (GPU 训练执行 + VRAMMonitor 显存监控 + CheckpointManager)
  └─ LLM Provider Layer (15+ Provider, 5 种 API 格式)
        ↓ HTTPS
   OpenAI / Anthropic / 阿里百炼 / Kimi / DeepSeek / Ollama / ...
```

### 关键模块
- `backend/app/agents/orchestrator.py` — 两阶段主编排器（Classic）
- `backend/app/agents/langgraph_orchestrator.py` — LangGraph StateGraph 编排器（推荐，支持断点续传）
- `backend/app/agents/{base,analyzer,data,research,modeler,solver,writer,peer_review,experimentation}_agent.py` — Agent 实现
- `backend/app/agents/base.py` — BaseAgent + AgentFactory + AgentModelRouter + ReAct 工具循环 + 双模式代码生成（Claude CLI + HTTP API）
- `backend/app/agents/demo_code_templates.py` — 15+ 数学建模算法模板
- `backend/app/core/agent_model_map.py` — AgentModelRouter 注册表
- `backend/app/core/paper_templates/` — 论文模板注册表
- `backend/app/core/memory.py` — 三级记忆系统
- `backend/app/core/gpu_executor.py` — GPUExecutor + VRAMMonitor + CheckpointManager
- `backend/app/services/result_validator.py` — ResultValidator + CrossValidator
- `backend/app/services/camera_ready.py` — Camera-Ready 打包
- `backend/app/services/experiment_executor.py` — 实验全生命周期编排（数据集→代码生成→环境→执行→聚合）
- `backend/app/services/experiment_runner.py` — 实验批量执行（集成 GPUExecutor）
- `backend/app/services/code_sandbox.py` — 代码沙箱（静态扫描+路径白名单+超时+内存限制）

---

## 🧠 Agent 通信与记忆机制

### 1. Agent 间通信架构

本系统采用**黑板模式 + 消息总线**的混合通信架构：

```
┌─────────────────────────────────────────────────────────────┐
│                    TaskState (共享状态)                       │
│  ├─ problem_text, template, workflow                         │
│  ├─ sub_problems[]                                          │
│  ├─ section_results[] (各阶段产出)                           │
│  ├─ results: {analyzer_agent, modeler_agent, ...}            │
│  ├─ peer_review_feedback                                     │
│  └─ paper_memory (全局论文记忆池)                             │
└─────────────────────────────────────────────────────────────┘
         ↑↓ 读写                          ↑↓ 事件订阅
    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │Analyzer │ →  │Modeler  │ →  │Solver   │ →  │Writer   │
    │Agent    │    │Agent    │    │Agent    │    │Agent    │
    └─────────┘    └─────────┘    └─────────┘    └─────────┘
         ↑              ↑              ↑              ↑
         └──────────────┴──────────────┴──────────────┘
                    ChatRoom (SSE 消息总线)
                    ├─ Agent 讨论消息
                    ├─ 用户实时发言
                    └─ 系统状态事件
```

**通信方式**：
- **同步状态共享**：Orchestrator/LangGraph 通过 `TaskState` 传递上下文，Agent 从 state 读取输入、写入输出
- **异步消息总线**：`ChatRoom` 支持 SSE 实时推送，Agent 讨论时互相发送消息，用户可实时介入
- **记忆检索**：Agent 通过 `MemoryManager` 检索历史经验，独立决策是否复用

### 2. 上下文长度管理

LLM 上下文窗口有限（通常 8K-128K），长论文生成时容易超出。本系统采用**多层压缩策略**：

| 层级 | 策略 | 实现 |
|------|------|------|
| **输入压缩** | 只传递必要上下文 | Agent 从 `TaskState` 按需提取，不传递全量历史 |
| **摘要传递** | 前序结果→摘要→后续 | 每章生成 `chapter_summary`（100-200字），后续章节只接收摘要 |
| **全局记忆池** | 术语/符号/结论集中维护 | `paper_memory` 维护全文一致性信息，避免重复描述 |
| **State 外部化** | 大输出不存 State | `TaskResultStore` 将 Agent 输出持久化到磁盘，State 只存引用标记 |
| **分段生成** | 章节独立调用 | WriterAgent 每章独立调 LLM，而非一次性生成整篇论文 |

### 3. 记忆机制（三级架构）

```
┌─────────────────────────────────────────────────────────────┐
│                    Lessons Memory (跨任务)                     │
│  • 经验提取：任务完成后自动 extract_lessons_from_result      │
│  • 经验检索：新任务启动时 retrieve_relevant 注入 prompt      │
│  • 反馈闭环：用户反馈更新 use_count，优质经验优先复用          │
│  存储：backend/data/memory/lessons.json                       │
└─────────────────────────────────────────────────────────────┘
                              ↑↓ 经验沉淀/复用
┌─────────────────────────────────────────────────────────────┐
│                   Episodic Memory (任务级)                     │
│  • 事件流：Agent 执行日志、讨论记录、用户干预                 │
│  • 时间线：按时间顺序记录完整决策过程                         │
│  • 可追溯：debug-history API 可回放任意任务                   │
│  存储：backend/data/memory/tasks/{task_id}.json               │
└─────────────────────────────────────────────────────────────┘
                              ↑↓ 事件记录
┌─────────────────────────────────────────────────────────────┐
│                   Working Memory (任务上下文)                  │
│  • 当前任务状态：problem_text, sub_problems, section_results  │
│  • Agent 私有记忆：每个 Agent 独立的记忆池（关键词检索）        │
│  • 全局论文记忆池：writer_agent 维护的术语/符号/结论表          │
│  存储：内存 + TaskState + paper_memory                       │
└─────────────────────────────────────────────────────────────┘
```

### 4. 全局论文记忆池（v5.0）

解决长论文生成中的**术语不一致、符号冲突、结论矛盾**问题：

```python
paper_memory = {
    "terminology": {      # 术语表：确保全文使用统一术语
        "神经网络": "modeling",  # {术语: 首次出现章节}
        "LSTM": "modeling",
    },
    "symbols": {          # 符号表：确保符号含义一致
        "W": {"meaning": "权重矩阵", "unit": "", "chapter": "modeling"},
        "b": {"meaning": "偏置向量", "unit": "", "chapter": "modeling"},
    },
    "key_claims": [       # 关键结论：确保后续章节引用正确
        {"claim": "LSTM 在时序预测上优于 ARIMA", "chapter": "results", "evidence": "summary"},
    ],
    "model_names": ["LSTM", "ARIMA", "Random Forest"],  # 方法名称
    "algorithms": ["Adam", "SGD"],                        # 算法名称
    "datasets": ["IMDB", "CIFAR-10"],                      # 数据集
    "metrics": ["Accuracy", "F1", "BLEU-4"],               # 指标
    "cross_references": {},  # 章节引用关系
    "chapter_summaries": {}, # 各章摘要
}
```

### 5. 实验执行记忆

ExperimentationAgent 执行真实实验后，结果通过 `experiment_result` 注入 WriterAgent：

```python
experiment_result = {
    "success": True,
    "executed": True,
    "aggregated": {
        "markdown_table": "| Method | Accuracy |\n|--------|----------|\n| Our Method | 0.95 |",
        "latex_table": "\\begin{table}...",
        "summary_text": "相比最强 baseline 提升 5.3%",
        "best_baseline": "Baseline B",
    },
    "raw_batch": {...},  # 原始实验结果
    "dataset_info": {"names": ["CIFAR-10"], "splits": [...]},
    "code_dir": ".../experiments/code",
    "checkpoints": [...],  # 检查点列表
    "gpu_used": True,
    "vram_peak_mb": 6144,
}
```

WriterAgent 在 `experiment` 和 `results_discussion` 章节自动注入真实实验结果，**禁止编造数字**。

---

## 📐 算法与论文模板

### 经典数学建模算法（15+）
`demo_code_templates.py` 内置：
- 优化：LP、IP、MILP、GA、PSO
- 预测：ARIMA、灰色预测、LSTM
- 评价：AHP、TOPSIS、熵权法、灰色关联
- 图论：最短路径、最小生成树、网络流
- 统计：聚类、判别、主成分、因子分析
- 数值方法：插值、拟合、数值积分

### 论文模板（8 套 + 可扩展）
在 `backend/app/core/paper_templates/templates/` 下：
- `cumcm.json` — 全国大学生数学建模竞赛
- `neurips_2024.json` — NeurIPS 2024（CCF-A）
- `acm_sigconf.json` — ACM SIG Conference（CCF-A）
- `ieee_conference.json` — IEEE Conference（CCF-A）
- `springer_lncs.json` — Springer LNCS（CCF-B）
- `research_survey.json` — Research Survey
- `coursework.json` — 课程作业
- `financial_analysis.json` — 金融分析

新增模板只需在 `templates/` 下加 JSON + 对应 `.cls/.sty`，注册表自动加载。

---

## 📁 项目结构

```
MathModel-MutiAgentSystem/
├── backend/                       # FastAPI 后端
│   ├── app/
│   │   ├── agents/                # 所有 Agent 实现
│   │   │   ├── base.py            # BaseAgent + AgentFactory + AgentModelRouter + ReAct + 双模式代码生成
│   │   │   ├── orchestrator.py    # 两阶段主编排器（Classic）
│   │   │   ├── langgraph_orchestrator.py # LangGraph StateGraph 编排器（推荐，支持断点续传）
│   │   │   ├── analyzer_agent.py
│   │   │   ├── data_agent.py
│   │   │   ├── research_agent.py
│   │   │   ├── modeler_agent.py
│   │   │   ├── algorithm_engineer_agent.py
│   │   │   ├── financial_analyst_agent.py
│   │   │   ├── solver_agent.py    # 含 CrossValidator + experiment 模式 + 双模式代码生成
│   │   │   ├── writer_agent.py      # 含全局论文记忆池 v5.0
│   │   │   ├── peer_review_agent.py # 含实验可复现性检查
│   │   │   ├── experimentation_agent.py
│   │   │   ├── requirement_decomposer.py  # 需求分解器（v7.0）
│   │   │   ├── innovation_agent.py        # 创新发现专家（v7.0）
│   │   │   └── summary_agent.py           # 任务总结专家（v7.0）
│   │   ├── core/                  # 核心模块
│   │   │   ├── memory.py          # 三级记忆系统
│   │   │   ├── agent_model_map.py # AgentModelRouter
│   │   │   ├── paper_templates/   # 论文模板注册表
│   │   │   ├── gpu_executor.py    # GPUExecutor + VRAMMonitor + CheckpointManager
│   │   │   ├── nas.py               # 神经架构搜索（进化算法，v6.0）
│   │   │   ├── loss_design.py       # 自动损失函数设计（进化算法，v6.0）
│   │   │   ├── sandbox.py           # 代码沙箱（统一：namespace + import hook + 静态扫描 + 路径白名单）
│   │   │   ├── agent_discussion.py  # 多Agent讨论投票系统（v7.0）
│   │   │   ├── chat_room.py
│   │   │   ├── event_bus.py         # EventBus 事件总线（v7.2）
│   │   │   ├── task_manager.py      # AsyncTaskManager 异步任务队列（v7.2）
│   │   │   ├── context_compressor.py # 上下文压缩器
│   │   │   ├── circuit_breaker.py   # 熔断器
│   │   │   ├── llm/                 # LLM 客户端 + 14 个 Adapter + 缓存
│   │   │   ├── paths.py
│   │   │   └── task_persistence.py # Checkpoint 保存与恢复
│   │   ├── services/              # 服务层
│   │   │   ├── result_validator.py  # ResultValidator + CrossValidator（含准确率>1.0检查）
│   │   │   ├── camera_ready.py      # Camera-Ready 打包
│   │   │   ├── experiment_executor.py # 实验全生命周期编排
│   │   │   ├── experiment_runner.py   # 实验批量执行（集成 GPUExecutor）
│   │   │   ├── experiment_result_aggregator.py # 结果聚合与表格生成
│   │   │   ├── code_manifest.py     # 代码文件清单校验
│   │   │   ├── self_collector.py    # 自主数据收集（httpx 并发下载）
│   │   │   ├── automl.py            # AutoML 超参数搜索（TPE 贝叶斯优化）
│   │   │   ├── knowledge_organizer.py # 知识库自动分类整理（v7.0）
│   │   │   ├── rate_limiter.py      # AsyncTokenBucket 令牌桶限流（v7.3）
│   │   │   ├── knowledge.py
│   │   ├── mcp/                   # MCP 客户端
│   │   ├── routers/               # FastAPI 路由（含 discussion.py 讨论API v7.0）
│   │   ├── schemas/               # Pydantic 模型
│   │   └── main.py                # FastAPI app
│   ├── data/
│   ├── tests/
│   └── app.log
├── frontend/                      # Next.js 14 Web UI
│   └── src/app/
│       ├── page.tsx               # 主页面（10 个 Tab）
│       ├── components/            # 24 个组件（含 DiscussionPanel v7.0）
│       ├── hooks/                  # useTaskState 等
│       └── store/                  # Zustand
├── config/
│   ├── latex_templates/           # LaTeX 样式文件（.cls/.sty）
│   └── mcp_config.json
├── outputs/                       # 论文产出
│   ├── agent_memory_paper_en/     # 英文 Memora 论文
│   └── agent_memory_paper_zh/     # 中文 ACM 论文
├── data/                          # 共享数据
├── workspace/                     # 用户工作空间
├── .env                           # Provider 密钥
├── Dockerfile                     # Docker 镜像定义（v7.3）
├── docker-compose.yml
├── main.py                        # CLI 入口
├── requirements.txt
├── 技术说明文档.md                 # 详细技术架构文档
└── README.md
```

---

## ⚙️ 配置说明

### `.env`（必填项）
```bash
# Provider 选一
ANTHROPIC_API_KEY=sk-ant-...
# 或
OPENAI_API_KEY=sk-...
# 或（Anthropic 兼容）
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
ANTHROPIC_AUTH_TOKEN=sk-kimi-...

# 可选
DEFAULT_MODEL=sonnet
DATABASE_URL=sqlite:///./data/agents.db

# GPU 配置（可选，无 GPU 时自动回退 CPU）
CUDA_VISIBLE_DEVICES=0

# 全自动模式（v7.0 新增）
MATHMODEL_API_KEY=your-secret-key    # 可选：启用 API 认证
```

### 自动模式配置（v7.0 新增）
在 `backend/app/config.py` 中可配置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `auto_mode_enabled` | True | 全自动模式开关 |
| `max_concurrent_tasks` | 3 | 最大并发任务数 |
| `task_timeout_seconds` | 7200 | 单任务超时（2小时） |
| `auto_retry_on_failure` | True | 失败自动重试 |
| `max_retry_count` | 2 | 最大重试次数 |
| `experiment_max_iterations` | 3 | 实验自动迭代上限 |
| `human_intervention_timeout` | 300 | 人类介入超时（5分钟） |

> 注：运行时产物统一输出到 `outputs/<project>/`（无项目时写入 `outputs/_global/`），无需通过环境变量配置输出根目录。

---

## 🔧 故障排除

### 后端启动失败
- **缺包**：`pip install -r requirements.txt`
- **端口占用**：改 `--port 8001`
- **`.env` 缺失**：从 `.env.example` 复制

### Provider 调用失败
- `curl http://localhost:8000/api/v1/providers/{id}/test` 测试连通性
- 查看 `backend/app.log` 或 `uvicorn.log`

### 论文卡在 `solver_agent`
- SolverAgent 调 LLM 写代码 → 沙箱执行 → retry。失败 3 次会 fallback 到 demo 模板。
- 复杂问题可改 `--mode sequential` 逐题递进。
- 检查是否有 GPU 和 CUDA（`nvidia-smi`），无 GPU 时实验会回退到 CPU 模式。

### Camera-Ready 提示 `main.tex not found`
- WriterAgent 的 latex_code 字段已含完整 LaTeX，但 orchestrator 默认不会把它写到磁盘。
- Workaround：用 `POST /api/v1/tasks/{id}/result` 拿 `output.writer_agent.latex_code` → 写到 `output/main.tex` → 再调 camera-ready。
- 或手动打 zip：`cd outputs/.../output && xelatex main.tex && zip camera_ready_paper_xx.zip main.tex code/ figures/ solves.json models.json`

### LaTeX 中文乱码
- 确保系统装了 Noto CJK 字体（`apt install fonts-noto-cjk`）
- 编译命令：`xelatex -interaction=nonstopmode main.tex`

### GPU OOM（显存不足）
- 系统会自动估算推荐 batch size，但 LLM 生成的代码可能忽略此建议
- 手动降低 batch size 或选择更小的模型
- 检查 VRAMMonitor 日志了解显存使用峰值

### 任务中断后无法恢复
- 确认 `backend/data/tasks/` 目录存在且可写
- 检查 checkpoint 文件是否存在（`{task_id}_checkpoints.json`）
- 调用 `POST /tasks/{id}/resume` 触发恢复

---

## 📜 版本历史

### v7.4（2026-07-07）— 当前
- **安全加固（T3-T5）**：
  - **输入验证**：`TaskCreateRequest` Pydantic 约束（problem_text 1-100000 字符 + 控制字符清理，project_name 仅允许安全字符）；文件上传 50MB 大小限制 + HTTP 413 响应；文件名清理
  - **路径穿越防护**：`validate_path_within()` 校验 5 个文件操作端点，`Path.resolve()` 解析符号链接防止 symlink escape
  - **Prompt 注入防御**：`wrap_user_content()` 用 XML 标签包裹用户输入 + HTML 实体转义，BaseAgent + 14 个 Agent 全部使用
  - **共享安全模块**：`backend/app/core/security.py` 提供 5 个安全工具函数
  - **81 个安全测试**：覆盖路径穿越、输入验证、Prompt 注入、端点防护
- **前端重构完成**：
  - 15 个 Next.js 路由（三栏布局：Sidebar + Main + DetailPanel）
  - Tailwind CSS v4 + shadcn/ui + Framer Motion 动画
  - Agent 拓扑可视化、实时日志流、主题切换、响应式设计
- **知识库自动分类 Bug 修复**：修正 import 错误 + 扫描路径扩展

### v7.3（2026-07-05）
- **统一沙箱实现**：合并 `core/sandbox.py`（namespace 隔离 + import hook）与 `services/code_sandbox.py`（静态扫描 + 路径白名单）为单一 `CodeSandbox`，消除两套实现的安全策略不一致问题
- **Docker 化部署**：新增 `Dockerfile`（python:3.11-slim + TeX Live + CJK 字体），`docker-compose.yml` 一键启动后端 + Redis
- **API 限流**：`AsyncTokenBucket` 令牌桶限流器集成到 LLM 调用路径（`UnifiedLLMClient`），防止 API 配额耗尽
- **LLM 调用缓存**：`LLMCache` 基于 SHA256 哈希的请求级缓存（TTL 30 分钟，最大 200 条），开发调试时避免重复调用

### v7.2（2026-07-04）
- **SSE 实时推送（事件驱动）**：
  - **EventBus**：全局事件总线，基于 asyncio.Queue 的发布-订阅模式
  - **实时事件流**：Agent 执行状态变化时立即推送（agent_start/agent_complete/phase_change/error）
  - **历史回放**：新订阅者自动收到最近 100 条历史事件
  - **替代轮询**：`GET /tasks/{id}/stream` 从 2 秒轮询升级为事件驱动
- **并行 Agent 执行**：
  - **parallel_analysis 节点**：data_agent + research_agent + innovation_agent 同时执行
  - **asyncio.gather 并发**：三个 Agent 并行运行，结果自动合并到 state
  - **时间节省**：原本串行执行 3 个 Agent 约 3 分钟，并行后约 1 分钟
- **异步任务队列**：
  - **AsyncTaskManager**：替代 fire-and-forget 的 asyncio.create_task
  - **并发限制**：最多 3 个任务同时运行（通过 Semaphore 控制）
  - **任务取消**：支持真正取消底层协程
  - **状态跟踪**：pending/running/completed/failed/cancelled
  - **与 EventBus 集成**：任务状态变化自动推送
- **Agent 单元测试**：
  - **31 个测试用例**：覆盖所有 Agent（analyzer/data/research/modeler/solver/writer/peer_review/innovation/requirement_decomposer/summary/experimentation/algorithm_engineer/financial_analyst）
  - **模板测试**：验证 11 个代码模板无 TODO 占位符
  - **基础设施测试**：EventBus/TaskManager/Memory/ContextCompressor/CircuitBreaker
  - **Mock LLM**：所有 Agent 测试使用 mock，不消耗真实 API 额度

### v7.1（2026-07-04）
- **ReAct 循环改进（核心）**：
  - **动态迭代次数**：基于工具数量和上下文长度预估所需迭代数 × 1.5 作为上限，硬上限 20
  - **实时监控**：每 60 秒检查 token 使用量，超过预算 80% 自动触发压缩
  - **滑动窗口 + 摘要混合**：保留最近 6 轮完整历史，旧的 tool call 压缩为摘要（参考 MemGPT）
  - **Token 预算优化**：react_history 从 8% 增至 15%，新增 summary_buffer 5%
- **真实评估器接入**：
  - **NAS**：`_default_evaluator` 现在实际训练 3 epoch 返回真实准确率（失败回退到参数量估算）
  - **Loss Design**：`_default_evaluator` 实际训练返回验证损失（失败回退到表达式复杂度）
  - **AutoML**：目标函数从 `lambda cfg: 0.5` 改为真实 CNN 训练评估
- **安全加固**：
  - **网络隔离**：`code_sandbox.py` 优先使用 `unshare --net` 真实 namespace（不可用时回退 + 警告）
  - **MCP Fallback**：`_execute_mcp_tool` 支持重试 + 本地降级（file_write/latex_compile/web_search/file_read）
  - **ReAct 不再调用 _mock_response**：循环耗尽时返回明确错误 JSON 而非编造结果
  - **modeler fallback**：LLM 失败时重试 2 次，仍失败标记 `_degraded_mode=True`
- **其他改进**：
  - **EpisodicMemory**：`compress()` 支持 LLM 智能摘要（通过 `llm_client` 参数）
  - **推理脚本**：`_generate_inference_script` 生成完整推理逻辑（支持 checkpoint/CSV/NPY）
  - **分析估计**：`_analytical_estimate` 不再返回无意义的 0.0 常量，改为范围校验
  - **交叉验证**：无替代方法时跳过（不做假比较）
  - **solver 模板**：`algorithm_design` 替换 TODO 为真实 Dijkstra + Kadane 实现
  - **experimentation_agent**：删除废弃的 `_try_smoke_execute`，`_empty_plan` 标记失败原因

### v7.0（2026-07-03）
- **全自动 AI 科学家流程**：
  - **需求自动分解器**：`requirement_decomposer.py`，万字以上长提示词自动拆解为结构化研究计划
  - **创新点发现**：`innovation_agent.py`，从文献调研中识别研究空白、提出创新方案
  - **多 Agent 讨论投票系统**：`agent_discussion.py` + `routers/discussion.py`，结构化讨论协议 + 投票引擎 + 人类介入
  - **任务总结 Agent**：`summary_agent.py`，任务完成自动生成总结报告 + 经验提取分类存储
  - **知识库自动分类**：`knowledge_organizer.py`，下载资源按类型×领域×方法×质量自动归类
  - **实验自动迭代**：实验完成后自动评估质量（baseline/ablation），不足时自动调整重新执行
  - **全自动配置**：`config.py` 新增 auto_mode_enabled/max_concurrent_tasks/task_timeout/auto_retry 等配置
  - **前端讨论面板**：`DiscussionPanel.tsx`，实时展示 Agent 讨论、支持用户投票和决策
- **安全加固**：
  - 命令执行端点白名单校验
  - 沙箱导入拦截钩子重新启用（Layer 3）
  - 可选 API Key 认证中间件
  - 全局异常处理不泄露内部信息
- **测试修复**：修复 7 个已有测试失败（research_survey 章节数、neurips_2024 断言、SOCKS 代理环境）
- **模板参数修复**：`GET /{id}/status` 返回 template/workflow_type/mode，修复前端 rerun/CameraReady 模板丢失

### v6.0（2026-06-29）
- **5 大自主研究能力**：
  - **神经架构搜索（NAS）**：`backend/app/core/nas.py`，进化算法自动探索网络结构，适合单卡 8GB 显存
  - **自动损失函数设计**：`backend/app/core/loss_design.py`，进化算法搜索最优损失函数结构
  - **跨论文研究空白识别**：`research_agent._identify_cross_paper_gaps()`，自动分析多篇论文 limitations
  - **代码自动演化**：`solver_agent.CodeEvolutionEngine`，求解成功后迭代改进而非一次性生成
  - **AutoML 超参数搜索**：`backend/app/services/automl.py`，TPE 贝叶斯优化自动搜索超参数空间
- **功能开关**：`backend/app/config.py` 支持独立启用/禁用 5 大能力
- **与 LangGraph 集成**：experiment 节点自动触发 NAS/AutoML/损失函数搜索，结果注入实验代码
- **技术说明文档更新**：第 12 章详细描述 5 大能力的设计与集成

### v5.4（2026-06-29）
- **GPU 显存监控与 OOM 防护**：VRAMMonitor 实时监控，85% 预警 / 95% 触发保护
- **检查点保存与恢复**：CheckpointManager 自动管理，支持从最新检查点恢复训练
- **ExperimentRunner 集成 GPUExecutor**：优先使用 GPU 执行实验，自动回退 CPU
- **断点续传**：LangGraph 编排器支持从 checkpoint 恢复任务状态
- **自主数据收集**：self_collect 节点实现真正的数据搜索和下载
- **Claude Code 双模式**：优先 CLI，不可用时自动回退 HTTP API
- **数值范围校验强化**：准确率>1.0、精确率<0 等设为 error 级别
- **实验可复现性检查**：Peer Review 新增 reproducibility 维度
- **.cls/.sty 路径修复**：cumcm 和 neurips 模板路径修正
- **solver_agent data_context bug 修复**：_solve_sequential 中补全变量定义
- **诚实能力声明**：README 和技术文档增加"系统不能做什么"章节

### v3.2（2026-06）
- **自动化实验执行**：ExperimentationAgent 真正执行实验（非仅设计方案），端到端流程：数据集搜索/下载 → solver_agent LLM 生成实验代码 → 独立 venv 环境 → 沙箱执行 → 结果聚合（baseline 对比 + ablation 消融）
- **SolverAgent experiment 模式**：新增 `action="experiment"`，LLM 生成 main.py + baseline_*.py + ablation_*.py，替代硬编码模板
- **代码沙箱**：CodeSandbox 静态扫描 + 路径白名单 + 超时 + 内存限制（POSIX setrlimit），拦截危险调用
- **全局论文记忆池 v5.0**：WriterAgent 维护跨章节的术语表、符号表、关键结论，解决长论文不一致问题
- **全局一致性检查**：所有章节生成后检查术语/符号/结论/数据一致性，发现问题自动修复
- **一键启动增强**：start.sh 彩色输出、自动检测、依赖增量更新、API Key 配置引导
- **五阶段流水线**：StageProgress 增加 experiment 阶段（分析→建模→求解→实验→写作）
- **CC-Switch 自动检测**：系统每 30s 轮询 `~/.cc-switch/cc-switch.db`，自动同步 Provider 配置

### v3.1（2026-06）
- **模板化建模路由**：`math_modeling`→modeler、`financial_analysis`→financial_analyst、CCF-A/`research_paper`→algorithm_engineer；deep_research/research_survey 跳过建模
- **算法工程师双模式**：`ALGORITHM_ENGINEER_SYSTEM_CCFA` + `ALGORITHM_ENGINEER_SYSTEM_MATH_MODELING`，按模板自动切换
- **金融分析师**：金融数学建模、风险分析、回测设计，强化防编造纪律
- **结果归一化**：三种建模 Agent 输出统一为 `sub_problem_models`，保留 `_raw_output` 供 writer 使用
- **防编造校验**：`_validate_no_fabrication` 检测无来源价格/收益率、无引用性能数字、异常引用；`_fabrication_flags` 透传给 writer
- **环境管理器**：`conda` / `venv` 生命周期管理 + `/api/v1/environments` API + 前端「环境」Tab
- **LangGraph State 外部化**：`TaskResultStore` 避免节点间深拷贝大输出
- **清理硬编码兜底模板**：移除 SiC/报童等过于具体的 `MODEL_TEMPLATES`，改为通用类别模板，并标记兜底结果

### v3.0（2026-06）
- **Phase 7** AgentModelRouter + CrossValidator
- **Phase 6** Camera-Ready + useTaskState hook + TaskStatusBadge
- **Phase 5** PDF 双轨统一 + PaperMetadata LRU 缓存
- **Phase 4** 可插拔 Reranker + LessonsMemory use_count 闭环
- **Phase 3** 实验设计 Agent + PeerReview 4 维评分
- **Phase 2** 8 数学建模模板 + 拆文件编程 + 同行评议 + Camera-Ready
- **Phase 1** 14 个 git commit 落地的通用论文产线

### v6.0（2026-07）
- **混合检索引擎**：语义检索（sentence-transformers）+ BM25 关键词检索，RRF 融合，替代纯 TF-IDF
- **所有 Agent 知识库查询**：BaseAgent 标准化 `_inject_knowledge_context()`，所有 Agent 可按需查询知识库
- **来源追踪**：每条检索结果标注来源文档、知识库名称、检索方式，用于论文末尾参考文献
- **NAS 智能决策**：协调者与研究员讨论决定是否执行 NAS（支持中英文关键词）
- **严格模式**：删除所有 fallback，任何 Agent 失败立即终止，不生成虚假内容
- **MCP 修复**：DuckDuckGo + Bing 搜索、微信公众号搜索、文件系统操作全部正常工作
- **死代码清理**：删除 `_mock_response`（400+ 行）和 `demo_code_templates.py`

### 历史版本
- v2.6 — CC Switch 风格 Provider 管理 + MCP 增强
- v2.0 — CrewAI 风格多 Agent 架构
- v1.0 — 数学建模单题 CLI

---

## 📝 引用

如使用本系统产出学术论文，请引用本仓库：

```bibtex
@misc{memm2026,
  title={A Multi-Agent System for Automated CCF-A Paper Generation with Real Code Execution and Cross-Method Validation},
  author={Anonymous Authors},
  year={2026},
  howpublished={\url{https://github.com/your-org/MathModel-MutiAgentSystem}}
}
```

---

## 📄 许可证

本项目仅供学术研究与教学使用。产出的论文请遵守目标期刊/会议的投稿规范与作者署名要求。

**重要提醒**：本系统产出的论文是"初稿"，需要研究者深度修改、审核关键结论和创新点后才能投稿。请勿将系统产出直接作为最终投稿版本。
