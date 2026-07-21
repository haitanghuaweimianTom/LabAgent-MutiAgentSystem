# Human-in-the-Loop 设计文档

> **版本：** v1.1
> **日期：** 2026-07-07
> **状态：** 待实现
> **核心理念：** 无人值守时系统自主想办法完成任务；用户输入时考虑新指令并调整行为

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
| **自主完成** | 无人值守时，系统自主想办法完成任务 — 遇到问题自动重试、换方案、调整策略 |
| **用户重定向** | 用户随时输入新指令，系统读取后调整后续行为（不一定是暂停，而是"转向"） |
| **实时观察** | Agent 输出实时显示在聊天框（已有 SSE 基础） |
| **弹性执行** | 失败时自主探索替代方案，而非简单重试或报错放弃 |

---

## 三、架构设计

### 核心理念

**无人值守 ≠ 简单自动继续。** 无人值守意味着系统具备自主决策能力：
- 遇到错误 → 分析原因 → 尝试替代方案
- 数据不足 → 自动搜集 → 调整建模策略
- LLM 调用失败 → 重试 → 换模型 → 使用模板兜底
- 某个 Agent 失败 → 跳过 → 用其他 Agent 的输出继续

**用户输入 ≠ 暂停。** 用户输入是"重定向信号"：
- 用户说"用 LSTM" → 下一个 Agent 读取并采用 LSTM 方案
- 用户说"跳过实验" → 跳过 experiment 节点，直接进入 writer
- 用户说"这个方向不对" → 重新分析，调整研究方向

### 3.1 数据流

```
用户输入消息
    ↓
ChatRoom.add_message(role="user", content=...)  ← 前端聊天框
    ↓
LangGraph 节点完成后检查 ChatRoom
    ├── 有新用户消息 → 读取，注入 context，通知 Agent
    └── 无新消息 → 正常继续
    ↓
Agent.execute(context) 中读取 context["user_feedback"]
    ├── 有反馈 → 在 prompt 中加入"用户要求调整"，修正行为
    └── 无反馈 → 自主决策，尝试最佳方案
    ↓
如果某步骤失败 → 自动降级/重试/换方案（弹性执行）
```

### 3.2 核心组件

#### A. TaskState 扩展

```python
class TaskState(TypedDict):
    # ... 现有字段 ...
    user_messages: List[Dict]  # 用户在执行期间输入的消息
    last_input_check: float    # 上次检查用户消息的时间戳
```

#### B. ChatRoom 增强

```python
class ChatRoom:
    def get_unread_messages(self, since_timestamp: float) -> List[Dict]:
        """获取指定时间戳之后的用户消息"""
        ...

    def mark_all_read(self):
        """标记所有消息为已读"""
        ...
```

#### C. LangGraph 节点间检查

```python
async def _check_user_input(self, state: TaskState) -> TaskState:
    """每个节点完成后调用 — 检查用户输入并注入"""
    task_id = state["task_id"]
    room = get_chat_room(task_id)
    if not room:
        return state

    user_msgs = room.get_unread_messages(state.get("last_input_check", 0))
    if not user_msgs:
        return state

    # 记录到 state
    all_msgs = state.get("user_messages", [])
    all_msgs.extend(user_msgs)

    # 通知用户已收到
    room.post("coordinator", f"📝 已收到用户反馈，正在调整...", "broadcast")

    return {
        **state,
        "user_messages": all_msgs,
        "last_input_check": time.time(),
    }
```

#### D. Agent 自主决策 + 用户反馈注入

```python
# BaseAgent.execute() 中
async def execute(self, task_input, context):
    # 读取用户反馈
    user_feedback = context.get("user_messages", [])
    feedback_section = ""
    if user_feedback:
        latest = user_feedback[-1]
        feedback_section = f"""

【用户最新指令】
{latest.get('content', '')}

请根据用户指令调整你的方案。如果用户指令与当前步骤无关，在输出中说明并继续原计划。
"""

    # 注入到 prompt
    prompt = f"{original_prompt}{feedback_section}"

    # ... 正常执行（含自主决策逻辑）...
```

#### E. 弹性执行（自主完成能力）

```python
# LangGraph orchestrator 中
async def _run_with_fallback(self, state, agent_name, fallback_fn):
    """执行 Agent，失败时自动降级"""
    try:
        return await self._run_agent(state, agent_name)
    except Exception as e:
        logger.warning(f"[{agent_name}] 失败: {e}，尝试降级方案")
        return await fallback_fn(state, e)
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

### 场景 1：无人值守 — 自主完成（默认）

```
用户提交任务："小资金期货量化投资策略"
    ↓
系统自主执行：
  Analyzer → 分解为 3 个子问题
  Data → 自动搜集数据（arXiv + 自有数据）
  Research → 文献调研
  Modeler → 选择金融分析模型
  Solver → 生成代码 → 执行失败 → 自动修复 → 重试 → 成功
  Writer → 生成论文
  PeerReview → 自评 → 自动修改 → 通过
    ↓
全程无用户干预，系统自主解决所有问题
```

### 场景 2：用户中途输入 — 重定向

```
系统正在执行 ModelerAgent（建模中）
    ↓
用户在聊天框输入："改用蒙特卡洛模拟，不要用线性规划"
    ↓
ModelerAgent 当前步骤完成 → 检查到用户消息
    ↓
读取用户指令 → "蒙特卡洛模拟"
    ↓
ModelerAgent 重新建模（使用蒙特卡洛方法）
    ↓
后续 Solver/Writer 自动适配新方案
```

### 场景 3：用户补充信息

```
系统正在执行 DataAgent（数据分析中）
    ↓
用户输入："我有一份 Excel 数据在桌面上，文件名是 strategy_data.xlsx"
    ↓
DataAgent 读取 → 发现新数据源
    ↓
调整分析策略 → 读取 Excel → 重新分析
```

### 场景 4：用户纠正方向

```
系统正在执行 WriterAgent（写论文中）
    ↓
用户输入："不要写综述，要写方法论章节，重点讲模型设计"
    ↓
WriterAgent 读取 → 调整写作重点
    ↓
重新生成方法论章节（而非综述）
```

### 场景 5：弹性执行 — 自动降级

```
SolverAgent 生成代码 → 执行失败（ModuleNotFoundError）
    ↓
自动修复：检测到缺少 numpy → 生成 pip install 代码 → 重新执行
    ↓
仍然失败 → 尝试替代算法（不依赖 numpy 的版本）
    ↓
成功 → 继续后续流程
```

---

## 五、关键节点行为

| 节点 | 无用户输入时 | 有用户输入时 |
|------|------------|------------|
| `preflight_decision` | 自主决策模板/工作流 | 采用用户指定的模板/工作流 |
| `analyzer` | 自主分解子问题 | 根据用户反馈调整子问题拆分 |
| `modeler/algorithm_engineer` | 自主选择建模方法 | 采用用户指定的方法 |
| `solver` | 自主编码+自动修复 | 采用用户指定的算法/框架 |
| `writer` | 自主生成论文 | 调整写作重点/风格/章节 |
| `peer_review` | 自评+自动修改 | 根据用户意见修改 |

---

## 六、实现步骤

### Phase 1: 基础设施（1-2 天）
1. TaskState 增加 `user_messages`、`last_input_check` 字段
2. ChatRoom 增加 `get_unread_messages()`、`mark_all_read()` 方法
3. LangGraph 节点间增加 `_check_user_input()` 中间检查

### Phase 2: Agent 反馈注入（1-2 天）
4. BaseAgent.execute() 注入 user_messages 到 context
5. 各 Agent 的 prompt 模板增加"用户最新指令"段落
6. Agent 输出中增加"已读取用户反馈"状态提示

### Phase 3: 弹性执行（2-3 天）
7. 实现 `_run_with_fallback()` — Agent 失败时自动降级
8. SolverAgent 增加自动修复循环（检测缺失依赖 → 安装 → 重试）
9. 各节点增加错误恢复逻辑（跳过/降级/换方案）

### Phase 4: 前端 UI（1-2 天）
10. 任务详情页增加聊天输入框（增强现有组件）
11. 消息气泡区分：用户消息 / Agent 输出 / 系统通知
12. 实时显示 Agent 决策过程（"正在尝试方案 A..."）

### Phase 5: 测试（1 天）
13. 单元测试：ChatRoom 未读消息检测
14. 集成测试：用户输入 → Agent 响应
15. 端到端测试：无人值守自主完成 + 用户中途重定向

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
