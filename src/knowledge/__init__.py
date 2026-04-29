"""
知识库/RAG 模块
===============

借鉴 cherry-studio 的 Knowledge 架构设计，
为数学建模多Agent系统提供文档检索和知识增强能力。

核心组件:
- Document: 文档数据类
- EmbeddingModel: 嵌入模型 (支持 sentence-transformers / TF-IDF)
- DocumentChunker: 文档分块
- VectorStore: 向量存储与检索
- KnowledgeBase: 知识库 (封装上述组件)

使用方法:
    from src.knowledge import KnowledgeBase

    # 创建知识库
    kb = KnowledgeBase()

    # 添加文档
    kb.add_document("数学建模方法", "优化方法包括线性规划...")
    kb.add_document("算法设计", "遗传算法是一种启发式算法...")

    # 检索相关知识
    results = kb.query("如何设计优化算法？", top_k=3)
    for doc, score in results:
        print(f"[{score:.3f}] {doc.title}: {doc.content[:100]}")
"""

from .document import Document, DocumentChunker
from .embeddings import EmbeddingModel, SentenceTransformerEmbedding, TfidfEmbedding
from .vector_store import VectorStore
from .knowledge_base import KnowledgeBase

__all__ = [
    "Document",
    "DocumentChunker",
    "EmbeddingModel",
    "SentenceTransformerEmbedding",
    "TfidfEmbedding",
    "VectorStore",
    "KnowledgeBase",
]
