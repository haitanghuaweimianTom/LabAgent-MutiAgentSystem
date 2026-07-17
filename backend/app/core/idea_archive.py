"""Idea Archive - 跨 run 的想法库 + 近重复新颖性检查 + GPU 价值 HITL 闸门。

v8.1: 实现科学家闭环的关键组件：
1. 跨 run 的想法库（持久化存储）
2. 近重复新颖性检查（基于标题/摘要/方法的相似度）
3. GPU 价值 HITL 闸门（评估是否值得烧 GPU）

参考：Sakana AI Scientist v2 的 Idea Archive 机制。
"""
from __future__ import annotations

import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class IdeaArchive:
    """跨 run 的想法库，支持近重复检查和 GPU 价值评估。"""

    def __init__(self, archive_dir: Optional[Path] = None):
        """初始化 Idea Archive。

        Args:
            archive_dir: 存储目录，默认为 ~/.mathmodel/idea_archive/
        """
        if archive_dir is None:
            archive_dir = Path.home() / ".mathmodel" / "idea_archive"
        self.archive_dir = archive_dir
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # 主索引文件
        self.index_file = self.archive_dir / "index.json"
        self.ideas: List[Dict[str, Any]] = self._load_index()

    def _load_index(self) -> List[Dict[str, Any]]:
        """加载想法索引。"""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load idea archive index: {e}")
        return []

    def _save_index(self) -> None:
        """保存想法索引。"""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.ideas, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save idea archive index: {e}")

    def _compute_idea_hash(self, idea: Dict[str, Any]) -> str:
        """计算想法的哈希值，用于去重。"""
        # 基于标题、方法、创新点计算哈希
        key_parts = [
            idea.get("title", ""),
            idea.get("methodology", ""),
            idea.get("novelty", ""),
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode("utf-8")).hexdigest()

    def add_idea(
        self,
        idea: Dict[str, Any],
        task_id: str,
        source: str = "innovation_agent",
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """添加新想法到 archive。

        Args:
            idea: 创新点（来自 innovation_agent）
            task_id: 产生该想法的任务 ID
            source: 来源 Agent
            metrics: 实验指标（如果有）

        Returns:
            包含 idea_id、hash、novelty_score 的元数据
        """
        idea_id = len(self.ideas) + 1
        idea_hash = self._compute_idea_hash(idea)

        # 近重复检查
        duplicates = self.check_near_duplicates(idea)
        novelty_score = self._compute_novelty_score(idea, duplicates)

        # GPU 价值评估
        gpu_value = self._evaluate_gpu_value(idea, metrics)

        record = {
            "idea_id": idea_id,
            "hash": idea_hash,
            "title": idea.get("title", ""),
            "novelty": idea.get("novelty", ""),
            "methodology": idea.get("methodology", ""),
            "expected_contribution": idea.get("expected_contribution", ""),
            "feasibility": idea.get("feasibility", "medium"),
            "risks": idea.get("risks", ""),
            "related_gaps": idea.get("related_gaps", []),
            "task_id": task_id,
            "source": source,
            "created_at": datetime.now().isoformat(),
            "novelty_score": novelty_score,
            "gpu_value": gpu_value,
            "duplicate_ids": [d["idea_id"] for d in duplicates],
            "status": "new",  # new | running | completed | failed | archived
        }

        self.ideas.append(record)
        self._save_index()

        logger.info(
            f"Idea Archive: added idea {idea_id} (hash={idea_hash[:8]}, "
            f"novelty_score={novelty_score:.2f}, gpu_value={gpu_value})"
        )

        return {
            "idea_id": idea_id,
            "hash": idea_hash,
            "novelty_score": novelty_score,
            "gpu_value": gpu_value,
            "is_duplicate": len(duplicates) > 0,
        }

    def check_near_duplicates(
        self,
        idea: Dict[str, Any],
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """检查近重复想法。

        Args:
            idea: 新想法
            threshold: 相似度阈值（0-1）

        Returns:
            相似的想法列表
        """
        duplicates = []
        new_title = idea.get("title", "").lower()
        new_method = idea.get("methodology", "").lower()
        new_novelty = idea.get("novelty", "").lower()

        for existing in self.ideas:
            # 计算相似度
            similarity = self._compute_similarity(
                new_title, new_method, new_novelty,
                existing.get("title", "").lower(),
                existing.get("methodology", "").lower(),
                existing.get("novelty", "").lower(),
            )

            if similarity >= threshold:
                duplicates.append({
                    "idea_id": existing["idea_id"],
                    "title": existing.get("title", ""),
                    "similarity": similarity,
                })

        return duplicates

    def _compute_similarity(
        self,
        title1: str, method1: str, novelty1: str,
        title2: str, method2: str, novelty2: str,
    ) -> float:
        """计算两个想法的相似度。

        使用简单的关键词匹配 + Jaccard 相似度。
        """
        def tokenize(text: str) -> set:
            # 简单分词：按空格和标点分割
            import re
            tokens = re.findall(r'\w+', text.lower())
            return set(tokens)

        # 标题相似度
        title_sim = self._jaccard_similarity(tokenize(title1), tokenize(title2))

        # 方法相似度
        method_sim = self._jaccard_similarity(tokenize(method1), tokenize(method2))

        # 新颖性相似度
        novelty_sim = self._jaccard_similarity(tokenize(novelty1), tokenize(novelty2))

        # 加权平均
        return 0.4 * title_sim + 0.4 * method_sim + 0.2 * novelty_sim

    def _jaccard_similarity(self, set1: set, set2: set) -> float:
        """计算 Jaccard 相似度。"""
        if not set1 and not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _compute_novelty_score(
        self,
        idea: Dict[str, Any],
        duplicates: List[Dict[str, Any]],
    ) -> float:
        """计算新颖性分数（0-1）。

        基于：
        1. 与已有想法的重复程度
        2. 创新点描述的独特性
        """
        if duplicates:
            # 有重复时，根据最高相似度降低分数
            max_sim = max(d["similarity"] for d in duplicates)
            return max(0.0, 1.0 - max_sim)

        # 无重复时，基于创新点描述计算
        novelty_text = idea.get("novelty", "")
        if not novelty_text:
            return 0.5

        # 简单启发式：包含"首次"、"novel"、"new"等词汇加分
        novelty_keywords = ["首次", "novel", "new", "创新", "原创", "突破"]
        bonus = sum(0.1 for kw in novelty_keywords if kw.lower() in novelty_text.lower())

        return min(1.0, 0.7 + bonus)

    def _evaluate_gpu_value(
        self,
        idea: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
    ) -> str:
        """评估 GPU 价值，决定是否值得烧 GPU。

        Returns:
            "high" — 值得烧 GPU
            "medium" — 可以尝试
            "low" — 不值得
        """
        # 基于可行性评估
        feasibility = idea.get("feasibility", "medium")
        if feasibility == "high":
            base_value = "high"
        elif feasibility == "medium":
            base_value = "medium"
        else:
            base_value = "low"

        # 基于预期贡献调整
        contribution = idea.get("expected_contribution", "").lower()
        high_value_keywords = ["显著提升", "突破性", "state-of-the-art", "sota", "大幅提升"]
        low_value_keywords = ["小幅", "微调", "minor", "incremental"]

        for kw in high_value_keywords:
            if kw in contribution:
                if base_value == "medium":
                    base_value = "high"
                break

        for kw in low_value_keywords:
            if kw in contribution:
                if base_value == "high":
                    base_value = "medium"
                break

        # 基于已有指标调整（如果有）
        if metrics:
            # 如果已经有正向指标，说明值得继续
            if metrics.get("improvement", 0) > 0.05:  # 改进超过 5%
                base_value = "high"

        return base_value

    def get_ideas_by_status(self, status: str) -> List[Dict[str, Any]]:
        """按状态筛选想法。"""
        return [idea for idea in self.ideas if idea.get("status") == status]

    def get_idea(self, idea_id: int) -> Optional[Dict[str, Any]]:
        """获取指定想法。"""
        for idea in self.ideas:
            if idea.get("idea_id") == idea_id:
                return idea
        return None

    def update_idea_status(self, idea_id: int, status: str, metrics: Optional[Dict[str, Any]] = None) -> bool:
        """更新想法状态。"""
        idea = self.get_idea(idea_id)
        if not idea:
            return False

        idea["status"] = status
        if metrics:
            idea["metrics"] = metrics
        idea["updated_at"] = datetime.now().isoformat()

        self._save_index()
        return True

    def get_stats(self) -> Dict[str, Any]:
        """获取 archive 统计信息。"""
        total = len(self.ideas)
        by_status = {}
        by_gpu_value = {"high": 0, "medium": 0, "low": 0}

        for idea in self.ideas:
            status = idea.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1

            gpu_value = idea.get("gpu_value", "medium")
            by_gpu_value[gpu_value] = by_gpu_value.get(gpu_value, 0) + 1

        return {
            "total_ideas": total,
            "by_status": by_status,
            "by_gpu_value": by_gpu_value,
            "avg_novelty_score": (
                sum(i.get("novelty_score", 0) for i in self.ideas) / total
                if total > 0 else 0
            ),
        }

    def get_top_ideas(self, n: int = 5, min_novelty: float = 0.6) -> List[Dict[str, Any]]:
        """获取 top-n 新颖性想法。"""
        filtered = [
            idea for idea in self.ideas
            if idea.get("novelty_score", 0) >= min_novelty
        ]
        filtered.sort(key=lambda x: x.get("novelty_score", 0), reverse=True)
        return filtered[:n]


# 全局单例
_archive_instance: Optional[IdeaArchive] = None


def get_idea_archive() -> IdeaArchive:
    """获取全局 Idea Archive 实例。"""
    global _archive_instance
    if _archive_instance is None:
        _archive_instance = IdeaArchive()
    return _archive_instance
