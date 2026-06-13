"""PDF 解析相关数据模型"""
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PdfSource(str, Enum):
    """PDF 来源"""
    UPLOAD = "upload"
    URL = "url"
    ARXIV = "arxiv"


class PdfParseStrategy(str, Enum):
    """PDF 解析策略"""
    AUTO = "auto"                 # 自动选择
    PYMUPDF4LLM = "pymupdf4llm"   # 保底文本提取
    MARKER = "marker"             # 英文公式/排版（需安装）
    MINERU = "mineru"             # 中文复杂版面（需安装）
    VISION = "vision"             # 多模态视觉辅助（限速、按页）


class PdfPageContent(BaseModel):
    """单页解析内容"""
    page_number: int = Field(..., ge=1, description="页码（从1开始）")
    text: str = Field(default="", description="文本内容")
    images: List[Dict[str, Any]] = Field(default_factory=list, description="页面内图片描述/路径")
    tables: List[Dict[str, Any]] = Field(default_factory=list, description="页面内表格数据")
    markdown: Optional[str] = Field(default=None, description="Markdown 格式内容")


class PdfParseResult(BaseModel):
    """PDF 解析结果"""
    file_id: str = Field(..., description="文件唯一ID")
    filename: str = Field(..., description="原始文件名")
    source: PdfSource = Field(..., description="来源")
    strategy: str = Field(default="auto", description="实际使用的解析策略")
    pages: int = Field(default=0, description="总页数")
    text: str = Field(default="", description="完整文本")
    markdown: Optional[str] = Field(default=None, description="完整 Markdown")
    page_contents: List[PdfPageContent] = Field(default_factory=list, description="逐页内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="PDF 元数据")
    errors: List[str] = Field(default_factory=list, description="解析过程中的警告/错误")
    parsed_at: Optional[float] = Field(default=None, description="解析时间戳")


class PdfFileInfo(BaseModel):
    """PDF 文件信息"""
    file_id: str
    filename: str
    size: int
    pages: Optional[int] = None
    source: PdfSource
    url: Optional[str] = None
    uploaded_at: float
    parsed: bool = False


class PdfParseRequest(BaseModel):
    """PDF 解析请求"""
    file_id: str
    strategy: PdfParseStrategy = PdfParseStrategy.AUTO
    pages: Optional[List[int]] = Field(default=None, description="指定页码，None 表示全部")
    use_vision: bool = Field(default=False, description="是否启用视觉辅助")
    vision_provider: Optional[str] = Field(default=None, description="视觉模型 provider ID，None 使用默认")
    vision_max_pages: int = Field(default=5, ge=1, le=20, description="视觉辅助最大页数（限速保护）")


class PdfDownloadRequest(BaseModel):
    """PDF 下载请求"""
    url: str = Field(..., description="PDF 下载链接或 arXiv ID/URL")
    filename: Optional[str] = Field(default=None, description="指定保存文件名")
    project_name: Optional[str] = Field(default=None, description="所属项目")


class PdfUploadResponse(BaseModel):
    """PDF 上传响应"""
    success: bool
    file_id: str
    filename: str
    size: int
    path: str


class PdfListResponse(BaseModel):
    """PDF 列表响应"""
    files: List[PdfFileInfo]
    total: int
