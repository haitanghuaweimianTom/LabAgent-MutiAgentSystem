---
name: labagent-embedding-blocks-event-loop
description: LabAgent进程级"连不上LLM"真因——agent落到被墙的api.openai.com(provider缺凭证不回退)，非ARK并发差、非embedding阻塞
metadata:
  node_type: memory
  type: project
  originSessionId: 2f01771d-9090-4607-b9da-653497292e0b
  modified: 2026-07-26T05:28:40.206Z
---

LabAgent 后端用火山方舟(ARK)做 LLM 时，间歇性出现 `[anthropic] All connection attempts failed` / 空 `ConnectTimeout('')`，e2e 任务卡死。**之前一度归因于 embedding 同步阻塞 event loop（commit 830d8499），但 2026-07-26 用 repr 日志（adapters/base.py `_handle_exception` 记 type/repr/host）查明真正根因**：

`make_agent`(tasks.py) 把 `settings.api_base_url`(默认 `https://api.openai.com/v1`，国内被墙)透传给所有 agent。当 agent 被分配到**缺凭证的 provider**(如 MiniMax 未填 api_key)时，`base.py:_resolve_provider_config` 仅告警 bail(line 274)而**不回退默认 provider**，api_base_url 停在被墙的 api.openai.com → connect 8s 超时 → 空 ConnectTimeout。analyzer/research/data/writer 全中（它们 cfg 里是 MiniMax）；modeler/solver 因解析到 ARK 正常。**现象极具迷惑性**：新进程秒连 ARK(0.17s)，后端进程"整进程连不上"(连 SYN 都不发，ss 看不到到 ARK 的连接)，像进程级网络损坏。

**Why:** 空 str 的 ConnectTimeout 是黑盒（httpx ConnectTimeout 的 `__str__` 为空），不记 host 看不出是连 api.openai.com 还是连 ARK。必须 repr+host 一起记。

**How to apply:** 排查"间歇性/进程级连接失败"：(1)给 adapter 的 `_handle_exception` 加 `type(exc).__name__`+`repr(exc)`+`host` 日志，先看清连的是哪个 host；(2)区分 API 问题(新进程也连不上)vs 客户端配置问题(新进程秒连、后端连不上→多半是 agent 落到了被墙/占位 endpoint)；(3)占位符凭证(`your_api_key_here`/`api.openai.com`)是 truthy 字符串，`if not api_key` 判断会漏，必须显式识别占位符集；(4)指定 provider 缺凭证时必须回退默认 provider，别留在占位地址。修复见 commit edf629c0（base.py 占位符识别+provider 回退 + adapters 显式 connect=8s + reference_verifier per-ref cap + executor 扩容 64 + repr 诊断）。embedding 的 to_thread/CPU 化(830d8499)作为补充加固保留，但它**不是**连接失败的根因。Bug Finder(serve_bug_finder.py, GPU占3G+)不能杀，参见 [[no-inflated-resume-numbers]]。
