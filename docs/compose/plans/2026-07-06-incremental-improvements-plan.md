# 增量改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一前后端类型、聊天消息 SSE 化、清理重复代码，提升系统一致性

**Architecture:** 在现有系统上做增量改进，不改变核心架构。统一枚举定义，将轮询改为 SSE 流式，清理残留重复代码。

**Tech Stack:** Python/FastAPI, Next.js 14, Zustand, LangGraph, SSE (EventSource)

## Global Constraints

- 不改动后端核心 Agent 逻辑
- 不改动 LangGraph 工作流结构（20+ 节点保持不变）
- 不改动前端路由结构（15 routes 保持不变）
- 所有改进向后兼容
- 每个 Task 独立可验证

---

## Task 1: 统一 TaskStatus 枚举定义

**Covers:** [S2]

**Files:**
- Modify: `backend/app/core/task_persistence.py` — TaskStatus 枚举
- Modify: `frontend/src/lib/types.ts` — 前端 TaskStatus 类型

**Interfaces:**
- Produces: 统一的 TaskStatus 枚举，前后端一致

- [ ] **Step 1: 检查后端当前 TaskStatus 定义**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem && grep -n "class TaskStatus\|phase1\|phase2\|retrying" backend/app/core/task_persistence.py | head -20
```

- [ ] **Step 2: 检查前端当前 TaskStatus 定义**

```bash
grep -A 15 "TaskStatus" frontend/src/lib/types.ts
```

- [ ] **Step 3: 统一后端 TaskStatus 枚举**

确保 `backend/app/core/task_persistence.py` 包含所有状态值。如果缺少 `phase1`/`phase2`/`retrying`，添加它们。

- [ ] **Step 4: 更新前端 TaskStatus 类型**

确保 `frontend/src/lib/types.ts` 的 TaskStatus 与后端完全一致。

- [ ] **Step 5: 更新 useTaskState 状态映射**

检查 `frontend/src/app/hooks/useTaskState.ts`，确保所有后端状态值都有对应映射。

- [ ] **Step 6: 验证后端启动**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem/backend && python -c "from app.core.task_persistence import TaskStatus; print([s.value for s in TaskStatus])"
```

- [ ] **Step 7: 验证前端构建**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem/frontend && npx next build --no-lint 2>&1 | tail -10
```

- [ ] **Step 8: 提交**

```bash
git add backend/app/core/task_persistence.py frontend/src/lib/types.ts frontend/src/app/hooks/useTaskState.ts
git commit -m "unify TaskStatus enum between frontend and backend"
```

---

## Task 2: 统一 TEAM_COLORS 和 TEAM_LABELS 导入

**Covers:** [S5]

**Files:**
- Modify: `frontend/src/app/task/[id]/page.tsx` — 移除局部 getTeamLabel

**Interfaces:**
- Consumes: `TEAM_LABELS` from `@/lib/constants`

- [ ] **Step 1: 检查 task 页面中的重复定义**

```bash
grep -n "getTeamLabel\|TEAM_LABELS\|TEAM_COLORS" frontend/src/app/task/\[id\]/page.tsx
```

- [ ] **Step 2: 移除局部 getTeamLabel 函数**

如果 `task/[id]/page.tsx` 中有 `getTeamLabel` 函数定义（约 line 13-23），删除它并改为从 `@/lib/constants` 导入 `TEAM_LABELS`。

修改后应有：
```typescript
import { TEAM_LABELS } from '@/lib/constants'
```

并将所有 `getTeamLabel(sender)` 调用改为 `TEAM_LABELS[sender] || sender`。

- [ ] **Step 3: 全局搜索其他残留**

```bash
grep -rn "const apiBase = " frontend/src/ --include="*.tsx" --include="*.ts"
grep -rn "const TEAM_COLORS" frontend/src/ --include="*.tsx" --include="*.ts"
grep -rn "getTeamLabel" frontend/src/ --include="*.tsx" --include="*.ts"
```

- [ ] **Step 4: 验证构建**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem/frontend && npx next build --no-lint 2>&1 | tail -10
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/app/task/\[id\]/page.tsx
git commit -m "remove duplicate getTeamLabel, use shared TEAM_LABELS"
```

---

## Task 3: 后端 EventBus 添加 chat_message 事件

**Covers:** [S3]

**Files:**
- Modify: `backend/app/core/event_bus.py` — 添加 chat_message 事件

**Interfaces:**
- Produces: `broadcast_chat_message(task_id, sender, content, sender_label)`

- [ ] **Step 1: 检查当前 EventBus 实现**

```bash
grep -n "class TaskEventBus\|def broadcast\|chat_message" backend/app/core/event_bus.py | head -20
```

- [ ] **Step 2: 在 TaskEventBus 中添加 chat_message 广播方法**

在 `event_bus.py` 中找到 `TaskEventBus` 类，添加：

```python
async def broadcast_chat_message(
    self,
    task_id: str,
    sender: str,
    content: str,
    sender_label: str = "",
    msg_type: str = "text",
):
    """广播聊天消息事件（Agent 讨论/系统消息）"""
    await self.broadcast(task_id, {
        "type": "chat_message",
        "sender": sender,
        "sender_label": sender_label or sender,
        "content": content,
        "msg_type": msg_type,
        "timestamp": time.time(),
    })
```

- [ ] **Step 3: 在 Agent 发送消息时触发广播**

搜索后端中 Agent 写入消息的地方（如 `save_message` 或 `add_message`），在写入后调用 `broadcast_chat_message`。

```bash
grep -rn "save_message\|add_message\|_save_message" backend/app/ --include="*.py" | grep -v __pycache__ | head -10
```

- [ ] **Step 4: 验证后端启动**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem/backend && python -c "from app.core.event_bus import TaskEventBus; print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/event_bus.py
git commit -m "add chat_message event type to TaskEventBus"
```

---

## Task 4: 前端 AgentChat 改为 SSE 流式

**Covers:** [S3]

**Files:**
- Modify: `frontend/src/app/components/AgentChat.tsx` — 消费 SSE 替代轮询

**Interfaces:**
- Consumes: SSE 事件 `chat_message`（来自 Task 3）

- [ ] **Step 1: 检查当前轮询逻辑**

```bash
grep -n "setInterval\|poll\|fetch.*messages" frontend/src/app/components/AgentChat.tsx | head -10
```

- [ ] **Step 2: 修改 AgentChat 消费 SSE**

将 AgentChat 中的消息轮询改为监听 SSE 事件。找到消息加载的 `useEffect`，替换为：

```typescript
// 在组件中添加 SSE 消费
useEffect(() => {
  if (!taskId) return
  const es = new EventSource(apiBase() + '/tasks/' + taskId + '/stream')
  es.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data)
      if (d.type === 'chat_message') {
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          sender: d.sender,
          sender_label: d.sender_label,
          content: d.content,
          type: d.msg_type || 'text',
          timestamp: new Date(d.timestamp * 1000).toISOString(),
        }])
      }
    } catch {}
  }
  es.onerror = () => es.close()
  return () => es.close()
}, [taskId])
```

- [ ] **Step 3: 保留初始加载的轮询作为降级**

保留首次加载历史消息的 fetch 调用，只替换后续的增量轮询。

- [ ] **Step 4: 验证构建**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem/frontend && npx next build --no-lint 2>&1 | tail -10
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/app/components/AgentChat.tsx
git commit -m "migrate AgentChat from polling to SSE streaming"
```

---

## Task 5: 前端 DiscussionPanel 改为 SSE 流式

**Covers:** [S3]

**Files:**
- Modify: `frontend/src/app/components/DiscussionPanel.tsx` — 消费 SSE 替代轮询

**Interfaces:**
- Consumes: SSE 事件 `chat_message`（来自 Task 3）

- [ ] **Step 1: 检查当前轮询逻辑**

```bash
grep -n "setInterval\|poll\|fetch.*discussion" frontend/src/app/components/DiscussionPanel.tsx | head -10
```

- [ ] **Step 2: 修改 DiscussionPanel 消费 SSE**

与 Task 4 类似，将讨论消息的轮询改为 SSE 流式。

- [ ] **Step 3: 验证构建**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem/frontend && npx next build --no-lint 2>&1 | tail -10
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/app/components/DiscussionPanel.tsx
git commit -m "migrate DiscussionPanel from polling to SSE streaming"
```

---

## Task 6: 清理 useAppStore 残留 apiBase

**Covers:** [S5]

**Files:**
- Modify: `frontend/src/app/store/useAppStore.ts` — 确认无残留 apiBase

**Interfaces:**
- Consumes: `apiBase` from `@/lib/api`

- [ ] **Step 1: 检查 useAppStore 中的 apiBase 使用**

```bash
grep -n "apiBase\|__API_BASE__" frontend/src/app/store/useAppStore.ts
```

- [ ] **Step 2: 如果仍有局部定义，替换为导入**

确保 import 行有：
```typescript
import { apiBase } from '@/lib/api'
```

删除任何 `const apiBase = ...` 定义。

- [ ] **Step 3: 验证构建**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem/frontend && npx next build --no-lint 2>&1 | tail -10
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/app/store/useAppStore.ts
git commit -m "clean up residual apiBase in useAppStore"
```

---

## Summary

| Task | 描述 | 覆盖 |
|------|------|------|
| 1 | 统一 TaskStatus 枚举 | [S2] 类型对齐 |
| 2 | 清理重复 getTeamLabel | [S5] 重复代码 |
| 3 | EventBus chat_message 事件 | [S3] 聊天 SSE |
| 4 | AgentChat SSE 化 | [S3] 聊天 SSE |
| 5 | DiscussionPanel SSE 化 | [S3] 聊天 SSE |
| 6 | 清理 useAppStore apiBase | [S5] 重复代码 |

总计 6 个 Task，每个独立可验证。
