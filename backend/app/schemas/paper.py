"""文献结构化模型"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Paper(BaseModel):
    """真实文献结构化模型（来源可扩展：arxiv / semantic_scholar / crossref 等）"""

    arxiv_id: str = Field(..., description="arXiv ID，如 2401.12345")
    title: str = Field(..., description="论文标题")
    authors: List[str] = Field(default_factory=list, description="作者列表")
    year: int = Field(default=0, description="发表年份")
    abstract: str = Field(default="", description="摘要")
    url: str = Field(..., description="论文页面 URL（arXiv 摘要页）")
    pdf_url: Optional[str] = Field(default=None, description="PDF 下载 URL")
    categories: List[str] = Field(default_factory=list, description="arXiv 分类或学科标签")
    published: Optional[str] = Field(default=None, description="发表日期 ISO 格式")
    source: str = Field(default="arxiv", description="来源：arxiv / semantic_scholar / crossref")
    search_query: Optional[str] = Field(default=None, description="记录检索关键词")

    # ===== Semantic Scholar 等外部源补充的元数据（全部可选） =====
    doi: Optional[str] = Field(default=None, description="DOI")
    citation_count: Optional[int] = Field(default=None, description="被引次数")
    reference_count: Optional[int] = Field(default=None, description="参考文献数量")
    influential_citation_count: Optional[int] = Field(default=None, description="高影响力被引次数")
    venue: Optional[str] = Field(default=None, description="期刊/会议名称")
    fields_of_study: List[str] = Field(default_factory=list, description="研究领域")
    publication_date: Optional[str] = Field(default=None, description="精确发表日期")
    s2_paper_id: Optional[str] = Field(default=None, description="Semantic Scholar paperId")
    s2_url: Optional[str] = Field(default=None, description="Semantic Scholar 页面 URL")
    tldr: Optional[str] = Field(default=None, description="AI 生成的短摘要")
    open_access_pdf: Optional[str] = Field(default=None, description="开放获取 PDF URL")
    metadata_sources: List[str] = Field(default_factory=list, description="补充过元数据的来源列表")

    # ===== 相关性评分与深度内容抽取（用于深度调研报告）=====
    relevance_score: Optional[float] = Field(default=None, description="与查询的相关性评分 0-100")
    extraction: Optional[dict] = Field(default=None, description="结构化内容抽取")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "arxiv_id": "2401.12345",
                "title": "Multi-Agent Reinforcement Learning: A Survey",
                "authors": ["Alice Smith", "Bob Jones"],
                "year": 2024,
                "abstract": "This paper surveys...",
                "url": "https://arxiv.org/abs/2401.12345",
                "pdf_url": "https://arxiv.org/pdf/2401.12345",
                "categories": ["cs.MA", "cs.LG"],
                "published": "2024-01-15",
                "source": "arxiv",
            }
        }
    )


class Citation(BaseModel):
    """引用条目（用于参考文献/BibTeX生成）"""

    id: str = Field(..., description="引用标识，如 Smith2024")
    title: str
    authors: List[str]
    year: int
    venue: Optional[str] = Field(default=None, description="期刊/会议")
    doi: Optional[str] = None
    url: Optional[str] = None
    arxiv_id: Optional[str] = None
    bibtex: Optional[str] = None


class LiteratureSearchResult(BaseModel):
    """文献检索结果聚合"""

    query: str
    papers: List[Paper] = Field(default_factory=list)
    total_found: int = 0
    source: str = "arxiv"
    search_time_ms: Optional[int] = None
