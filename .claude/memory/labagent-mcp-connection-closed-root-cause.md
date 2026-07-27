---
name: labagent-mcp-connection-closed-root-cause
description: LabAgent MCP工具"Connection closed"真因——file_system npx服务器用相对路径启动即退出；已用内置code_tools Python服务器替代
metadata:
  type: project
  modified: 2026-07-26T13:05:28.350Z
  originSessionId: 2f01771d-9090-4607-b9da-653497292e0b
---

LabAgent 后端 solver/reAct 调 `code_execute`/`file_write` 时，日志全部 `MCP tool 'X' failed: Connection closed`（每调用都失败，重试也失败，最后 "No fallback available for MCP tool 'code_execute'"）。**真因不是网络**，而是 `file_system` MCP 服务器（`npx -y @modelcontextprotocol/server-filesystem ./workspace ./output`）：
1. 启动参数用**相对路径** `./workspace ./output`，后端 cwd 是 `backend/`，两目录都不存在 → 服务器打印 "None of the specified directories are accessible" → **立即退出** → MCPClient `McpError('Connection closed')`。
2. 该服务器只暴露 `read_file`/`write_file`，**根本没有 `code_execute` 工具**。
3. `_mcp_fallback` 原本只兜底 file_write/latex_compile/web_search，无 code_execute/file_read → 真正断了 solver 代码执行。

**Why:** "Connection closed" 是黑盒（看不出是连不上还是服务器主动退出）；必须实际 spawn 服务器看 stderr 才知道是"目录不存在→退出"。

**How to apply:** 排查"MCP tool failed: Connection closed"：直接 spawn 服务器命令看 stderr（多半是启动即退出）；检查 args 是否相对路径+目录是否存在。修复（commit dee7a597）：
- 新增 `app/mcp/code_tools_server.py` 内置 Python MCP 服务器（code_execute/file_read/file_write/latex_compile），工作目录**绝对路径**+启动时 `mkdir`，永不因目录缺失退出；文件操作沙箱限制在工作目录内；code_execute 以子进程 cwd=workspace 运行（相对 import/写文件生效）。
- `config.py`：注册 code_tools，`BUILTIN_TOOLS` 重映射 file_read/write/code_execute/latex_compile→code_tools；`_merge_builtin_servers()` 自愈（旧 mcp_config.json 未含 code_tools 也补齐，因 `load_config` 从文件加载会覆盖 BUILTIN_SERVERS）。
- `base.py _mcp_fallback`：补 code_execute/file_read 本地 fallback；修 file_write fallback 读 `path`（原读 `file_path` → 一直没生效）。

注意：solver 的 "LLM 未返回有效代码"是**另一个**问题——solver ReAct 用工具写文件/跑代码，但 `_solve_single` 期望最终返回结构化 JSON（`code_files[0].code`），LLM 返回散文则解析失败。MCP 修好后工具能跑了，但输出格式不匹配仍在 → 由 5 次重试后的 HTTP 降级（commit f85ae499）兜底。参见 [[labagent-memory-pool-architecture]]、[[labagent-embedding-blocks-event-loop]]。

**2026-07-26 完整端到端修复链（18 个 commit，从 MCP 全崩→端到端出论文）**：MCP 修好后 solver 仍失败，逐层挖出 5 类隐藏 bug，每修一个测一轮暴露下一个：
1. solver 代码生成 call_llm 自动注入 MCP 工具→ReAct 但 `_solve_single` 期望结构化 JSON → 加 `tools=[]` 禁用 ReAct（base.py `_call_claude_coder_http` + solver 3 处 + writer 3 处 共 7 处 call_llm 都要加）。
2. harness cross-check 用占位 secondary(`numerical×0.95`) 永远 diverged → 否决正确结果 → 占位不参与否决。
3. OpenBLAS 内存分配失败（多线程）→ 全局 `OPENBLAS_NUM_THREADS=1` 等。
4. numpy 数组 `json.dumps` TypeError → CLAUDE_CODER_SYSTEM 加序列化警告。
5. **`_solve_single` 不解析 exec_output JSON 字符串**（CLI/HTTP 返回 str）→ `numerical_results` 始终空 → harness 判"数值结果为空"否决正确解 → 加 `json.loads`。这是 solver 反复重试的**真因**。
6. result_validator 子串匹配 `'ratio' in 'iterations'` 误判比例字段 → 整词匹配。
7. writer `_collect_kb_sources_for_citations` 遍历 `km._bases` 全部基（含 paper_reader 留下的几十个临时 `task_kb_*`）→ 每个重建引擎 → KB 构建死循环、0 LLM → 跳过 `task_kb_*` 基。
8. pre 阶段数据质量门禁警告 `cannot_solve_report` 让已产出论文+交付的任务被标 `failed` → 写作完成时降级为质量警告、任务标 `completed`。
验证（2026-07-27 纠正注水）：solver 3/3 子问题 harness `passed=True`、total_cost=85 属实；但 **writer 第3章「模型假设」生成失败 → 整篇 `latex_code` 为空 → camera-ready zip 空壳（无 tex 无 PDF）**，"出论文"系注水。且 math_modeling preamble 用 cumcmthesis 但无 cls，**此前从未真出过 PDF**。两 bug 真因+修复详见 [[writer-no-pdf-ctexart-fix]]。
