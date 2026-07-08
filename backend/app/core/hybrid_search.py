"""混合检索引擎 — 语义 + BM25 混合搜索

参照 LlamaIndex EnsembleRetriever 和 CrewAI 检索模式，
支持：
- 语义检索（sentence-transformers）
- BM25 关键词检索
- 混合融合（Reciprocal Rank Fusion）
- 来源追踪（provenance tracking）
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果"""
    content: str
    score: float
    source: str = ""
    title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    retrieval_method: str = ""  # "semantic", "bm25", "hybrid"
    chunk_id: str = ""


class HybridSearchEngine:
    """混合检索引擎
    
    结合语义检索和 BM25 关键词检索，使用 RRF (Reciprocal Rank Fusion) 融合结果。
    """
    
    def __init__(
        self,
        semantic_weight: float = 0.6,
        bm25_weight: float = 0.4,
        use_reranker: bool = False,
        reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ):
        self.semantic_weight = semantic_weight
        self.bm25_weight = bm25_weight
        self.use_reranker = use_reranker
        self.reranker_model_name = reranker_model
        
        self._semantic_model = None
        self._reranker = None
        self._bm25_index = None
        self._documents: List[Dict[str, Any]] = []
        self._doc_embeddings: Optional[np.ndarray] = None
    
    def _ensure_models(self):
        """延迟加载模型"""
        if self._semantic_model is None:
            try:
                # 清除 SOCKS 代理（sentence-transformers 不支持）
                import os
                for var in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
                    if var in os.environ and "socks" in os.environ[var].lower():
                        del os.environ[var]

                from sentence_transformers import SentenceTransformer
                self._semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("[HybridSearch] 语义模型已加载")
            except Exception as e:
                logger.warning(f"[HybridSearch] 语义模型加载失败: {e}")
        
        if self.use_reranker and self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                self._reranker = CrossEncoder(self.reranker_model_name)
                logger.info("[HybridSearch] 重排序模型已加载")
            except Exception as e:
                logger.warning(f"[HybridSearch] 重排序模型加载失败: {e}")
    
    def add_documents(self, documents: List[Dict[str, Any]]):
        """添加文档到索引
        
        documents: [{"content": str, "metadata": dict, "title": str, "source": str}]
        """
        self._documents.extend(documents)
        self._build_indices()
    
    def _build_indices(self):
        """构建检索索引"""
        self._ensure_models()
        
        # 构建 BM25 索引
        self._build_bm25_index()
        
        # 构建语义索引
        self._build_semantic_index()
    
    def _build_bm25_index(self):
        """构建 BM25 索引"""
        try:
            from rank_bm25 import BM25Okapi
            
            # 分词
            tokenized_docs = []
            for doc in self._documents:
                text = doc.get("content", "")
                # 简单分词：按空格和标点分割
                tokens = re.findall(r'\w+', text.lower())
                tokenized_docs.append(tokens)
            
            self._bm25_index = BM25Okapi(tokenized_docs)
            logger.info(f"[HybridSearch] BM25 索引已构建: {len(self._documents)} 文档")
        except ImportError:
            logger.warning("[HybridSearch] rank_bm25 未安装，跳过 BM25 索引")
        except Exception as e:
            logger.warning(f"[HybridSearch] BM25 索引构建失败: {e}")
    
    def _build_semantic_index(self):
        """构建语义索引"""
        if self._semantic_model is None:
            return
        
        try:
            texts = [doc.get("content", "") for doc in self._documents]
            self._doc_embeddings = self._semantic_model.encode(texts, show_progress_bar=False)
            logger.info(f"[HybridSearch] 语义索引已构建: {len(self._documents)} 文档")
        except Exception as e:
            logger.warning(f"[HybridSearch] 语义索引构建失败: {e}")
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """混合搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数
            min_score: 最低分数阈值
        
        Returns:
            搜索结果列表
        """
        if not self._documents:
            return []
        
        results = []
        
        # 1. BM25 搜索
        bm25_results = self._search_bm25(query, top_k=top_k * 2)
        
        # 2. 语义搜索
        semantic_results = self._search_semantic(query, top_k=top_k * 2)
        
        # 3. 融合结果
        if bm25_results and semantic_results:
            results = self._rrf_fusion(bm25_results, semantic_results, top_k=top_k)
        elif bm25_results:
            results = bm25_results[:top_k]
        elif semantic_results:
            results = semantic_results[:top_k]
        
        # 4. 过滤低分结果
        results = [r for r in results if r.score >= min_score]
        
        # 5. 重排序（可选）
        if self.use_reranker and self._reranker and results:
            results = self._rerank(query, results, top_k=top_k)
        
        return results[:top_k]
    
    def _search_bm25(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """BM25 搜索"""
        if self._bm25_index is None:
            return []
        
        try:
            # 分词
            query_tokens = re.findall(r'\w+', query.lower())
            
            # 搜索
            scores = self._bm25_index.get_scores(query_tokens)
            
            # 获取 top-k
            top_indices = np.argsort(scores)[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                if scores[idx] > 0:
                    doc = self._documents[idx]
                    results.append(SearchResult(
                        content=doc.get("content", ""),
                        score=float(scores[idx]),
                        source=doc.get("source", ""),
                        title=doc.get("title", ""),
                        metadata=doc.get("metadata", {}),
                        retrieval_method="bm25",
                        chunk_id=str(idx),
                    ))
            
            return results
        except Exception as e:
            logger.warning(f"[HybridSearch] BM25 搜索失败: {e}")
            return []
    
    def _search_semantic(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """语义搜索"""
        if self._semantic_model is None or self._doc_embeddings is None:
            return []
        
        try:
            # 编码查询
            query_embedding = self._semantic_model.encode([query], show_progress_bar=False)
            
            # 计算相似度
            similarities = np.dot(self._doc_embeddings, query_embedding.T).flatten()
            
            # 获取 top-k
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                if similarities[idx] > 0:
                    doc = self._documents[idx]
                    results.append(SearchResult(
                        content=doc.get("content", ""),
                        score=float(similarities[idx]),
                        source=doc.get("source", ""),
                        title=doc.get("title", ""),
                        metadata=doc.get("metadata", {}),
                        retrieval_method="semantic",
                        chunk_id=str(idx),
                    ))
            
            return results
        except Exception as e:
            logger.warning(f"[HybridSearch] 语义搜索失败: {e}")
            return []
    
    def _rrf_fusion(
        self,
        bm25_results: List[SearchResult],
        semantic_results: List[SearchResult],
        top_k: int,
        k: int = 60,
    ) -> List[SearchResult]:
        """Reciprocal Rank Fusion 融合"""
        # 合并分数
        score_map: Dict[str, float] = {}
        result_map: Dict[str, SearchResult] = {}
        
        # BM25 分数
        for rank, result in enumerate(bm25_results):
            key = result.chunk_id
            rrf_score = self.bm25_weight / (k + rank + 1)
            score_map[key] = score_map.get(key, 0) + rrf_score
            result_map[key] = result
        
        # 语义分数
        for rank, result in enumerate(semantic_results):
            key = result.chunk_id
            rrf_score = self.semantic_weight / (k + rank + 1)
            score_map[key] = score_map.get(key, 0) + rrf_score
            if key not in result_map:
                result_map[key] = result
        
        # 排序
        sorted_keys = sorted(score_map.keys(), key=lambda k: score_map[k], reverse=True)
        
        results = []
        for key in sorted_keys[:top_k]:
            result = result_map[key]
            result.score = score_map[key]
            result.retrieval_method = "hybrid"
            results.append(result)
        
        return results
    
    def _rerank(
        self,
        query: str,
        results: List[SearchResult],
        top_k: int,
    ) -> List[SearchResult]:
        """使用 Cross-encoder 重排序"""
        if not self._reranker or not results:
            return results
        
        try:
            # 准备文本对
            pairs = [(query, r.content[:512]) for r in results]
            
            # 重排序
            scores = self._reranker.predict(pairs)
            
            # 更新分数
            for result, score in zip(results, scores):
                result.score = float(score)
            
            # 重新排序
            results.sort(key=lambda r: r.score, reverse=True)
            
            return results[:top_k]
        except Exception as e:
            logger.warning(f"[HybridSearch] 重排序失败: {e}")
            return results


def create_hybrid_search_engine(
    semantic_weight: float = 0.6,
    bm25_weight: float = 0.4,
    use_reranker: bool = False,
) -> HybridSearchEngine:
    """创建混合检索引擎实例"""
    return HybridSearchEngine(
        semantic_weight=semantic_weight,
        bm25_weight=bm25_weight,
        use_reranker=use_reranker,
    )
