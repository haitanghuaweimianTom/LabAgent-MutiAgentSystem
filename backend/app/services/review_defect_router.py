"""审稿缺陷分类路由 —— 将 peer_review 意见映射到 writer / experiment / solver。

规则优先级：
1. 数字矛盾 / 实验缺失 / 可复现性过低 → experiment 或 solver
2. 仅表述/结构/清晰度问题 → writer
3. 默认 writer
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

DefectRoute = Literal["revise", "revise_experiment", "revise_solver", "accept", "abort", "wait_user"]

# 实验/证据类关键词
_EXPERIMENT_KEYWORDS = re.compile(
    r"(实验|消融|baseline|基线|对比|ablation|metric|指标|结果|表格|表\s*\d|"
    r"数据集|dataset|可复现|reproducib|训练|train|eval|准确率|AUC|F1|"
    r"缺少实验|没有实验|弱实验|证据不足|数字矛盾|数值不一致|hallucin)",
    re.IGNORECASE,
)

# 实现/代码/求解类关键词
_SOLVER_KEYWORDS = re.compile(
    r"(代码|实现|算法错误|求解失败|bug|crash|报错|运行失败|脚本|"
    r"implementation|solver|数值求解|收敛|优化器)",
    re.IGNORECASE,
)

# 文笔/结构类关键词
_WRITING_KEYWORDS = re.compile(
    r"(表述|清晰|结构|语法|语言|图表说明|caption|排版|引用格式|"
    r"clarity|writing|grammar|typo|章节|摘要|introduction)",
    re.IGNORECASE,
)


def _flatten_comments(review: Dict[str, Any]) -> List[str]:
    comments = review.get("comments") or {}
    texts: List[str] = []
    for key in ("major", "minor"):
        for item in comments.get(key, []) or []:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                texts.append(str(item.get("text") or item.get("comment") or item))
    for ed in review.get("suggested_edits") or []:
        if isinstance(ed, dict):
            texts.append(f"{ed.get('target', '')} {ed.get('change', '')}")
        else:
            texts.append(str(ed))
    return texts


def classify_defect_route(
    review: Dict[str, Any],
    *,
    paper_template: str = "math_modeling",
    experiment_revision_count: int = 0,
    max_experiment_revisions: int = 2,
    ccf_a_templates: Optional[set] = None,
) -> DefectRoute:
    """根据审稿结果决定下一步路由目标。"""
    rec = (review.get("recommendation") or "").lower()
    scores = review.get("scores") or {}
    repro = review.get("reproducibility") or {}

    # 显式 defect_category（若 peer_review 已标注）
    explicit = (review.get("defect_category") or review.get("revise_target") or "").lower()
    if explicit in ("experiment", "revise_experiment", "evidence"):
        if experiment_revision_count >= max_experiment_revisions:
            return "revise"
        return "revise_experiment"
    if explicit in ("solver", "revise_solver", "code", "implementation"):
        if experiment_revision_count >= max_experiment_revisions:
            return "revise"
        return "revise_solver"
    if explicit in ("writer", "writing", "clarity", "revise"):
        return "revise"

    soundness = int(scores.get("soundness") or 3)
    clarity = int(scores.get("clarity") or 3)
    novelty = int(scores.get("novelty") or 3)
    repro_score = int(repro.get("score") or 3)

    texts = _flatten_comments(review)
    joined = "\n".join(texts)

    exp_hits = len(_EXPERIMENT_KEYWORDS.findall(joined))
    solver_hits = len(_SOLVER_KEYWORDS.findall(joined))
    writing_hits = len(_WRITING_KEYWORDS.findall(joined))

    # 可复现性缺失或 soundness 低 → 实验/求解
    evidence_weak = (
        soundness <= 2
        or repro_score <= 2
        or not repro.get("has_baseline_source", True)
        or not repro.get("has_dataset_reference", True)
        or exp_hits >= 1
    )

    ccf = ccf_a_templates or {
        "ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper",
    }
    is_ccf = paper_template in ccf

    if evidence_weak and experiment_revision_count < max_experiment_revisions:
        if solver_hits > exp_hits and not is_ccf:
            return "revise_solver"
        if is_ccf or exp_hits > 0 or soundness <= 2 or repro_score <= 2:
            return "revise_experiment"
        return "revise_solver"

    # 主要是写作问题
    if writing_hits >= exp_hits and clarity <= 3:
        return "revise"

    # novelty 低但证据够 → 写作/讨论加强即可
    if novelty <= 2 and soundness >= 3:
        return "revise"

    if rec == "revise":
        return "revise"
    return "revise"


def build_revision_brief(review: Dict[str, Any], route: DefectRoute) -> Dict[str, Any]:
    """构造传给下游节点的修订简报。"""
    return {
        "route": route,
        "defect_category": route.replace("revise_", "") if route.startswith("revise_") else "writing",
        "scores": review.get("scores") or {},
        "comments": review.get("comments") or {},
        "suggested_edits": review.get("suggested_edits") or [],
        "reproducibility": review.get("reproducibility") or {},
        "instruction": _route_instruction(route),
    }


def _route_instruction(route: DefectRoute) -> str:
    if route == "revise_experiment":
        return (
            "审稿指出实验/证据不足。请补充 baseline 对比、消融实验、"
            "可复现配置（seed/超参/数据引用），并确保数字来自真实运行日志。"
        )
    if route == "revise_solver":
        return (
            "审稿指出实现/求解问题。请修复代码错误、重新执行求解，"
            "并保证输出数字与论文声明一致。"
        )
    return "审稿指出表述/结构问题。请按 suggested_edits 修订论文文本与图表说明。"
