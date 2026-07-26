---
name: labagent-memory-pool-architecture
description: LabAgent记忆池两套系统+接入要点；_get_working_memory曾调不存在方法致共享黑板全死代码（已修）；Lessons闭环2026-07-26修好
metadata: 
  node_type: memory
  type: project
  modified: 2026-07-26T07:20:57.302Z
  originSessionId: 2f01771d-9090-4607-b9da-653497292e0b
---

LabAgent 有**两套并行、互不打通的记忆系统**：

1. **MemoryManager**（`app/core/memory.py`）——任务级共享记忆，三层：WorkingMemory（黑板，分区 problem/literature/methods/results/...，`set_result`/`add_literature` 写入，`get_context_for_agent` 按角色读取）、EpisodicMemory（事件日志）、LessonsMemory（跨任务经验，`data/memory/lessons.json`）。LangGraph 在 `run()` 里 `create_task_memory(task_id)` 创建；正确取黑板方法是 `mm.get_working(task_id)`（不是 get_task_memory）。
2. **AgentProfileMemory**（`app/core/agent_memory.py`）——每个 Agent 个人长期记忆（work_style/preferences/skills/cases），存 `data/memory/agents/{name}.json` + `{name}_cases.jsonl`。BaseAgent `__init__` 自动 `get_agent_profile(self.name)` 加载，`call_llm` 自动作为 system prompt 注入；`_evolve_agent_profiles`（任务结束）回写 7 个 agent 案例。

**接入记忆的关键模式**（排查"agent 没记忆"时查这些）：
- Agent 读黑板：必须经 `call_llm(messages, context=context)` 且 **context 含 `working_memory` 键**（`_agent_context` 注入）。`_call_llm_once` 是底层裸调，**绕过全部记忆/profile/KB 注入**——投票、临时调用别用 `_call_llm_once`，要用 `call_llm` + context。
- Agent 写黑板：orchestrator 节点层在 agent.execute 返回后显式 `wm.set_result(agent_name, output)` / `wm.add_literature`。**不是基类自动做**。
- `try/except: return None` 吞掉不存在的方法调用是个隐蔽 bug 模式：`_get_working_memory` 曾调 `mm.get_task_memory(task_id)`（MemoryManager 无此方法，正确是 `get_working`），被 except 吞 → 返回 None → 12 处 `wm.set_result/add_*` 全死代码、共享黑板形同虚设。已修（commit f85ae499）。

**新增 Agent 接入清单**（routers/tasks.py `make_agent` 注册到 self.agents + `_evolve_agent_profiles` evolution_map 回写 + execute 传 context）：
- voter agents：`_get_voter_agent` 从 self.agents 取；`_voter_discuss`/`_voter_vote` 已改走 `call_llm(context=voter_context)`（含 working_memory+problem_type），接入记忆。
- peer_review_agent：已注册到 self.agents + `_call_llm_review` 传 context。
- coordinator：不是 BaseAgent 子类（`core/coordinator.py` 是工作流辅助类），voter 里 fallback analyzer。
- financial_analyst / algorithm_engineer：正常接入（profile+Lessons 读 OK，在 evolution_map）。

KB 注入（`_inject_knowledge_context`）已 opt-in（`use_global_kb` flag 默认 False），call_llm 默认不遍历 59 个 KB，安全。参见 [[labagent-embedding-blocks-event-loop]]。

**Lessons 闭环（2026-07-26 commit dee7a597 修好，之前断在三处）**：
1. 注入不自增：`base.py:_inject_memory_context` 原调 `get_context_text(problem_type=...)`→`query`（不增 use_count、仅 problem_type 精确匹配）。改为传 `problem_text`→`get_context_text` 走 `retrieve_relevant`（关键词兜底匹配 + use_count 自增 + save）→"越用越准"闭环真正转起来。
2. problem_type 漏注入：`_agent_context` 原仅 `research_survey` 模板设 `ctx["problem_type"]`，`math_modeling` 等不设→lessons 注入拿到空 problem_type。改为全模板在基础 ctx 注入 `problem_type`。
3. 失败经验不提取：`extract_lessons_from_result` 原只记 `success=True`。现补 `success=False`：solver 降级 HTTP（`_degraded_by=="http_api_coder_fallback"`）、`_quality_report.degraded_items`、`cannot_solve_report`。新增 `failure` 分类。
4. solver 没记忆：`solver_agent._solve_single/_solve_sequential/_solve_all` 原 `call_llm(messages)` 不传 context→无 lessons/黑板。现传 `context=context`（solver 节点已传 `**_agent_context(state)`）。`_run_code_with_autofix` 内的 call_llm 不在改造范围（该方法签名无 context）。
验证：use_count [0,0]→[1,1] 闭环 + 失败经验提取均通过。
