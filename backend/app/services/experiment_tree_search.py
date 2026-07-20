"""浅层实验树搜索 —— 并行 seed / beam 节点，失败 Pivot。

规模刻意保持小（默认 beam=3, depth=2），对齐计划 P2「浅树搜索」。
"""
from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExperimentNode:
    node_id: str
    parent_id: Optional[str]
    depth: int
    config: Dict[str, Any]
    status: str = "pending"  # pending | running | success | failed | pruned
    score: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    children: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentTreeResult:
    best_node_id: Optional[str]
    best_config: Dict[str, Any]
    best_score: float
    nodes: List[Dict[str, Any]]
    pivots: List[Dict[str, Any]]
    parallel_seeds: List[int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "best_node_id": self.best_node_id,
            "best_config": self.best_config,
            "best_score": self.best_score,
            "nodes": self.nodes,
            "pivots": self.pivots,
            "parallel_seeds": self.parallel_seeds,
        }


def _default_variants(base: Dict[str, Any], seeds: List[int]) -> List[Dict[str, Any]]:
    """从基础配置生成浅层变体（seed + 学习率/深度等）。"""
    variants = []
    lrs = base.get("learning_rates") or [base.get("learning_rate", 1e-3), 3e-4, 1e-4]
    for i, seed in enumerate(seeds):
        cfg = copy.deepcopy(base)
        cfg["seed"] = seed
        if i < len(lrs):
            cfg["learning_rate"] = lrs[i]
        cfg["variant_id"] = f"seed{seed}_lr{cfg.get('learning_rate')}"
        variants.append(cfg)
    return variants


def run_experiment_tree_search(
    base_config: Dict[str, Any],
    evaluate_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    *,
    beam_width: int = 3,
    max_depth: int = 2,
    seeds: Optional[List[int]] = None,
    pivot_on_failure: bool = True,
) -> ExperimentTreeResult:
    """同步浅树搜索。

    evaluate_fn(config) -> {success: bool, score: float, metrics: dict, error?: str}
    """
    seeds = seeds or [42, 43, 44][:beam_width]
    nodes: Dict[str, ExperimentNode] = {}
    pivots: List[Dict[str, Any]] = []

    root_id = f"node_{uuid.uuid4().hex[:8]}"
    root = ExperimentNode(
        node_id=root_id,
        parent_id=None,
        depth=0,
        config=dict(base_config),
        status="success",
        score=0.0,
    )
    nodes[root_id] = root

    frontier = [root_id]
    best_id, best_score = root_id, -1.0

    for depth in range(1, max_depth + 1):
        candidates: List[str] = []
        parent_configs = [nodes[pid].config for pid in frontier]
        # 对每个父节点扩展 seed 变体
        expansions: List[tuple] = []
        for pid in frontier:
            parent = nodes[pid]
            variants = _default_variants(parent.config, seeds)
            for cfg in variants[:beam_width]:
                expansions.append((pid, cfg))

        scored: List[ExperimentNode] = []
        for pid, cfg in expansions[: beam_width * max(1, len(frontier))]:
            nid = f"node_{uuid.uuid4().hex[:8]}"
            node = ExperimentNode(
                node_id=nid,
                parent_id=pid,
                depth=depth,
                config=cfg,
                status="running",
            )
            try:
                result = evaluate_fn(cfg) or {}
                ok = bool(result.get("success", True))
                score = float(result.get("score", 0.0))
                node.metrics = result.get("metrics") or {}
                node.score = score
                node.status = "success" if ok else "failed"
                node.error = result.get("error") or ""
                if not ok and pivot_on_failure:
                    # Pivot：降低 lr / 换 seed
                    pivot_cfg = copy.deepcopy(cfg)
                    pivot_cfg["learning_rate"] = float(cfg.get("learning_rate", 1e-3)) * 0.5
                    pivot_cfg["seed"] = int(cfg.get("seed", 42)) + 100
                    pivot_cfg["variant_id"] = f"pivot_{pivot_cfg['variant_id']}"
                    pivots.append({
                        "from": nid,
                        "reason": node.error or "eval failed",
                        "new_config": pivot_cfg,
                    })
                    try:
                        pr = evaluate_fn(pivot_cfg) or {}
                        if pr.get("success", False):
                            node.config = pivot_cfg
                            node.score = float(pr.get("score", 0.0))
                            node.metrics = pr.get("metrics") or {}
                            node.status = "success"
                            node.error = ""
                    except Exception as pexc:
                        logger.debug(f"pivot failed: {pexc}")
            except Exception as exc:
                node.status = "failed"
                node.error = str(exc)
                node.score = 0.0

            nodes[nid] = node
            nodes[pid].children.append(nid)
            scored.append(node)
            if node.status == "success" and node.score > best_score:
                best_score = node.score
                best_id = nid

        # beam prune
        scored.sort(key=lambda n: n.score, reverse=True)
        kept = scored[:beam_width]
        kept_ids = {n.node_id for n in kept}
        for n in scored:
            if n.node_id not in kept_ids:
                n.status = "pruned" if n.status == "success" else n.status
        frontier = [n.node_id for n in kept if n.status == "success"]
        if not frontier:
            break

    best = nodes.get(best_id)
    return ExperimentTreeResult(
        best_node_id=best_id,
        best_config=best.config if best else dict(base_config),
        best_score=best_score if best_score >= 0 else 0.0,
        nodes=[n.to_dict() for n in nodes.values()],
        pivots=pivots,
        parallel_seeds=list(seeds),
    )


def make_plan_evaluator_from_metrics(metrics_table: Dict[str, float]) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """用已有 metrics 表做伪评估（离线/测试用）。"""

    def _eval(cfg: Dict[str, Any]) -> Dict[str, Any]:
        key = cfg.get("variant_id") or str(cfg.get("seed"))
        score = float(metrics_table.get(key, metrics_table.get("default", 0.5)))
        # 惩罚极端 lr
        lr = float(cfg.get("learning_rate", 1e-3))
        if lr > 0.1 or lr < 1e-6:
            return {"success": False, "score": 0.0, "error": "lr out of range", "metrics": {}}
        return {"success": True, "score": score, "metrics": {"proxy_score": score}}

    return _eval
