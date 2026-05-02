"""
算法知识库 (Algorithm Library)
============================
基于 https://github.com/HuangCongQing/Algorithms_MathModels 构建的
数学建模算法检索与推荐系统。

功能：
1. 加载算法索引 JSON
2. 基于关键词/问题描述检索相关算法
3. 生成算法推荐文本，供 LLM 建模时参考
4. 提供算法代码片段作为实现参考
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from difflib import SequenceMatcher


class AlgorithmLibrary:
    """
    数学建模算法知识库
    """

    def __init__(self, index_path: Optional[str] = None):
        if index_path is None:
            index_path = Path(__file__).parent / "algorithm_index.json"
        else:
            index_path = Path(index_path)

        self.index_path = index_path
        self.categories: List[Dict[str, Any]] = []
        self._tag_index: Dict[str, List[str]] = {}  # tag -> category_ids
        self._scenario_index: Dict[str, List[str]] = {}  # scenario keyword -> category_ids

        self._load_index()
        self._build_indices()

    def _load_index(self):
        """加载算法索引"""
        if not self.index_path.exists():
            raise FileNotFoundError(f"算法索引文件不存在: {self.index_path}")

        with open(self.index_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.categories = data.get("categories", [])
        self.meta = data.get("meta", {})
        print(f"[AlgorithmLibrary] 加载了 {len(self.categories)} 个算法类别")

    def _build_indices(self):
        """构建倒排索引，加速检索"""
        for cat in self.categories:
            cat_id = cat["id"]

            # 索引 tags
            for tag in cat.get("tags", []):
                self._tag_index.setdefault(tag, []).append(cat_id)

            # 索引适用场景
            for scenario in cat.get("applicable_scenarios", []):
                # 分词并索引每个关键词
                keywords = self._extract_keywords(scenario)
                for kw in keywords:
                    self._scenario_index.setdefault(kw, []).append(cat_id)

            # 索引子类型
            for subtype_name, subtype_desc in cat.get("subtypes", {}).items():
                keywords = self._extract_keywords(subtype_name + " " + subtype_desc)
                for kw in keywords:
                    self._scenario_index.setdefault(kw, []).append(cat_id)

    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        # 保留中文字符和英文单词
        chinese = re.findall(r'[一-鿿]+', text)
        english = re.findall(r'[a-zA-Z]+', text.lower())
        return chinese + english

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        基于问题描述检索相关算法

        Args:
            query: 问题描述或关键词
            top_k: 返回前 k 个最相关的算法

        Returns:
            相关算法列表，按相关度排序
        """
        query_keywords = self._extract_keywords(query)

        # 计算每个类别的匹配分数
        scores: Dict[str, float] = {}

        for cat in self.categories:
            cat_id = cat["id"]
            score = 0.0

            # 1. Tag 匹配（权重最高）
            for tag in cat.get("tags", []):
                for qk in query_keywords:
                    if qk in tag or tag in qk:
                        score += 3.0
                    elif SequenceMatcher(None, qk, tag).ratio() > 0.7:
                        score += 2.0

            # 2. 适用场景匹配
            for scenario in cat.get("applicable_scenarios", []):
                for qk in query_keywords:
                    if qk in scenario:
                        score += 1.5

            # 3. 描述文本匹配
            desc = cat.get("description", "")
            for qk in query_keywords:
                if qk in desc:
                    score += 1.0

            # 4. 子类型匹配
            for subtype_name, subtype_desc in cat.get("subtypes", {}).items():
                for qk in query_keywords:
                    if qk in subtype_name or qk in subtype_desc:
                        score += 2.0

            # 5. 名称匹配
            name_en = cat.get("name_en", "").lower()
            name_cn = cat.get("name_cn", "")
            for qk in query_keywords:
                if qk.lower() in name_en or qk in name_cn:
                    score += 2.5

            if score > 0:
                scores[cat_id] = score

        # 按分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        # 返回 top_k 结果
        results = []
        for cat_id in sorted_ids[:top_k]:
            cat = self._get_category_by_id(cat_id)
            if cat:
                cat_copy = dict(cat)
                cat_copy["relevance_score"] = round(scores[cat_id], 2)
                results.append(cat_copy)

        return results

    def _get_category_by_id(self, cat_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取类别"""
        for cat in self.categories:
            if cat["id"] == cat_id:
                return cat
        return None

    def get_algorithm_detail(self, cat_id: str) -> Optional[Dict[str, Any]]:
        """获取算法的详细信息"""
        return self._get_category_by_id(cat_id)

    def generate_recommendation_text(self, query: str, top_k: int = 3) -> str:
        """
        生成算法推荐文本，可直接注入 Prompt

        Args:
            query: 问题描述
            top_k: 推荐算法数量

        Returns:
            格式化的推荐文本
        """
        results = self.search(query, top_k=top_k)

        if not results:
            return ""

        lines = ["【算法库推荐】基于问题特征，以下算法可能适用：", ""]

        for i, algo in enumerate(results, 1):
            score = algo.get("relevance_score", 0)
            lines.append(f"{i}. {algo['name_cn']} ({algo['name_en']}) [相关度: {score}]")
            lines.append(f"   描述: {algo['description']}")
            lines.append(f"   适用场景: {', '.join(algo.get('applicable_scenarios', [])[:3])}")
            lines.append(f"   数学模型: {algo.get('mathematical_model', 'N/A')}")

            # 子类型
            subtypes = algo.get("subtypes", {})
            if subtypes:
                lines.append(f"   具体方法: {', '.join(subtypes.keys())}")

            # 优缺点
            advantages = algo.get("advantages", [])
            limitations = algo.get("limitations", [])
            if advantages:
                lines.append(f"   优点: {', '.join(advantages)}")
            if limitations:
                lines.append(f"   局限: {', '.join(limitations)}")

            # 代码片段
            snippets = algo.get("code_snippets", [])
            if snippets:
                lines.append(f"   参考代码文件: {', '.join(s['filename'] for s in snippets[:2])}")

            lines.append("")

        return "\n".join(lines)

    def get_code_reference(self, cat_id: str, filename: Optional[str] = None) -> Optional[str]:
        """
        获取算法的代码参考

        Args:
            cat_id: 算法类别 ID
            filename: 指定文件名，不指定则返回第一个

        Returns:
            代码片段字符串
        """
        cat = self._get_category_by_id(cat_id)
        if not cat:
            return None

        snippets = cat.get("code_snippets", [])
        if not snippets:
            return None

        if filename:
            for s in snippets:
                if s["filename"] == filename:
                    return s["snippet"]
            return None
        else:
            return snippets[0]["snippet"]

    def list_all_categories(self) -> List[str]:
        """列出所有算法类别"""
        return [cat["id"] for cat in self.categories]


# 全局单例
_algorithm_library_instance: Optional[AlgorithmLibrary] = None


def get_algorithm_library(index_path: Optional[str] = None) -> AlgorithmLibrary:
    """获取 AlgorithmLibrary 单例"""
    global _algorithm_library_instance
    if _algorithm_library_instance is None:
        _algorithm_library_instance = AlgorithmLibrary(index_path)
    return _algorithm_library_instance
