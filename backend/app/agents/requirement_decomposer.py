"""需求分解器 Agent - 将长篇问题描述分解为结构化研究计划

当用户输入超过 3000 字符时，自动分解为包含研究目标、子任务、
方法提示等结构化信息的 JSON 计划，便于后续 Agent 并行协作。
"""
import json
import logging
import os
from typing import Any, Dict, Optional

from .base import BaseAgent, AgentFactory
from ..core.paths import get_project_output_dir

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """你是一位资深的研究规划专家，擅长将复杂的数学建模问题拆解为可执行的结构化研究计划。

你的任务是分析用户给出的完整问题描述，提取核心信息并分解为子任务。

【输出要求】
严格输出以下 JSON 格式，不要添加任何多余文本：

{
  "research_goal": "一句话概括的研究目标",
  "background": "问题背景摘要（2-3句话）",
  "key_questions": ["需要回答的核心问题1", "核心问题2", "..."],
  "methodology_hints": ["建议的研究方法/模型提示1", "提示2", "..."],
  "expected_output": "预期产出类型（如：优化方案/预测模型/评价报告等）",
  "data_requirements": ["需要的数据类型1", "数据类型2", "..."],
  "template_suggestion": "推荐使用的模板ID（math_modeling/research_paper/coursework 等）",
  "subtasks": [
    {
      "id": 1,
      "description": "子任务描述",
      "suggested_agent": "推荐执行该子任务的Agent名称（如 research_agent/modeler_agent/solver_agent/writer_agent 等）",
      "priority": "high/medium/low",
      "dependencies": []
    }
  ]
}

【分解原则】
1. 子任务粒度适中，每个子任务应可在一次 Agent 调用内完成
2. 明确子任务间的依赖关系（dependencies 填写依赖的子任务 id 列表）
3. 根据问题特征推荐合适的模板和方法
4. 子任务数量建议 3-8 个，避免过细或过粗"""


@AgentFactory.register("requirement_decomposer")
class RequirementDecomposerAgent(BaseAgent):
    name = "requirement_decomposer"
    label = "需求分解器"
    description = "将长篇问题描述分解为结构化研究计划"
    default_model = ""

    # 字符数阈值：低于此值不触发分解
    DECOMPOSITION_THRESHOLD = 3000

    def get_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    async def execute(
        self, task_input: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """执行需求分解。

        Args:
            task_input: 任务输入（未使用，数据从 context 获取）
            context: 必须包含 "problem_text" 键

        Returns:
            分解后的结构化 JSON 计划；若无需分解则返回 None
        """
        problem_text = context.get("problem_text", "")
        if not problem_text:
            logger.warning("[requirement_decomposer] context 中缺少 problem_text")
            return None

        # 短问题无需分解
        if len(problem_text) < self.DECOMPOSITION_THRESHOLD:
            logger.info(
                f"[requirement_decomposer] 问题长度 {len(problem_text)} "
                f"< {self.DECOMPOSITION_THRESHOLD}，跳过分解"
            )
            return None

        logger.info(
            f"[requirement_decomposer] 问题长度 {len(problem_text)}，开始分解"
        )

        # 调用 LLM 生成结构化计划
        plan = await self._decompose_with_llm(problem_text, context)
        if plan is None:
            # LLM 失败，返回原始文本作为 fallback
            logger.warning("[requirement_decomposer] LLM 分解失败，返回原始文本")
            return {
                "research_goal": problem_text[:200],
                "background": "",
                "key_questions": [],
                "methodology_hints": [],
                "expected_output": "",
                "data_requirements": [],
                "template_suggestion": "math_modeling",
                "subtasks": [],
                "_fallback": True,
                "_raw_problem_text": problem_text,
            }

        # 保存到项目输出目录
        self._save_plan(plan, context)

        return plan

    async def _decompose_with_llm(
        self, problem_text: str, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """调用 LLM 将问题文本分解为结构化 JSON 计划。"""
        # 截断过长的输入，避免超出上下文窗口
        truncated = problem_text[:15000]

        user_prompt = (
            f"请分析以下数学建模问题，并将其分解为结构化研究计划：\n\n"
            f"【问题描述】\n{truncated}"
        )

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self.call_llm(
                messages=messages,
                context=context,
                temperature=0.3,
                tools=[],
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            plan = self.extract_json(content)
            if not plan:
                logger.warning("[requirement_decomposer] LLM 输出无法解析为 JSON")
                return None

            # 基本校验：确保关键字段存在
            plan.setdefault("research_goal", "")
            plan.setdefault("background", "")
            plan.setdefault("key_questions", [])
            plan.setdefault("methodology_hints", [])
            plan.setdefault("expected_output", "")
            plan.setdefault("data_requirements", [])
            plan.setdefault("template_suggestion", "math_modeling")
            plan.setdefault("subtasks", [])

            logger.info(
                f"[requirement_decomposer] 分解完成，"
                f"共 {len(plan.get('subtasks', []))} 个子任务"
            )
            return plan

        except Exception as e:
            logger.error(f"[requirement_decomposer] LLM 调用异常: {e}")
            return None

    def _save_plan(self, plan: Dict[str, Any], context: Dict[str, Any]) -> None:
        """将分解计划保存到项目输出目录的 requirement_plan.json。"""
        project_name = context.get("project_name")
        output_dir = get_project_output_dir(project_name)
        file_path = os.path.join(output_dir, "requirement_plan.json")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            logger.info(f"[requirement_decomposer] 计划已保存: {file_path}")
        except Exception as e:
            logger.warning(f"[requirement_decomposer] 保存计划失败: {e}")
