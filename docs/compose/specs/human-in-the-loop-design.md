# Human-in-the-Loop 设计文档

> **版本：** v1.0 Draft
> **日期：** 2026-07-07
> **状态：** 待实现

---

## 一、现状分析

### 当前架构

```
用户提交任务 → Preflight → Analyzer → Data/Research → Modeler → Solver → Writer → PeerReview → END
                                                                          ↑
                                                          wait_user 节点（v7.2 改为全自动，不暂停）
```

### 问题

1. **`wait_user` 节点被跳过** — v7.2 改为 `should_pause=False`，直接继续
2. **用户输入不被读取** — 聊天框输入的消息只存入 ChatRoom，Agent 执行时不检查
3. **无暂停机制** — 无法在关键步骤暂停等待用户确认
4. **无无人值守开关** — 所有任务都自动跑完，用户无法控制

---

## 二、设计目标

| 目标 | 描述 |
|------|------|
| **无人值守开关** | 用户可随时切换"自动继续" vs "等待确认"模式 |
| **实时观察** | Agent 输出实时显示在聊天框（已有 SSE 基础） |
| **用户打断** | 用户随时输入，Agent 在下一步读取并响应 |
| **Agent 响应用户** | Agent 将用户输入纳入上下文，修正行为 |

---

## 三、架构设计

### 3.1 数据流

```
用户输入消息
    ↓
ChatRoom.add_message(role="user", content=...)  ← 前端聊天框
    ↓
LangGraph 节点完成后检查 ChatRoom.unread_count()
    ├── 有未读消息 + unattended=False → 暂停，设置 should_pause=True
    ├── 有未读消息 + unattended=True → 读取消息，注入 context，继续
    └── 无未读消息 → 正常继续
    ↓
Agent.execute(context) 中读取 context["user_feedback"]
    ↓
Agent 在 prompt 中纳入用户反馈 → 修正输出
```

### 3.2 核心组件

#### A. TaskState 扩展

```python
class TaskState(TypedDict):
    # ... 现有字段 ...
    unattended_mode: bool  # True=自动继续, False=关键步骤暂停
    user_messages: List[Dict]  # 用户在执行期间输入的消息
    pending_user_input: bool   # 是否有未处理的用户输入
```

#### B. ChatRoom 增强

```python
class ChatRoom:
    def add_message(self, role, content, msg_type="text"):
        """现有方法 — 保存消息"""
        ...

    def get_unread_messages(self, since_timestamp: float) -> List[Dict]:
        """获取指定时间戳之后的用户消息"""
        ...

    def mark_all_read(self):
        """标记所有消息为已读"""
        ...
```

#### C. LangGraph 节点检查

```python
async def _check_user_input(self, state: TaskState) -> TaskState:
    """每个节点完成后调用 — 检查用户输入"""
    task_id = state["task_id"]
    room = get_chat_room(task_id)

    if not room:
        return state

    # 获取上次检查后的新消息
    user_msgs = room.get_unread_messages(state.get("last_input_check", 0))

    if not user_msgs:
        return state

    # 记录用户消息到 state
    all_msgs = state.get("user_messages", [])
    all_msgs.extend(user_msgs)

    if state.get("unattended_mode", True):
        # 无人值守模式：读取但不暂停
        room.post("coordinator", f"📝 收到用户反馈: {user_msgs[-1]['content'][:50]}...", "broadcast")
        return {
            **state,
            "user_messages": all_msgs,
            "last_input_check": time.time(),
        }
    else:
        # 确认模式：暂停等待用户
        return {
            **state,
            "user_messages": all_msgs,
            "pending_user_input": True,
            "should_pause": True,
            "current_step": "等待用户输入",
        }
```

#### D. Agent 注入用户反馈

```python
# BaseAgent.execute() 中
async def execute(self, task_input, context):
    # 读取用户反馈
    user_feedback = context.get("user_messages", [])
    feedback_text = ""
    if user_feedback:
        latest = user_feedback[-1]
        feedback_text = f"\n\n【用户反馈】\n{latest.get('content', '')}"

    # 注入到 prompt
    prompt = f"{original_prompt}{feedback_text}"

    # ... 正常执行 ...
```

### 3.3 前端改动

#### A. 无人值守开关

```tsx
// 任务详情页
<button onClick={() => toggleUnattended(!unattended)}>
  {unattended ? '🤖 无人值守 (自动继续)' : '🧑 人工确认 (暂停等待)'}
</button>
```

#### B. 聊天输入框

```tsx
// 任务详情页底部
<div className="chat-input">
  <input
    value={message}
    onChange={e => setMessage(e.target.value)}
    onKeyDown={e => e.key === 'Enter' && sendMessage()}
    placeholder="输入消息与 Agent 交互..."
  />
  <button onClick={sendMessage}>发送</button>
</div>
```

#### C. 实时消息显示

已通过 SSE + ChatRoom 实现。用户消息和 Agent 输出都显示在聊天框中。

---

## 四、交互流程

### 场景 1：无人值守模式（默认）

```
用户提交任务 → 选择"无人值守" → 系统自动执行所有步骤
                                   ↓
                          Agent 输出实时显示在聊天框
                                   ↓
                          用户随时可以在聊天框输入反馈
                                   ↓
                          Agent 读取反馈 → 调整后续行为
```

### 场景 2：人工确认模式

```
用户提交任务 → 选择"人工确认" → 系统执行到关键步骤时暂停
                                   ↓
                          Analyzer 完成 → 暂停，显示子问题列表
                                   ↓
                          用户确认/编辑子问题 → 继续执行
                                   ↓
                          Modeler 完成 → 暂停，显示模型方案
                                   ↓
                          用户确认模型 → 继续执行
                                   ↓
                          Writer 完成 → 暂停，显示论文草稿
                                   ↓
                          用户审阅 → 修改或确认 → 最终输出
```

### 场景 3：执行中打断

```
系统正在执行 SolverAgent
    ↓
用户在聊天框输入："请用 LSTM 而不是线性回归"
    ↓
SolverAgent 当前步骤完成 → 检查到用户消息
    ↓
将用户反馈注入下一步 prompt
    ↓
SolverAgent 重新生成代码（使用 LSTM）
```

---

## 五、关键节点暂停点

| 节点 | 暂停条件 | 暂停时显示 |
|------|---------|-----------|
| `preflight_decision` | 始终暂停（Phase 1） | 子问题列表 + 数据情况 |
| `analyzer` → `parallel_analysis` | 始终暂停 | 分析结果摘要 |
| `modeler/algorithm_engineer` | unattended=False 时暂停 | 模型方案 |
| `peer_review` | 始终暂停 | 论文评分 + 修改建议 |
| `writer` | unattended=False 时暂停 | 论文草稿预览 |

---

## 六、实现步骤

### Phase 1: 基础设施
1. TaskState 增加 `unattended_mode`、`user_messages`、`pending_user_input` 字段
2. ChatRoom 增加 `get_unread_messages()`、`mark_all_read()` 方法
3. LangGraph 增加 `_check_user_input()` 中间检查节点

### Phase 2: 暂停/继续机制
4. `_node_wait_user` 重新实现：检查未读消息 + 设置 should_pause
5. `_route_after_analyzer` 等路由函数增加暂停判断
6. 前端任务详情页增加"恢复执行"按钮

### Phase 3: Agent 用户反馈注入
7. BaseAgent.execute() 注入 user_messages 到 context
8. 各 Agent 的 prompt 模板增加"用户反馈"段落
9. Agent 输出中显示"已收到用户反馈并调整"

### Phase 4: 前端 UI
10. 任务详情页增加无人值守开关
11. 聊天输入框（已有基础，需增强）
12. 消息气泡区分：用户消息 / Agent 输出 / 系统通知

### Phase 5: 测试
13. 单元测试：ChatRoom 未读消息检测
14. 集成测试：暂停→恢复流程
15. 端到端测试：用户输入→Agent 响应

---

## 七、与现有代码的映射

| 现有代码 | 改动 |
|---------|------|
| `langgraph_orchestrator.py` `_node_wait_user` | 重新实现：检查未读消息 |
| `langgraph_orchestrator.py` `_route_after_*` | 增加暂停判断 |
| `base.py` `execute()` | 注入 user_messages 到 context |
| `chat_room.py` | 增加 get_unread_messages / mark_all_read |
| `TaskState` | 增加 3 个字段 |
| 前端 `task/[id]/page.tsx` | 增加开关 + 输入框 |
| 前端 `AgentChat.tsx` | 增强消息显示 |

---

## 八、风险与缓解

| 风险 | 缓解 |
|------|------|
| 暂停后用户不操作导致任务永远挂起 | 加超时机制（默认 30 分钟无操作自动继续） |
| 用户输入被 Agent 忽略 | Agent prompt 明确要求"如有用户反馈必须响应" |
| 并发任务的 ChatRoom 混淆 | 每个 task_id 独立 ChatRoom（已实现） |
| 暂停/恢复状态丢失 | 通过 TaskState 持久化到磁盘（已有机制） |
