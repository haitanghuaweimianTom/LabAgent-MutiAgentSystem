# LabAgent 排查记忆索引

本目录记录 LabAgent 端到端联调中挖出并修复的隐蔽 bug 链。每条 memory 是一份独立排查笔记，含真因 + 复现 + 修复 commit。

## 2026-07-26 端到端修复链（MCP 全崩 → 出论文，20 commit）

从"solver 全部 Connection closed + 任务卡死"到"运输问题 ILP 端到端出论文+camera-ready zip+lessons"，逐层挖出 5 类根因，每修一个测一轮暴露下一个：

1. **进程级连不上 LLM**（[[labagent-embedding-blocks-event-loop]]，commit edf629c0）— agent 落到被墙的 api.openai.com（provider 缺凭证不回退 + 占位符 `your_api_key_here` 是 truthy）。repr+host 日志才看清。修：占位符识别 + provider 回退默认。
2. **MCP "Connection closed"**（[[labagent-mcp-connection-closed-root-cause]]，commit dee7a597）— npx file_system 服务器相对路径启动即退出 + 无 code_execute 工具。修：内置 `code_tools_server.py`（绝对路径+自建目录+沙箱）。
3. **跨任务 Lessons 闭环**（[[labagent-memory-pool-architecture]]，commit dee7a597）— 三处断：注入不自增 use_count / problem_type 漏注入 / 失败经验不提取。修：retrieve_relevant + 全模板 problem_type + failure 分类。
4. **solver 反复重试真因**（commits b124e19a→a2888784，详见 [[labagent-mcp-connection-closed-root-cause]] 第 24-33 行 8 类根因）— ReAct 工具注入致 LLM 不返回 JSON / harness cross-check 占位否决 / OpenBLAS 内存失败 / `_solve_single` 不解析 exec_output JSON 字符串致 numerical_results 空被 harness 误判。修：`tools=[]` 禁 ReAct + BLAS=1 + json.loads + validator 词边界。
5. **writer KB 构建死循环**（commits 2516808d/11217dfb）— 章节生成 ReAct 触发 paper_search → 每论文新建 task_kb → 0 LLM。修：writer call_llm 禁 ReAct + 引用收集跳过 `task_kb_*` 基。
6. **数据质量门禁误标 failed**（commit fc37ffcb）— pre 阶段警告让已产出论文的任务标 failed。修：写作完成时降级为质量警告、任务标 completed。

**验证**：运输问题 ILP 任务端到端出论文 + camera-ready zip + lessons(84 条, 3 条 use_count 自增)，solver 3/3 子问题 harness `passed=True`，total_cost=85（教科书最优）。

## 约束（务必遵守）

- **Token (ark-8b02e574-...) 绝不进 commit** —— 仅存 `backend/app/core/runtime_config.py`（gitignore）+ 环境变量。每次推送前 `git diff | grep ark-8b02e574` 扫描。
- **DAOS 后端（8000 端口，PID 见 `ss -tlnp`）不能杀** —— LabAgent 后端用 8200 端口。
- **Bug Finder (ml/serve_bug_finder.py, GPU 占 3G+) 不能杀**。
- **简历数字必须可复现、不注水** —— 避免宽松匹配 / 数据泄露。

## 详细笔记

- [LabAgent MCP "Connection closed" 真因](labagent-mcp-connection-closed-root-cause.md) — 含完整 8 类根因 + 18-fix 链
- [LabAgent 记忆池架构](labagent-memory-pool-architecture.md) — 两套记忆系统 + Lessons 闭环
- [LabAgent 进程级连不上 LLM 真因](labagent-embedding-blocks-event-loop.md) — provider 缺凭证回退 + 占位符识别
