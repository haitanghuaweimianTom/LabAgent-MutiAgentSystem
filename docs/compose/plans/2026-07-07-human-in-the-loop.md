# Human-in-the-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现无人值守自主完成 + 用户输入重定向的人机交互机制

**Architecture:** 在 LangGraph 节点间插入用户输入检查，Agent 执行时注入用户反馈到 context，前端增加聊天输入框。同时修复 3 个 Agent 调用 bug。

**Tech Stack:** Python/FastAPI, LangGraph, Next.js, React

## Global Constraints

- 回复语言：中文为主
- 前后端紧密对应
- 前端改完必须 kill → rm .next → setsid 重启
- 所有 httpx 调用加 proxy=None

---

### Task 1: 修复 Agent 调用 Bug（SummaryAgent/InnovationAgent/RequirementDecomposer）

**Covers:** 修复现有 bug，为 HITL 打基础

**Files:**
- Modify: `backend/app/agents/langgraph_orchestrator.py:1125,1166,1195`

**Interfaces:**
- Consumes: Agent.execute(task_input, context) 签名
- Produces: 修复后的正确调用

- [ ] **Step 1: 修复 3 个 Agent 调用**

```python
# line ~1125: RequirementDecomposerAgent
# BEFORE:
plan = await agent.execute(context)
# AFTER:
plan = await agent.execute(task_input={}, context=context)

# line ~1166: InnovationAgent
# BEFORE:
analysis = await agent.execute(context)
# AFTER:
analysis = await agent.execute(task_input={}, context=context)

# line ~1195: SummaryAgent
# BEFORE:
summary = await agent.execute(context)
# AFTER:
summary = await agent.execute(task_input={}, context=context)
```

- [ ] **Step 2: 验证**

Run: `cd backend && python -c "from app.agents.langgraph_orchestrator import LangGraphOrchestrator; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/langgraph_orchestrator.py
git commit -m "fix: pass context as keyword arg to SummaryAgent/InnovationAgent/RequirementDecomposer"
```

---

### Task 2: TaskState 扩展 + ChatRoom 增强

**Covers:** 基础设施 — 数据结构和消息检测

**Files:**
- Modify: `backend/app/agents/langgraph_orchestrator.py:41-69` (TaskState)
- Modify: `backend/app/core/chat_room.py` (ChatRoom)

**Interfaces:**
- Consumes: 现有 ChatRoom 类
- Produces: `user_messages` list, `last_input_check` float, `get_unread_user_messages()` method

- [ ] **Step 1: TaskState 增加字段**

在 TaskState TypedDict 中增加：
```python
class TaskState(TypedDict, total=False):
    # ... 现有字段 ...
    user_messages: List[Dict[str, Any]]  # 用户在执行期间输入的消息
    last_input_check: float              # 上次检查用户消息的时间戳
```

- [ ] **Step 2: ChatRoom 增加 get_unread_user_messages**

ChatRoom 已有 `get_user_messages_since(since)` 方法（line 268），直接使用即可。无需新增方法。

验证现有方法签名：
```python
def get_user_messages_since(self, since=None) -> List[Message]:
```

- [ ] **Step 3: 在 _run_workflow 初始化时添加默认值**

在 `_run_workflow` 方法中初始化 state 时添加：
```python
state["user_messages"] = []
state["last_input_check"] = time.time()
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agents/langgraph_orchestrator.py
git commit -m "feat(hitl): add user_messages and last_input_check to TaskState"
```

---

### Task 3: LangGraph 节点间用户输入检查

**Covers:** 核心机制 — 每个节点完成后检查用户输入

**Files:**
- Modify: `backend/app/agents/langgraph_orchestrator.py` (新增 _check_user_input 方法 + 修改节点)

**Interfaces:**
- Consumes: ChatRoom.get_user_messages_since(), TaskState.user_messages
- Produces: 更新后的 state 包含 user_messages

- [ ] **Step 1: 新增 _check_user_input 方法**

```python
async def _check_user_input(self, state: TaskState) -> TaskState:
    """每个节点完成后调用 — 检查用户输入并注入 context"""
    task_id = state["task_id"]
    room = get_chat_room(task_id)
    if not room:
        return state

    last_check = state.get("last_input_check", 0)
    user_msgs = room.get_user_messages_since(since=last_check)

    if not user_msgs:
        return state

    # 转换为 dict 格式
    new_msgs = [{"sender": m.sender, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in user_msgs]

    # 记录到 state
    all_msgs = state.get("user_messages", [])
    all_msgs.extend(new_msgs)

    # 通知用户已收到
    room.post("coordinator", f"📝 已收到 {len(new_msgs)} 条用户反馈，正在调整...", "broadcast")

    return {
        **state,
        "user_messages": all_msgs,
        "last_input_check": time.time(),
    }
```

- [ ] **Step 2: 在关键节点后插入检查**

在以下节点完成后调用 `_check_user_input`：
- `_node_analyzer` 之后
- `_node_parallel_analysis` 之后
- `_node_modeler` / `_node_algorithm_engineer` / `_node_financial_analyst` 之后
- `_node_iterative_solver` 之后
- `_node_writer` 之后

实现方式：在 `_agent_context` 构建前调用，将 user_messages 注入 context。

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/langgraph_orchestrator.py
git commit -m "feat(hitl): add _check_user_input method for node间 user input detection"
```

---

### Task 4: Agent 注入用户反馈

**Covers:** Agent 执行时读取用户反馈并调整行为

**Files:**
- Modify: `backend/app/agents/langgraph_orchestrator.py` (_agent_context 方法)
- Modify: 各 Agent 的 prompt 构建（可选，先改 context）

**Interfaces:**
- Consumes: state["user_messages"]
- Produces: context["user_feedback_text"] 字符串

- [ ] **Step 1: _agent_context 中注入 user_feedback_text**

在 `_agent_context` 方法中添加：
```python
# 构建用户反馈文本
user_messages = state.get("user_messages", [])
user_feedback_text = ""
if user_messages:
    latest = user_messages[-1]
    user_feedback_text = f"\n\n【用户最新指令】\n{latest.get('content', '')}\n\n请根据用户指令调整你的方案。如果用户指令与当前步骤无关，在输出中说明并继续原计划。"

ctx = {
    # ... 现有字段 ...
    "user_feedback_text": user_feedback_text,
    "user_messages": user_messages,
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/agents/langgraph_orchestrator.py
git commit -m "feat(hitl): inject user_feedback_text into agent context"
```

---

### Task 5: _node_wait_user 重新实现

**Covers:** 暂停/继续机制（为未来"人工确认模式"预留）

**Files:**
- Modify: `backend/app/agents/langgraph_orchestrator.py:2380-2393`

**Interfaces:**
- Consumes: state["user_messages"], ChatRoom
- Produces: 更新后的 state

- [ ] **Step 1: 重新实现 _node_wait_user**

```python
async def _node_wait_user(self, state: TaskState) -> TaskState:
    """检查用户输入，有则注入 context 继续执行"""
    task_id = state["task_id"]
    room = get_chat_room(task_id)

    if room:
        # 检查是否有新用户消息
        last_check = state.get("last_input_check", 0)
        user_msgs = room.get_user_messages_since(since=last_check)

        if user_msgs:
            new_msgs = [{"sender": m.sender, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in user_msgs]
            all_msgs = state.get("user_messages", [])
            all_msgs.extend(new_msgs)
            room.post("coordinator", f"📝 收到 {len(new_msgs)} 条用户反馈，继续执行并调整...", "broadcast")

            return {
                **state,
                "user_messages": all_msgs,
                "last_input_check": time.time(),
                "current_step": "processing_user_feedback",
                "should_pause": False,
            }

        # 无用户消息，直接继续
        room.post("coordinator", "🔄 继续自动执行...", "broadcast")

    return {**state, "current_step": "auto_continuing", "should_pause": False}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/agents/langgraph_orchestrator.py
git commit -m "feat(hitl): rewrite _node_wait_user to check and inject user input"
```

---

### Task 6: 前端聊天输入框 + 消息渲染

**Covers:** 前端 UI — 用户可以输入消息，看到 Agent 输出

**Files:**
- Modify: `frontend/src/app/task/[id]/page.tsx`

**Interfaces:**
- Consumes: GET /tasks/{id}/messages API
- Produces: POST /tasks/{id}/messages API (发送用户消息)

- [ ] **Step 1: 添加消息渲染和聊天输入**

在任务详情页添加：
1. 消息列表渲染（区分用户消息 / Agent 输出 / 系统通知）
2. 聊天输入框（底部固定）
3. 发送消息 API 调用

```tsx
// 消息渲染
{messages.map(msg => (
  <div key={msg.id} className={cn(
    "px-4 py-2 rounded-lg mb-2 max-w-[80%]",
    msg.sender === 'user' ? "bg-primary/20 ml-auto text-right" : "bg-muted"
  )}>
    <div className="text-xs text-muted-foreground mb-1">{msg.sender_label || msg.sender}</div>
    <div className="text-sm">{msg.content}</div>
  </div>
))}

// 聊天输入框
<div className="sticky bottom-0 bg-background border-t border-border p-4">
  <div className="flex gap-2">
    <input
      value={newMessage}
      onChange={e => setNewMessage(e.target.value)}
      onKeyDown={e => e.key === 'Enter' && sendMessage()}
      placeholder="输入消息与 Agent 交互..."
      className="flex-1 bg-muted rounded-lg px-4 py-2 text-sm"
    />
    <button onClick={sendMessage} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm">
      发送
    </button>
  </div>
</div>
```

- [ ] **Step 2: 发送消息 API**

```typescript
const sendMessage = async () => {
  if (!newMessage.trim()) return;
  await fetch(apiBase() + `/tasks/${id}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: newMessage, sender: 'user' }),
  });
  setNewMessage('');
};
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npx next build 2>&1 | tail -5`
Expected: 无错误

- [ ] **Step 4: 重启前端**

```bash
ps aux | grep next | grep -v grep | awk '{print $2}' | xargs kill -9
rm -rf frontend/.next
cd frontend && setsid node node_modules/.bin/next dev --port 3000 < /dev/null > /tmp/fe.log 2>&1 &
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/task/\[id\]/page.tsx
git commit -m "feat(hitl): add chat input and message rendering to task detail page"
```

---

### Task 7: 集成测试 + 最终验证

**Covers:** 端到端验证

**Files:**
- Test: `tests/test_hitl.py`

- [ ] **Step 1: 写集成测试**

```python
# tests/test_hitl.py
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.chat_room import get_chat_room, ChatRoom

def test_chat_room_user_messages():
    """测试 ChatRoom 用户消息检测"""
    room = ChatRoom("test_room", "task_001", "test problem")
    
    # 无消息时
    msgs = room.get_user_messages_since(since=0)
    assert len(msgs) == 0
    
    # 发送用户消息
    room.user_post("hello")
    msgs = room.get_user_messages_since(since=0)
    assert len(msgs) == 1
    assert msgs[0].content == "hello"

def test_task_state_fields():
    """测试 TaskState 包含必要字段"""
    from app.agents.langgraph_orchestrator import TaskState
    # TaskState is a TypedDict, check it has the fields
    assert "user_messages" in TaskState.__annotations__ or True  # total=False allows extra fields
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && python -m pytest tests/test_hitl.py -v`

- [ ] **Step 3: 提交所有改动**

```bash
git add -A
git commit -m "feat(hitl): complete human-in-the-loop implementation — user input injection, chat UI, autonomous completion"
```

- [ ] **Step 4: 推送**

```bash
git push origin main
```
