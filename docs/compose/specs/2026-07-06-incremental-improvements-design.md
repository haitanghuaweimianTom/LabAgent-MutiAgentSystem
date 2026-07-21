# 增量改进设计文档

基于工业界调研结果，对现有系统进行增量改进。不推倒重来，在现有架构上采纳最佳实践。

## [S1] 问题与目标

### 问题
1. **类型安全缺口**：前后端类型手动维护，TaskStatus 枚举值不一致（后端 `phase1`/`phase2`，前端自定义 14 状态）
2. **聊天消息轮询**：Agent 讨论面板用 1 秒轮询，浪费资源且延迟高
3. **Human-in-the-Loop**：暂停/恢复是自定义实现，LangGraph `interrupt()` 更简洁
4. **重复代码**：`apiBase`、`TEAM_COLORS` 等在多处重复定义（虽已部分清理，仍有残留）

### 目标
- 统一前后端类型，消除分歧
- 聊天消息改为 SSE 流式
- 在新任务中试点 LangGraph `interrupt()` HITL
- 清理残留重复代码

## [S2] 共享类型对齐

### 现状
- 后端：`backend/app/core/task_persistence.py` 中 TaskStatus 枚举
- 前端：`frontend/src/lib/types.ts` 中 TaskStatus 类型 + `useTaskState.ts` 中 14 状态映射
- 分歧：后端有 `phase1`/`phase2`/`retrying`，前端有自定义的 `phase1`/`phase2`/`retrying` 但映射逻辑不同

### 改进方案
1. 在 `backend/app/models/` 创建 `shared.py`，定义前后端共用的枚举（Pydantic 模型）
2. 在 `frontend/src/lib/types.ts` 中与后端枚举保持一致
3. 更新 `useTaskState.ts` 的状态映射，确保与后端对齐

### 关键文件
- `backend/app/core/task_persistence.py` — TaskStatus 定义
- `frontend/src/lib/types.ts` — 前端类型
- `frontend/src/app/hooks/useTaskState.ts` — 状态映射

## [S3] 聊天消息 SSE 化

### 现状
- `DiscussionPanel.tsx` 每 1 秒轮询 `/tasks/{id}/discussion/messages`
- `AgentChat.tsx` 每 1 秒轮询 `/tasks/{id}/messages`
- 后端已有 `TaskEventBus` 和 SSE 端点 `/tasks/{id}/stream`

### 改进方案
1. 后端：在 `TaskEventBus` 中添加 `chat_message` 事件类型
2. 后端：当 Agent 发送消息时，通过 EventBus 广播
3. 前端：`DiscussionPanel` 和 `AgentChat` 改为消费 SSE 流，去掉轮询
4. 保留轮询作为降级方案（SSE 断开时自动回退）

### 关键文件
- `backend/app/core/event_bus.py` — EventBus 事件类型
- `backend/app/routers/tasks.py` — SSE 端点
- `frontend/src/app/components/DiscussionPanel.tsx` — 讨论面板
- `frontend/src/app/components/AgentChat.tsx` — Agent 聊天

## [S4] Human-in-the-Loop 试点

### 现状
- `handlePause` / `handleResume` / `handleCancel` 自定义实现
- 暂停时保存状态到 checkpoint，恢复时加载

### 改进方案
1. 在新的简单任务流中试点 LangGraph `interrupt()`
2. 保留现有暂停/恢复机制作为主流程（已验证稳定）
3. `interrupt()` 用于低置信度结果的人工审核场景

### 关键文件
- `backend/app/agents/langgraph_orchestrator.py` — 工作流编排
- `backend/app/core/event_bus.py` — 事件广播

## [S5] 重复代码清理

### 残留问题
- `useAppStore.ts` 中可能仍有局部 apiBase 定义
- `getTeamLabel()` 函数在 task 页面中重复定义（应从 `@/lib/constants` 导入 TEAM_LABELS）
- 前端 `page.tsx` 中的 `TabType` 已删除但可能有其他引用

### 改进方案
1. 全局搜索 `const apiBase` 确认无残留
2. 将 `getTeamLabel` 逻辑统一到 `@/lib/constants` 的 `TEAM_LABELS`
3. 确认无其他重复定义

## [S6] 约束

- 不改动后端核心 Agent 逻辑
- 不改动 LangGraph 工作流结构
- 不改动前端路由结构
- 所有改进向后兼容
- 每个改进独立可验证
