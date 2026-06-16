"""论文全文阅读管线配置。"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class PaperReadingConfig:
    """论文阅读管线配置。"""

    # 开关
    enabled: bool = True

    # 下载
    max_download_papers: int = 5
    download_timeout: float = 60.0
    download_strategy: str = "pdf_service"  # "pdf_service" | "mcp_arxiv_download"

    # 解析
    parse_strategy: str = "auto"  # "auto" | "pymupdf4llm" | "mineru" | "vision"
    auto_vision_page_threshold: int = 20
    auto_vision_size_threshold_mb: int = 5

    # 结构化抽取
    enable_structure_extraction: bool = True
    extraction_model: Optional[str] = None  # None 表示使用当前 provider 默认模型

    # 分块索引
    enable_chunk_indexing: bool = True
    chunk_size: int = 512
    chunk_overlap: int = 128
    embedding_type: str = "tfidf"  # "tfidf" | "openai" | "sentence_transformer"
    top_k_chunks: int = 5
    min_chunk_score: float = 0.1

    # 检索增强阅读
    enable_retrieval_reading: bool = True
    max_chars_per_query: int = 3000

    # 调试
    save_raw_markdown: bool = True
    save_structured_json: bool = True
