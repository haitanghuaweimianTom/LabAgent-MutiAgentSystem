---
name: writer-no-pdf-ctexart-fix
description: writer单章失败致整篇latex为空+math_modeling用cumcmthesis无cls从未出PDF;本次会话修writer容错+换ctexart preamble(2026-07-27)
metadata:
  type: project
  modified: 2026-07-27
---

# writer 出空壳 zip / 从未出过 PDF — 两 bug 真因 + 修复（2026-07-27）

用户反馈「要 tex 也要 pdf，没看到 pdf」。排查 `task_5a92bcfea314` 发现两个独立 bug 叠加，导致**此前所有 math_modeling 论文从未真正生成 PDF**（zip 只有代码壳，无 tex 无 pdf）。

## bug1：writer 单章失败 raise → 整篇 latex 为空（核心，治本）
- `_generate_chapter`（writer_agent.py ~1492）3 次重试 LLM 返回无效内容（空 / ≤50 字 / 含"内容待补充"）后 `raise RuntimeError`（line 1524）。
- 章节循环（~1074）无 try/except 包裹 → 单章 raise 中断整个 for → `_assemble_paper` 不执行 → `latex_code=""`。
- `_node_writer`（langgraph_orchestrator.py ~8542）catch 后只用错误标记覆盖 output，latex 仍空。
- camera_ready 兜底读 `writer_agent.latex_code` 拿空串 → 跳过 → zip 无 main.tex。
- **讽刺**：`_chapter_fallback`（~2403，返回带 `% [DEGRADED]` 标记的可编译占位 LaTeX）早已写好却**从未被调用**（死代码）。
- **修**：raise 改 `return (self._chapter_fallback(plan, template), fallback_summary)`。单章失败不再致命，整篇仍可组装编译。新增单测 `test_generate_chapter_fallback_on_invalid_content` 验证。

## bug2：math_modeling preamble 用 cumcmthesis 但无 cls（配置矛盾）
- 注册表 `cumcm.json`（id=math_modeling）：preamble `\documentclass[withoutpreface]{cumcmthesis}` + 一堆 cumcmthesis 专有命令（\tihao \baominghao \schoolname \membera/b/c \supervisor \yearinput ...），但 `cls_file` 指向 `mcmthesis.cls`。
- `kpsewhich cumcmthesis.cls` = 无；仓库 find 也无。`mcmthesis.cls` 是不同类（\ProvidesClass{mcmthesis}），不支持 cumcmthesis 命令，且缺 berasans.sty。
- 即便 writer 产出 tex，xelatex 也找不到 cumcmthesis.cls → 编译失败 → 无 PDF。
- **修**（用户选 ctexart）：preamble 换 `\documentclass{ctexart}` + `__TITLE__`/`__AUTHORS__` 占位符（让 writer 填）；documentclass→ctexart；cls_file→空（ctexart 系统自带，零依赖）。改 `cumcm.json` + writer_agent.py `_cumcm_preamble` fallback 两处。

## 验证
- bug1 单测通过；bug2 mock 端到端：全降级章节 + ctexart preamble → xelatex 编出 ~100KB PDF。
- 回归：WriterAgent + `test_readme_uses_cumcm_for_math_modeling`（断言 cumcmthesis→ctexart）通过。
- Modeler/Solver 3 个预存失败（stash 原状代码也失败，**非本次引入**，不在范围内）。

## 关键文件
- writer_agent.py：`_generate_chapter`（raise→return fallback）、`_cumcm_preamble`（cumcmthesis→ctexart）
- cumcm.json：preamble / documentclass / cls_file 三字段
- test_agents_unit.py::TestWriterAgent::test_generate_chapter_fallback_on_invalid_content（新增）
- test_camera_ready.py::test_readme_uses_cumcm_for_math_modeling（断言改 ctexart）

## 待办
- 真实重跑 task_5a92bcfea314（需重启 8200 后端加载新代码）确认端到端出 PDF（当前仅 mock 验证）。
- xelatex rc=1（warning，PDF 仍生成）— 可后续看 main.log 细化，不阻断出 PDF。

**Why:** 之前 coordinator 消息「论文写作完成（第3稿）」「交付文件夹已生成（含论文）」+ 记忆「端到端出论文」误导，实际 writer 降级、zip 空壳、无 PDF。两个 bug 叠加：单看 camera_ready 报 `main.tex not found` 会误以为是打包问题，实则是上游 writer 全空 + preamble 缺 cls。

**How to apply:** 排查「没看到 PDF」先看 `backend/data/tasks/task_*_result.json` 的 `output.writer_agent.latex_code` 是否为空（writer 是否降级）+ camera_ready `metadata.skipped_reasons`/`verification`；latex 非空再看 xelatex 是否因 cls 缺失失败（`kpsewhich <class>.cls`）。相关：[[labagent-mcp-connection-closed-root-cause]]、[[labagent-memory-pool-architecture]]、[[no-inflated-resume-numbers]]。
