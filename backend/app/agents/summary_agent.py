"""总结Agent - 生成结构化任务总结报告，提取经验教训"""
import json
import logging
from typing import Any, Dict, List, Optional
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)


@AgentFactory.register("summary_agent")
class SummaryAgent(BaseAgent):
    name = "summary_agent"
    label = "总结专家"
    description = "生成结构化总结报告，提取经验教训"
    default_model = ""

    def get_system_prompt(self) -> str:
        return """你是一位严谨细致的研究总结专家，专门负责在任务完成后生成结构化总结报告。

【核心职责】
1. 回顾整个研究过程，梳理各阶段的工作成果
2. 评估论文质量和创新性
3. 提炼经验教训，供后续任务复用
4. 整理数据集和文献注册表

【输出格式（严格JSON）】
{
    "task_id": "任务ID",
    "research_summary": "研究过程回顾（200-500字，涵盖问题定义、方法选择、求解过程、结果分析）",
    "innovation_points": ["创新点1", "创新点2"],
    "experiment_results": {
        "key_findings": ["关键发现1", "关键发现2"],
        "metrics": {"accuracy": 0, "score": 0}
    },
    "paper_quality": {
        "overall_score": 75,
        "chapter_scores": {
            "abstract": 80,
            "method": 70,
            "results": 75,
            "writing": 80,
            "innovation": 65
        },
        "strengths": ["优势1", "优势2"],
        "weaknesses": ["不足1", "不足2"]
    },
    "lessons_learned": [
        {
            "category": "method_selection|writing|data_processing|experiment_design|template_specific",
            "subcategory": "根据模板细化的子分类",
            "content": "经验内容（简洁明了）",
            "tags": ["tag1", "tag2"],
            "impact_score": 7
        }
    ],
    "dataset_registry": [
        {"name": "数据集名称", "source": "来源", "type": "类型"}
    ],
    "literature_registry": [
        {"title": "论文标题", "arxiv_id": "ID", "relevance": "与本任务的关联说明"}
    ],
    "recommendations": ["改进建议1", "改进建议2"]
}

【评分标准】
- overall_score: 0-100分，综合考虑创新性、方法严谨性、结果可靠性、写作质量
- impact_score: 1-10分，经验教训对后续任务的影响程度

【规则】
- 仅基于提供的任务结果进行分析，不要编造信息
- 经验教训要具体可复用，避免泛泛而谈
- 所有评价要客观公正"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务总结"""
        results = context.get("results", {})
        task_id = context.get("task_id", task_input.get("task_id", "unknown"))
        task_dir = context.get("task_dir", "")

        logger.info(f"SummaryAgent 开始为任务 {task_id} 生成总结报告")

        # 收集各 Agent 的结果摘要
        agent_summaries = self._collect_agent_results(results)

        # 使用 LLM 生成总结报告
        summary_report = await self._generate_summary(
            task_id=task_id,
            agent_summaries=agent_summaries,
            context=context,
        )

        # 保存总结报告到 task_dir/task_summary.json
        self._save_task_summary(task_dir, summary_report)

        # 提取经验教训并保存到 data/memory/lessons.json
        self._save_lessons(task_id, summary_report.get("lessons_learned", []))

        # 更新各 Agent 的案例库
        await self._update_agent_cases(task_id, summary_report)

        logger.info(f"SummaryAgent 总结完成: {task_id}")
        return summary_report

    def _collect_agent_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """从各 Agent 的结果中提取关键信息"""
        summaries = {}
        for agent_name, agent_result in results.items():
            if not isinstance(agent_result, dict):
                continue
            summaries[agent_name] = {
                "success": agent_result.get("success", True),
                "summary": agent_result.get("summary", agent_result.get("interpretation", "")),
                "key_findings": agent_result.get("key_findings", []),
                "errors": agent_result.get("errors", []),
            }
        return summaries

    async def _generate_summary(
        self,
        task_id: str,
        agent_summaries: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """使用 LLM 生成结构化总结报告"""
        system_prompt = self.get_system_prompt()

        # 构建用户 prompt
        summaries_text = json.dumps(agent_summaries, ensure_ascii=False, indent=2)
        problem_text = context.get("problem_text", "")[:500]
        template = context.get("template", "math_modeling")

        user_prompt = f"""任务ID: {task_id}
问题模板: {template}
问题描述: {problem_text}

各Agent执行结果摘要:
{summaries_text[:6000]}

请基于以上信息生成完整的结构化总结报告。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self.call_llm(messages=messages, context=context, tools=[])
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            result = self.extract_json(content)
            if result:
                result["task_id"] = task_id
                return result
        except Exception as e:
            logger.warning(f"SummaryAgent LLM 调用失败: {e}")

        # Fallback: 基于已有结果生成基本总结
        return self._build_fallback_summary(task_id, agent_summaries, context)

    def _build_fallback_summary(
        self,
        task_id: str,
        agent_summaries: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """LLM 失败时生成基础总结"""
        success_agents = [
            name for name, s in agent_summaries.items()
            if s.get("success", True)
        ]
        failed_agents = [
            name for name, s in agent_summaries.items()
            if not s.get("success", True)
        ]

        return {
            "task_id": task_id,
            "research_summary": f"任务 {task_id} 完成。成功执行的Agent: {', '.join(success_agents)}。"
                                + (f"失败的Agent: {', '.join(failed_agents)}。" if failed_agents else ""),
            "innovation_points": [],
            "experiment_results": {
                "key_findings": [
                    finding
                    for s in agent_summaries.values()
                    for finding in s.get("key_findings", [])
                ],
                "metrics": {},
            },
            "paper_quality": {
                "overall_score": 60 if failed_agents else 75,
                "chapter_scores": {},
                "strengths": ["各Agent协作完成任务"],
                "weaknesses": [f"以下Agent执行失败: {', '.join(failed_agents)}"] if failed_agents else [],
            },
            "lessons_learned": [],
            "dataset_registry": [],
            "literature_registry": [],
            "recommendations": [],
        }

    def _save_task_summary(self, task_dir: str, summary: Dict[str, Any]) -> None:
        """保存任务总结到 task_dir/task_summary.json"""
        if not task_dir:
            logger.warning("SummaryAgent: task_dir 为空，跳过保存")
            return
        try:
            from pathlib import Path
            output_path = Path(task_dir) / "task_summary.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.info(f"SummaryAgent: 任务总结已保存到 {output_path}")
        except Exception as e:
            logger.warning(f"SummaryAgent: 保存任务总结失败: {e}")

    def _save_lessons(self, task_id: str, lessons: List[Dict[str, Any]]) -> None:
        """提取经验教训并保存到 memory 系统"""
        if not lessons:
            return
        try:
            from ..core.memory import get_memory_manager
            mm = get_memory_manager()
            for lesson in lessons:
                if not isinstance(lesson, dict):
                    continue
                mm.get_lessons().add_lesson(
                    category=lesson.get("category", "general"),
                    content=lesson.get("content", ""),
                    problem_type=lesson.get("subcategory", ""),
                    method=", ".join(lesson.get("tags", [])),
                    success=True,
                    source_task=task_id,
                )
            mm.save_lessons()
            logger.info(f"SummaryAgent: 已保存 {len(lessons)} 条经验教训")
        except Exception as e:
            logger.warning(f"SummaryAgent: 保存经验教训失败: {e}")

    async def _update_agent_cases(self, task_id: str, summary: Dict[str, Any]) -> None:
        """根据总结报告更新各 Agent 的案例库"""
        paper_quality = summary.get("paper_quality", {})
        overall_score = paper_quality.get("overall_score", 50)
        success = overall_score >= 60

        # 收集所有 Agent 的方法信息
        all_agents = set()
        for agent_result in summary.get("experiment_results", {}).get("key_findings", []):
            pass  # findings 不含 agent 信息

        # 从各 Agent 的结果中提取方法信息（通过 agent_summaries 推断）
        try:
            from ..core.agent_memory import get_agent_profile
            for agent_name in ["research_agent", "modeler_agent", "solver_agent", "writer_agent"]:
                profile = get_agent_profile(agent_name)
                method = summary.get("research_summary", "")[:200]
                outcome = "success" if success else "failure"
                profile.add_case(
                    case_type=outcome,
                    task_id=task_id,
                    problem_type=summary.get("task_id", ""),
                    method=method,
                    outcome=f"论文质量评分: {overall_score}",
                    impact_score=overall_score / 100.0,
                    summary=summary.get("research_summary", "")[:500],
                )
            logger.info(f"SummaryAgent: 已更新 {len(['research_agent', 'modeler_agent', 'solver_agent', 'writer_agent'])} 个 Agent 的案例库")
        except Exception as e:
            logger.debug(f"SummaryAgent: 更新 Agent 案例库失败（静默跳过）: {e}")
