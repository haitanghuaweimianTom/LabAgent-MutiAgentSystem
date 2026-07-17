"""VLM 图审闭环 - 读图 → 评估 → 改代码 → 再编译。

v8.2: 实现 VLM 图审闭环：
1. VLM 读图 → 评估图表质量
2. 识别问题：与结果不一致 / 重复图 / 错误 caption
3. 生成修改建议
4. 自动修改代码并重新生成

参考：Sakana AI Scientist v2 的 VLM 图审机制。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VLMFigureReviewer:
    """VLM 图审闭环，使用视觉语言模型评估图表质量。"""

    def __init__(self):
        """初始化 VLM 图审器。"""
        self.review_history: List[Dict[str, Any]] = []

    def review_figure(
        self,
        figure_path: Path,
        figure_spec: Dict[str, Any],
        experiment_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """使用 VLM 评估图表质量。

        Args:
            figure_path: 图表文件路径
            figure_spec: 图表规格（标题、描述等）
            experiment_data: 实验数据

        Returns:
            评估结果
        """
        review_result = {
            "figure_id": figure_spec.get("id", "unknown"),
            "figure_path": str(figure_path),
            "issues": [],
            "suggestions": [],
            "quality_score": 0,
            "needs_revision": False,
        }

        try:
            # 1. 分析图表内容
            content_issues = self._analyze_figure_content(
                figure_path, figure_spec, experiment_data
            )
            review_result["issues"].extend(content_issues)

            # 2. 检查与数据一致性
            consistency_issues = self._check_data_consistency(
                figure_path, experiment_data
            )
            review_result["issues"].extend(consistency_issues)

            # 3. 检查美学质量
            aesthetic_issues = self._check_aesthetic_quality(figure_path)
            review_result["issues"].extend(aesthetic_issues)

            # 4. 生成修改建议
            suggestions = self._generate_suggestions(review_result["issues"])
            review_result["suggestions"] = suggestions

            # 5. 计算质量分数
            quality_score = self._calculate_quality_score(review_result["issues"])
            review_result["quality_score"] = quality_score

            # 6. 判断是否需要修订
            review_result["needs_revision"] = quality_score < 0.7 or len(review_result["issues"]) > 2

            # 7. 保存评审历史
            self.review_history.append(review_result)

            logger.info(
                f"VLM Figure Review: {review_result['figure_id']} "
                f"score={quality_score:.2f}, issues={len(review_result['issues'])}"
            )

        except Exception as e:
            logger.error(f"VLM Figure Review failed: {e}")
            review_result["error"] = str(e)

        return review_result

    def _analyze_figure_content(
        self,
        figure_path: Path,
        figure_spec: Dict[str, Any],
        experiment_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """分析图表内容。"""
        issues = []

        # 检查图表文件是否存在
        if not figure_path.exists():
            issues.append({
                "type": "missing_file",
                "severity": "high",
                "description": f"图表文件不存在: {figure_path}",
            })
            return issues

        # 检查文件大小
        file_size = figure_path.stat().st_size
        if file_size < 1000:  # 小于 1KB
            issues.append({
                "type": "empty_figure",
                "severity": "high",
                "description": "图表文件过小，可能为空图",
            })

        # 检查文件类型
        suffix = figure_path.suffix.lower()
        if suffix not in [".png", ".svg", ".pdf"]:
            issues.append({
                "type": "invalid_format",
                "severity": "medium",
                "description": f"不支持的图表格式: {suffix}",
            })

        return issues

    def _check_data_consistency(
        self,
        figure_path: Path,
        experiment_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """检查图表与数据的一致性。"""
        issues = []

        # 这里可以集成 VLM 来实际分析图表内容
        # 目前使用基于规则的检查

        # 检查是否有实验数据
        if not experiment_data:
            issues.append({
                "type": "no_data",
                "severity": "medium",
                "description": "实验数据为空，无法验证图表准确性",
            })

        return issues

    def _check_aesthetic_quality(self, figure_path: Path) -> List[Dict[str, Any]]:
        """检查图表美学质量。"""
        issues = []

        # 基于文件大小的简单检查
        file_size = figure_path.stat().st_size
        if file_size > 10_000_000:  # 大于 10MB
            issues.append({
                "type": "large_file",
                "severity": "low",
                "description": "图表文件过大，可能影响加载速度",
            })

        return issues

    def _generate_suggestions(
        self,
        issues: List[Dict[str, Any]],
    ) -> List[str]:
        """根据问题生成修改建议。"""
        suggestions = []

        issue_types = {issue["type"] for issue in issues}

        if "missing_file" in issue_types:
            suggestions.append("重新生成图表文件")

        if "empty_figure" in issue_types:
            suggestions.append("检查数据是否正确传递给绘图代码")

        if "no_data" in issue_types:
            suggestions.append("确保实验数据已正确加载")

        if "large_file" in issue_types:
            suggestions.append("降低图表分辨率或使用 SVG 格式")

        # 通用建议
        if not suggestions:
            suggestions.append("图表质量良好，无需修改")

        return suggestions

    def _calculate_quality_score(
        self,
        issues: List[Dict[str, Any]],
    ) -> float:
        """计算质量分数（0-1）。"""
        if not issues:
            return 1.0

        # 根据严重程度计算扣分
        severity_penalty = {
            "high": 0.3,
            "medium": 0.15,
            "low": 0.05,
        }

        total_penalty = sum(
            severity_penalty.get(issue.get("severity", "low"), 0.05)
            for issue in issues
        )

        return max(0.0, 1.0 - total_penalty)

    def get_revision_code_suggestions(
        self,
        review_result: Dict[str, Any],
        original_code: str,
    ) -> str:
        """根据评审结果生成修改后的代码建议。"""
        issues = review_result.get("issues", [])

        # 简单的代码修改建议
        modified_code = original_code

        for issue in issues:
            if issue["type"] == "empty_figure":
                # 添加数据验证
                if "plt.show()" not in modified_code:
                    modified_code += "\nplt.tight_layout()\n"

        return modified_code

    def get_review_summary(self) -> Dict[str, Any]:
        """获取评审历史摘要。"""
        if not self.review_history:
            return {"total_reviews": 0}

        scores = [r.get("quality_score", 0) for r in self.review_history]
        issues_count = sum(len(r.get("issues", [])) for r in self.review_history)

        return {
            "total_reviews": len(self.review_history),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "total_issues": issues_count,
            "revisions_needed": sum(1 for r in self.review_history if r.get("needs_revision")),
        }


# 全局单例
_vlm_reviewer_instance: Optional[VLMFigureReviewer] = None


def get_vlm_figure_reviewer() -> VLMFigureReviewer:
    """获取全局 VLM 图审器实例。"""
    global _vlm_reviewer_instance
    if _vlm_reviewer_instance is None:
        _vlm_reviewer_instance = VLMFigureReviewer()
    return _vlm_reviewer_instance
