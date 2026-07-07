"""创新发现专家Agent - 从文献综述中发现研究空白并提出创新点

职责：
- 接收 research_agent 的文献/方法结果和 analyzer_agent 的问题分析
- 识别当前研究的空白（research gaps）
- 提出具有创新性的研究思路（novelty, methodology, expected contribution）
- 输出结构化的创新分析报告
"""

import json
import logging
from typing import Any, Dict, List, Optional
from .base import BaseAgent, AgentFactory
from ..core.security import wrap_user_content
from ..core.paths import get_project_output_dir

logger = logging.getLogger(__name__)


@AgentFactory.register("innovation_agent")
class InnovationAgent(BaseAgent):
    name = "innovation_agent"
    label = "创新发现专家"
    description = "从文献综述中发现研究空白并提出创新点"
    default_model = ""

    def get_system_prompt(self) -> str:
        return """你是一名严谨的学术研究创新分析师，擅长从现有文献中发现研究空白并提出创新性研究方案。

【核心职责】
1. 综合分析已有文献的研究内容、方法和局限性
2. 识别当前研究领域的空白和未解决问题
3. 基于研究空白提出具有创新性的研究思路
4. 评估每个创新点的新颖性、可行性和预期贡献

【分析原则】
- 所有分析必须基于提供的文献数据，不要编造不存在的研究
- 砇究空白应是当前文献中确实未覆盖或未充分解决的问题
- 创新点应有明确的方法论支撑，而非空泛的设想
- 充分考虑实际可行性（技术可行性、数据可获取性、计算复杂度）

【输出格式（严格JSON）】
{
    "research_gaps": [
        {
            "gap_id": 1,
            "description": "研究空白描述",
            "importance": "high/medium/low",
            "existing_work": "现有工作为何不足",
            "opportunity": "填补空白的机会"
        }
    ],
    "innovation_ideas": [
        {
            "idea_id": 1,
            "title": "创新点标题",
            "novelty": "新在哪里",
            "methodology": "核心方法",
            "expected_contribution": "预期贡献",
            "feasibility": "high/medium/low",
            "related_gaps": [1],
            "risks": "潜在风险"
        }
    ],
    "recommended_approach": "推荐方案",
    "confidence": 0.8
}

【格式要求】
- research_gaps 至少识别 2 个研究空白，最多 5 个
- innovation_ideas 至少提出 2 个创新点，最多 4 个
- 每个创新点必须关联至少一个 research gap
- confidence 表示整体分析的置信度（0-1）
- 输出必须是严格合法的 JSON，不要有任何其他文字"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行创新分析

        Args:
            task_input: 任务输入，可包含额外参数
            context: 上下文，包含 research_agent 和 analyzer_agent 的结果
        """
        # 从 context 中提取上游 Agent 的结果
        research_result = context.get("research_agent", {})
        analyzer_result = context.get("analyzer_agent", {})
        problem_text = context.get("problem_text", "")
        project_name = context.get("project_name")

        # 构建分析材料
        papers = research_result.get("papers", [])
        methods = research_result.get("methods", [])
        research_summary = research_result.get("summary", "")
        problem_type = analyzer_result.get("problem_type", "")
        sub_problems = analyzer_result.get("sub_problems", [])

        # 检查是否有足够的输入材料
        has_materials = bool(papers or methods or research_summary or problem_text)
        if not has_materials:
            logger.warning("InnovationAgent: 无足够的上游输入材料，使用 fallback")
            return self._fallback_result(
                project_name=project_name,
                reason="缺少上游 Agent 的研究结果和问题分析",
            )

        # 构建用户 prompt
        user_content = self._build_analysis_prompt(
            problem_text=problem_text,
            problem_type=problem_type,
            sub_problems=sub_problems,
            papers=papers,
            methods=methods,
            research_summary=research_summary,
        )

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": user_content},
        ]

        # 调用 LLM 进行创新分析
        try:
            response = await self.call_llm(messages=messages, temperature=0.4)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            result = self.extract_json(content)

            if result and self._validate_result(result):
                # 补充元数据
                result["analyzed_paper_count"] = len(papers)
                result["method_count"] = len(methods)
                result["problem_type"] = problem_type

                # 保存结果到项目输出目录
                self._save_result(result, project_name)

                gap_count = len(result.get("research_gaps", []))
                idea_count = len(result.get("innovation_ideas", []))
                logger.info(
                    f"InnovationAgent 完成: {gap_count} 个研究空白, "
                    f"{idea_count} 个创新点"
                )
                return result

            logger.warning("InnovationAgent: LLM 返回结果验证失败，使用 fallback")
        except Exception as e:
            logger.warning(f"InnovationAgent LLM 调用失败: {e}")

        # LLM 失败时的 fallback
        return self._fallback_result(
            project_name=project_name,
            reason=f"LLM 分析失败: {str(e)[:100]}" if 'e' in dir() else "LLM 分析失败",
            papers=papers,
            methods=methods,
            problem_type=problem_type,
            sub_problems=sub_problems,
        )

    def _build_analysis_prompt(
        self,
        problem_text: str,
        problem_type: str,
        sub_problems: List[Dict[str, Any]],
        papers: List[Dict[str, Any]],
        methods: List[Dict[str, Any]],
        research_summary: str,
    ) -> str:
        """构建 LLM 分析 prompt"""
        parts = []

        # 问题背景
        if problem_text:
            parts.append(f"【问题背景】\n{wrap_user_content(problem_text[:500], 'problem')}\n")

        if problem_type:
            parts.append(f"【问题类型】{problem_type}\n")

        # 子问题分析
        if sub_problems:
            sp_text = ""
            for sp in sub_problems:
                sp_text += (
                    f"- 子问题{sp.get('id', '')}: {sp.get('name', '')} "
                    f"({sp.get('problem_type', '')})\n"
                )
            parts.append(f"【子问题分解】\n{sp_text}")

        # 文献综述
        if papers:
            papers_brief = []
            for i, p in enumerate(papers[:10], 1):
                title = p.get("title", "")
                abstract = p.get("abstract", "")[:200]
                year = p.get("year", "")
                papers_brief.append(f"{i}. [{year}] {title}\n   摘要: {abstract}...")
            parts.append(f"【已搜集文献（{len(papers)}篇）】\n" + "\n".join(papers_brief))

        # 已有方法
        if methods:
            methods_text = ""
            for m in methods[:8]:
                name = m.get("name", m.get("method", ""))
                desc = m.get("description", "")[:150]
                methods_text += f"- {name}: {desc}\n"
            parts.append(f"【已有方法】\n{methods_text}")

        # 研究总结
        if research_summary:
            parts.append(f"【文献综述总结】\n{research_summary[:800]}\n")

        parts.append("请基于以上材料，识别研究空白并提出创新研究方案。输出严格 JSON 格式。")

        return "\n".join(parts)

    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """验证 LLM 返回的结果结构"""
        gaps = result.get("research_gaps")
        ideas = result.get("innovation_ideas")

        if not isinstance(gaps, list) or len(gaps) < 1:
            logger.warning("InnovationAgent: research_gaps 无效或为空")
            return False

        if not isinstance(ideas, list) or len(ideas) < 1:
            logger.warning("InnovationAgent: innovation_ideas 无效或为空")
            return False

        # 验证每个 gap 的必要字段
        for gap in gaps:
            if not gap.get("gap_id") or not gap.get("description"):
                logger.warning("InnovationAgent: gap 缺少必要字段")
                return False

        # 验证每个 idea 的必要字段
        for idea in ideas:
            if not idea.get("idea_id") or not idea.get("title"):
                logger.warning("InnovationAgent: idea 缺少必要字段")
                return False

        # 验证 recommended_approach
        if not result.get("recommended_approach"):
            logger.warning("InnovationAgent: 缺少 recommended_approach")
            return False

        return True

    def _save_result(self, result: Dict[str, Any], project_name: Optional[str]) -> None:
        """保存分析结果到项目输出目录"""
        try:
            output_dir = get_project_output_dir(project_name)
            file_path = output_dir / "innovation_analysis.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"InnovationAgent: 结果已保存到 {file_path}")
        except Exception as e:
            logger.warning(f"InnovationAgent: 保存结果失败: {e}")

    def _fallback_result(
        self,
        project_name: Optional[str] = None,
        reason: str = "",
        papers: Optional[List[Dict[str, Any]]] = None,
        methods: Optional[List[Dict[str, Any]]] = None,
        problem_type: str = "",
        sub_problems: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """LLM 失败时的 fallback 分析

        基于已有材料生成基础分析，不依赖 LLM。
        """
        fallback_result = {
            "research_gaps": [],
            "innovation_ideas": [],
            "recommended_approach": "基于已有文献的基础分析，请结合具体问题进一步细化",
            "confidence": 0.3,
            "_fallback": True,
            "_fallback_reason": reason,
        }

        # 尝试从已有材料中提取基础信息
        papers = papers or []
        methods = methods or []
        sub_problems = sub_problems or []

        # 从论文局限性中提取可能的研究空白
        for p in papers:
            extraction = p.get("extraction", {})
            limitations = extraction.get("limitations", "")
            if limitations:
                gap = {
                    "gap_id": len(fallback_result["research_gaps"]) + 1,
                    "description": limitations[:200],
                    "importance": "medium",
                    "existing_work": p.get("title", "现有研究"),
                    "opportunity": f"基于 {p.get('title', '现有研究')} 的局限性改进",
                }
                fallback_result["research_gaps"].append(gap)
                if len(fallback_result["research_gaps"]) >= 3:
                    break

        # 如果没有从论文中提取到空白，生成通用空白
        if not fallback_result["research_gaps"]:
            fallback_result["research_gaps"] = [
                {
                    "gap_id": 1,
                    "description": "当前研究在方法组合和创新应用方面存在不足",
                    "importance": "medium",
                    "existing_work": "现有研究多采用单一方法",
                    "opportunity": "探索多方法融合的创新路径",
                },
            ]

        # 生成基础创新点
        if methods:
            primary_method = methods[0].get("name", methods[0].get("method", "已有方法"))
            fallback_result["innovation_ideas"] = [
                {
                    "idea_id": 1,
                    "title": f"基于{primary_method}的改进方案",
                    "novelty": "在现有方法基础上引入新的约束条件或参数优化策略",
                    "methodology": primary_method,
                    "expected_contribution": "提升模型在特定场景下的精度和鲁棒性",
                    "feasibility": "high",
                    "related_gaps": [1],
                    "risks": "改进幅度可能有限",
                },
            ]
        else:
            fallback_result["innovation_ideas"] = [
                {
                    "idea_id": 1,
                    "title": "多方法融合创新方案",
                    "novelty": "将多种传统方法有机融合，发挥各方法优势",
                    "methodology": "组合优化 + 启发式搜索",
                    "expected_contribution": "提供更全面的分析视角和更优的求解效果",
                    "feasibility": "medium",
                    "related_gaps": [1],
                    "risks": "方法组合的协调性需要验证",
                },
            ]

        # 保存 fallback 结果
        self._save_result(fallback_result, project_name)

        logger.info(
            f"InnovationAgent fallback: {len(fallback_result['research_gaps'])} 个空白, "
            f"{len(fallback_result['innovation_ideas'])} 个创新点"
        )
        return fallback_result
