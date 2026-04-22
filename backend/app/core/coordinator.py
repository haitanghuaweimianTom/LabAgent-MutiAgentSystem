"""
协调者 (Coordinator) - 核心模块
像真正的项目经理一样管理团队：制定计划、分配任务、追踪进度
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from ..schemas import TaskStatus
from .chat_room import ChatRoom, get_chat_room

logger = logging.getLogger(__name__)


class Coordinator:
    """
    协调者 - 团队领导

    职责：
    1. 分析问题，制定工作计划
    2. 分配任务给各专业Agent
    3. 追踪进度，更新聊天室
    4. 处理异常，协调解决
    """

    name: str = "coordinator"
    label: str = "协调者"

    # 团队成员及其角色
    TEAM_ROLES = {
        "research_agent": "资料搜集 - 搜索相关文献、数据、方法",
        "data_agent": "数据分析 - 上传、清洗、分析数据",
        "analyzer_agent": "问题分析 - 理解问题、分解任务、制定策略",
        "modeler_agent": "数学建模 - 建立模型、选择算法",
        "solver_agent": "算法求解 - 编程实现、结果验证",
        "writer_agent": "论文写作 - 生成完整LaTeX论文",
    }

    # 标准工作流
    WORKFLOW_STEPS = [
        {"agent": "analyzer_agent", "action": "analyze", "label": "问题分析"},
        {"agent": "data_agent", "action": "analyze_data", "label": "数据分析"},
        {"agent": "research_agent", "action": "search", "label": "资料搜集"},
        {"agent": "modeler_agent", "action": "build_model", "label": "数学建模"},
        {"agent": "solver_agent", "action": "solve", "label": "算法求解"},
        {"agent": "writer_agent", "action": "write_paper", "label": "论文写作"},
    ]

    def __init__(self, agents: Dict[str, Any], chat_room: Optional[ChatRoom] = None):
        self.agents = agents
        self.chat_room = chat_room
        self.current_plan: List[Dict[str, Any]] = []

    def _notify(self, sender: str, content: str, mentions: Optional[List[str]] = None):
        """向聊天室发送消息"""
        if self.chat_room:
            self.chat_room.post(sender, content, mentions=mentions or [])

    async def plan_workflow(self, problem_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        制定工作计划

        根据问题分析结果，动态调整工作流程
        """
        self._notify("coordinator", "正在分析问题，制定工作计划...")

        # 基础计划
        plan = list(self.WORKFLOW_STEPS)

        # 根据上下文调整（如果有数据，优先数据分析）
        if context.get("has_data"):
            # 确保数据分析在前
            if "data_agent" not in [p["agent"] for p in plan[:2]]:
                plan.insert(0, {"agent": "data_agent", "action": "analyze_data", "label": "数据分析"})

        # 检查是否有数据文件
        data_files = context.get("data_files", [])
        if data_files:
            self._notify("coordinator", f"检测到 {len(data_files)} 个数据文件，数据分析将优先进行。", mentions=["data_agent"])

        self.current_plan = plan
        return plan

    async def execute_workflow(
        self,
        problem_text: str,
        context: Dict[str, Any],
        room: ChatRoom,
    ) -> Dict[str, Any]:
        """执行完整工作流：协调所有Agent按顺序工作，实时更新聊天室"""
        # 动态调整工作流
        if context.get("has_data") and context.get("data_files"):
            data_count = len(context["data_files"])
            self._notify("coordinator", f"检测到 {data_count} 个数据文件，数据分析将优先进行！", mentions=["data_agent"])
        results: Dict[str, Any] = {}
        plan = await self.plan_workflow(problem_text, context)
        total = len(plan)

        self._notify("coordinator", f"📋 工作计划已制定，共 {total} 个阶段：")
        for i, step in enumerate(plan):
            self._notify("coordinator", f"  {i+1}. {step['label']} ({step['agent']})")

        for i, step in enumerate(plan):
            agent_name = step["agent"]
            action = step["action"]
            label = step["label"]
            progress = int((i / total) * 100)

            self._notify("coordinator", f"📌 阶段 {i+1}/{total}：{label}，请 {room.team.get(agent_name, {}).get('label', agent_name)} 开始工作。", mentions=[agent_name])

            agent = self.agents.get(agent_name)
            if not agent:
                self._notify("coordinator", f"⚠️ Agent {agent_name} 未找到，跳过此步骤。", mentions=["system"])
                continue

            # 更新上下文（融合之前的结果）
            step_context = {
                **context,
                "results": results,
                "problem_text": problem_text,
                "progress": progress,
                "current_step": i + 1,
                "total_steps": total,
            }

            try:
                # 执行Agent任务
                if hasattr(agent, "execute"):
                    output = await agent.execute(
                        task_input={"action": action, "problem_text": problem_text},
                        context=step_context,
                    )
                else:
                    output = {"error": f"Agent {agent_name} has no execute method"}

                results[agent_name] = output

                # Agent报告结果
                if agent_name == "writer_agent" and output.get("title"):
                    self._notify(agent_name, f"✅ 论文写作完成！标题：{output.get('title', '未命名')}。", mentions=["coordinator"])
                elif agent_name == "data_agent":
                    self._notify(agent_name, f"数据分析完成！发现 {len(output.get('insights', []))} 个数据洞察。", mentions=["modeler_agent", "solver_agent"])
                elif output.get("summary"):
                    self._notify(agent_name, f"✅ {label}完成：{output.get('summary', '')[:100]}")
                else:
                    self._notify(agent_name, f"✅ {label}完成。")

            except Exception as e:
                logger.error(f"Agent {agent_name} failed: {e}")
                self._notify("coordinator", f"❌ {label}阶段遇到问题：{str(e)[:100]}，正在尝试解决...", mentions=[agent_name])

        self._notify("coordinator", "🎉 所有阶段完成！正在整理最终结果...")
        return results

    async def broadcast_progress(
        self,
        step: int,
        total: int,
        agent_name: str,
        status: str,
    ):
        """广播进度更新"""
        progress = int((step / total) * 100)
        label = self.TEAM_ROLES.get(agent_name, agent_name)
        self._notify(
            "coordinator",
            f"📊 进度 {progress}% - {step}/{total} {label} {status}",
        )
