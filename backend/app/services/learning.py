"""自我学习与记忆进化服务

职责：
- 从任务结果中提取经验教训
- 结合用户反馈生成 LessonsMemory 条目
- 权威来源搜索与验证
"""
import logging
from typing import Any, Dict, List, Optional

from ..core.memory import get_memory_manager

logger = logging.getLogger(__name__)


class LessonExtractor:
    """从任务结果中提取可复用的经验教训"""

    CATEGORY_MAP = {
        "analyzer_agent": "method_selection",
        "data_agent": "data_processing",
        "modeler_agent": "modeling",
        "solver_agent": "solving",
        "writer_agent": "writing",
        "research_agent": "method_selection",
    }

    def extract_from_task(self, task_id: str, result: Dict[str, Any], feedback: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """分析任务结果，返回建议添加的经验列表"""
        lessons: List[Dict[str, Any]] = []
        if not result:
            return lessons

        output = result.get("output", {})
        problem_text = result.get("problem_text", "")
        problem_type = self._infer_problem_type(problem_text, output)

        # 1. 从 Agent 结果中提取方法选择经验
        modeler_output = output.get("modeler_agent", {})
        models = modeler_output.get("sub_problem_models", [])
        for m in models:
            model_name = m.get("model_name", "")
            model_type = m.get("model_type", "")
            if model_name and model_type:
                lessons.append({
                    "category": "modeling",
                    "content": f"对于'{problem_type}'类型问题，可采用{model_name}（{model_type}）进行建模。",
                    "problem_type": problem_type,
                    "method": model_name,
                    "success": True,
                    "source_task": task_id,
                })

        # 2. 从求解结果中提取经验
        solver_output = output.get("solver_agent", {})
        solutions = solver_output.get("sub_problem_solutions", [])
        for sol in solutions:
            task_types = sol.get("task_types", [])
            alg_name = ""
            model = sol.get("model", {})
            if isinstance(model.get("algorithm"), dict):
                alg_name = model["algorithm"].get("name", "")
            if task_types:
                lessons.append({
                    "category": "solving",
                    "content": f"{task_types[0]}类型问题可使用{alg_name or '对应算法'}求解。",
                    "problem_type": problem_type,
                    "method": alg_name or task_types[0],
                    "success": sol.get("execution_success", True),
                    "source_task": task_id,
                })

            # 执行失败时记录教训
            if not sol.get("execution_success", True):
                error = sol.get("execution_error", "") or sol.get("error_classification", "")
                lessons.append({
                    "category": "solving",
                    "content": f"求解失败教训：{error[:200]}",
                    "problem_type": problem_type,
                    "method": alg_name or "",
                    "success": False,
                    "source_task": task_id,
                })

        # 3. 从写作结果中提取经验
        writer_output = output.get("writer_agent", {})
        chapters = writer_output.get("chapters", [])
        low_score_chapters = [c for c in chapters if c.get("score", 100) < 75]
        if low_score_chapters:
            lessons.append({
                "category": "writing",
                "content": f"写作章节评分偏低，需关注：{', '.join(c.get('title', '') for c in low_score_chapters)}",
                "problem_type": problem_type,
                "method": "chapter_writing",
                "success": False,
                "source_task": task_id,
            })

        # 4. 用户反馈
        if feedback:
            overall = feedback.get("overall", 0)
            comment = feedback.get("comment", "")
            if comment or overall > 0:
                lessons.append({
                    "category": feedback.get("category", "method_selection"),
                    "content": comment or f"用户评分：{overall}/5",
                    "problem_type": problem_type,
                    "method": feedback.get("method", ""),
                    "success": overall >= 3,
                    "source_task": task_id,
                })

        return lessons

    def _infer_problem_type(self, problem_text: str, output: Dict[str, Any]) -> str:
        analyzer = output.get("analyzer_agent", {})
        return analyzer.get("problem_type", "") or problem_text[:50]


class AuthoritySearcher:
    """权威来源搜索：优先查找官方文档、顶级期刊、知名数据集"""

    AUTHORITY_PATTERNS = {
        "dataset": ["kaggle.com", "huggingface.co/datasets", "archive.ics.uci.edu", "gov.uk", "data.gov"],
        "paper": ["arxiv.org", "doi.org", "ieee.org", "acm.org", "nature.com", "science.org"],
        "doc": ["docs.python.org", "pytorch.org", "scikit-learn.org", "tensorflow.org", "docs.scipy.org"],
    }

    def score_url(self, url: str) -> int:
        """给 URL 打分，权威来源分数高"""
        url_lower = url.lower()
        score = 0
        for category, patterns in self.AUTHORITY_PATTERNS.items():
            for pattern in patterns:
                if pattern in url_lower:
                    score += 20 if category == "paper" else 15
        if "wikipedia" in url_lower:
            score += 5
        return min(score, 100)


_lesson_extractor: Optional[LessonExtractor] = None
_authority_searcher: Optional[AuthoritySearcher] = None


def get_lesson_extractor() -> LessonExtractor:
    global _lesson_extractor
    if _lesson_extractor is None:
        _lesson_extractor = LessonExtractor()
    return _lesson_extractor


def get_authority_searcher() -> AuthoritySearcher:
    global _authority_searcher
    if _authority_searcher is None:
        _authority_searcher = AuthoritySearcher()
    return _authority_searcher


def add_lessons_from_task(task_id: str, result: Dict[str, Any], feedback: Optional[Dict[str, Any]] = None) -> int:
    """便捷函数：提取并保存任务经验教训"""
    extractor = get_lesson_extractor()
    lessons = extractor.extract_from_task(task_id, result, feedback)
    if not lessons:
        return 0

    mm = get_memory_manager()
    for lesson in lessons:
        mm.get_lessons().add_lesson(**lesson)
    mm.save_lessons()
    logger.info(f"从任务 {task_id} 提取并保存 {len(lessons)} 条经验")
    return len(lessons)
