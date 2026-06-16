"""论文全文阅读管线 — 下载、解析、结构化抽取、分块索引、按需检索。"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..core.paths import get_project_base_dir
from ..core.knowledge_manager import (
    get_knowledge_manager,
    KnowledgeItem,
)
from ..services.pdf_processing import get_pdf_service
from ..services.pdf_processing.pdf_service import PdfProcessingService
from .paper_reading_config import PaperReadingConfig

logger = logging.getLogger(__name__)


DEFAULT_SECTION_PROMPT = """你是一位严谨的学术论文阅读助手。请仔细阅读下面的论文全文（Markdown 格式），提取出结构化信息。

要求：
1. 不要编造论文中没有的内容
2. 公式保留 LaTeX 格式
3. 方法部分要具体：算法名称、核心思想、输入输出、关键步骤
4. 实验部分要具体：数据集名称、评估指标、主要结果
5. 输出严格是 JSON，不要 Markdown 代码块

输出格式：
{
  "title": "论文标题",
  "authors": ["作者1", "作者2"],
  "abstract": "摘要",
  "sections": [
    {"name": "Introduction", "summary": "...", "key_points": ["..."]},
    {"name": "Methodology", "summary": "...", "key_points": ["..."], "pseudo_code": "...", "formulas": ["$...$"]},
    {"name": "Experiments", "summary": "...", "key_points": ["..."], "datasets": ["..."], "metrics": ["..."], "results": ["..."]},
    {"name": "Conclusion", "summary": "...", "key_points": ["..."], "limitations": ["..."]}
  ],
  "key_findings": ["发现1", "发现2"],
  "limitations": ["局限1"],
  "relevant_methods": [{"name": "...", "description": "..."}],
  "datasets_used": ["..."],
  "citation_count": 0
}

论文全文：
__PAPER_TEXT__
"""


@dataclass
class PaperReadingResult:
    """单篇论文阅读结果。"""
    arxiv_id: str = ""
    title: str = ""
    pdf_path: Optional[Path] = None
    markdown_path: Optional[Path] = None
    structured_path: Optional[Path] = None
    parse_success: bool = False
    extraction_success: bool = False
    structured: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


class PaperReader:
    """负责单篇论文的下载与解析。"""

    def __init__(self, config: Optional[PaperReadingConfig] = None):
        self.config = config or PaperReadingConfig()
        self.pdf_service: PdfProcessingService = get_pdf_service()

    def _get_references_dir(self, project_name: Optional[str]) -> Path:
        """获取项目参考文献目录。

        使用全局共享目录（不随 project_name 变化），避免同一论文在不同项目下重复下载。
        """
        base = get_project_base_dir(None)  # 始终用全局目录
        ref_dir = base / "global_references"
        ref_dir.mkdir(parents=True, exist_ok=True)
        return ref_dir

    def _clean_arxiv_id(self, arxiv_id: str) -> str:
        """清理 arxiv id，去掉版本后缀等。防路径遍历。

        arxiv id 格式为 YYMM.NNNNN[vN]，例如 2401.12345 或 2401.12345v2。
        """
        if not arxiv_id:
            return ""
        aid = arxiv_id.strip()
        # 去掉 .pdf 后缀
        if aid.lower().endswith(".pdf"):
            aid = aid[:-4]
        # 去掉 query 参数
        aid = aid.split("?")[0]
        # 去掉 arxiv.org/abs/ 前缀（取最后一段）
        aid = aid.split("/")[-1]
        # 仅保留合法字符：字母数字 + . + -
        import re
        aid = re.sub(r"[^a-zA-Z0-9.\-]", "", aid)
        # 防御性：禁止路径遍历
        if ".." in aid or aid.startswith(".") or aid == "":
            return ""
        # 验证 arxiv id 格式：YYMM.NNNNN[vN]
        if not re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", aid):
            return ""
        return aid

    def _get_pdf_url(self, paper: Dict[str, Any]) -> str:
        """从 paper 元数据中提取 PDF URL。"""
        pdf_url = paper.get("pdf_url", "")
        if pdf_url and pdf_url.startswith("http"):
            return pdf_url
        arxiv_id = self._clean_arxiv_id(paper.get("arxiv_id", ""))
        if arxiv_id:
            return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        url = paper.get("url", "")
        if "/abs/" in url:
            arxiv_id = url.split("/abs/")[-1].split("?")[0].strip()
            return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        return ""

    async def download(
        self,
        paper: Dict[str, Any],
        project_name: Optional[str] = None,
    ) -> Optional[Path]:
        """下载单篇论文 PDF，返回本地路径。"""
        arxiv_id = self._clean_arxiv_id(paper.get("arxiv_id", ""))
        if not arxiv_id:
            logger.warning("PaperReader: 缺少 arxiv_id，无法下载")
            return None

        ref_dir = self._get_references_dir(project_name)
        save_path = ref_dir / f"{arxiv_id}.pdf"
        if save_path.exists():
            logger.info(f"PaperReader: PDF 已存在 {save_path}")
            return save_path

        pdf_url = self._get_pdf_url(paper)
        if not pdf_url:
            logger.warning(f"PaperReader: 无法获取 PDF URL, arxiv_id={arxiv_id}")
            return None

        try:
            async with httpx.AsyncClient(timeout=self.config.download_timeout, follow_redirects=True) as client:
                resp = await client.get(pdf_url)
                resp.raise_for_status()
                content = resp.content
                if not content:
                    raise ValueError("下载内容为空")

            save_path.write_bytes(content)
            logger.info(f"PaperReader: 下载成功 {arxiv_id} -> {save_path} ({len(content)} bytes)")
            return save_path
        except Exception as e:
            logger.warning(f"PaperReader: 下载失败 {arxiv_id}: {e}")
            return None

    async def parse(
        self,
        pdf_path: Path,
        arxiv_id: str,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """解析 PDF，返回 markdown/text。"""
        try:
            # 优先走 PdfProcessingService（Phase 5 统一入口）
            result = await self.pdf_service.parse_file(
                file_path=Path(pdf_path),
                mode=self.config.parse_strategy,
            )
            return {
                "success": True,
                "text": result.text or "",
                "markdown": result.markdown or result.text or "",
                "page_contents": result.page_contents or [],
                "pages": result.pages,
                "method": getattr(result, "strategy", None) or getattr(result, "method", None) or "auto",
                "errors": result.errors or [],
            }
        except Exception as e:
            logger.warning(f"PaperReader: 解析失败 {arxiv_id}: {e}")
            return {"success": False, "error": str(e)}


class PaperSectionExtractor:
    """用 LLM 从论文 markdown 中提取结构化信息。"""

    def __init__(self, config: Optional[PaperReadingConfig] = None):
        self.config = config or PaperReadingConfig()

    def _estimate_tokens(self, text: str) -> int:
        return max(1, int(len(text) * 0.6))

    def _truncate_for_extraction(self, markdown: str, max_tokens: int = 20000) -> str:
        """如果论文太长，先截断到合理长度再做抽取。"""
        if self._estimate_tokens(markdown) <= max_tokens:
            return markdown
        # 优先保留前半部分（通常包含方法）和最后 10%（结论）
        cut = int(len(markdown) * 0.7)
        conclusion_start = int(len(markdown) * 0.85)
        truncated = markdown[:cut]
        if conclusion_start > cut:
            truncated += "\n\n...[中间内容省略]...\n\n" + markdown[conclusion_start:]
        return truncated

    async def extract(
        self,
        paper: Dict[str, Any],
        markdown: str,
        agent: Any,
    ) -> Dict[str, Any]:
        """调用 LLM 抽取论文结构。"""
        if not self.config.enable_structure_extraction:
            return {}

        truncated = self._truncate_for_extraction(markdown)
        prompt = DEFAULT_SECTION_PROMPT.replace("__PAPER_TEXT__", truncated)

        try:
            response = await agent.call_llm(
                messages=[
                    {"role": "system", "content": "You are an academic paper analysis assistant. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                context={},
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            result = agent.extract_json(content)
            if not result:
                return {}

            # 补全基础字段
            result.setdefault("title", paper.get("title", ""))
            result.setdefault("authors", paper.get("authors", []))
            result.setdefault("abstract", paper.get("abstract", ""))
            result.setdefault("arxiv_id", paper.get("arxiv_id", ""))
            return result
        except Exception as e:
            logger.warning(f"PaperSectionExtractor: 抽取失败 {paper.get('arxiv_id')}: {e}")
            return {}


class TaskKnowledgeBase:
    """任务级知识库 — 把论文 chunks 索引进去，供各 Agent 按需查询。"""

    def __init__(self, task_id: str, config: Optional[PaperReadingConfig] = None):
        self.task_id = task_id
        self.config = config or PaperReadingConfig()
        self.km = get_knowledge_manager()
        self.base_id: Optional[str] = None
        self._create()

    def _create(self):
        try:
            base = self.km.create_base(
                name=f"task_kb_{self.task_id}",
                description=f"Task-level paper reading KB for {self.task_id}",
            )
            self.base_id = base.id
            # 更新 chunk 配置
            base.chunkSize = self.config.chunk_size
            base.chunkOverlap = self.config.chunk_overlap
            base.embedding_model = {"type": self.config.embedding_type}
            logger.info(f"TaskKnowledgeBase: 创建任务级知识库 {self.base_id}")
        except Exception as e:
            logger.warning(f"TaskKnowledgeBase: 创建失败 {e}")

    def add_paper_chunks(
        self,
        arxiv_id: str,
        title: str,
        markdown: str,
        structured: Dict[str, Any],
    ):
        """把论文 markdown 分块加入知识库。"""
        if not self.base_id or not self.config.enable_chunk_indexing:
            return

        # 简单按段落分块
        chunks = self._split_markdown(markdown)
        paper_summary = structured.get("abstract", "")[:500] if structured else ""

        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            metadata = {
                "arxiv_id": arxiv_id,
                "title": title,
                "chunk_index": i,
                "paper_summary": paper_summary,
            }
            item = KnowledgeItem(
                id=f"{arxiv_id}_chunk_{i}",
                type="note",
                content=chunk,
                source=f"arxiv:{arxiv_id}",
                metadata=metadata,
            )
            try:
                self.km.add_item(self.base_id, item)
            except Exception as e:
                logger.warning(f"TaskKnowledgeBase: 添加 chunk 失败 {arxiv_id}:{i}: {e}")

    def _split_markdown(self, markdown: str) -> List[str]:
        """按标题和自然段落分块。"""
        # 按二级/三级标题分割
        parts = re.split(r'\n(?=##?\s)', markdown)
        chunks = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # 如果单段太长，再按段落切
            if len(part) > self.config.chunk_size * 3:
                sub_parts = part.split("\n\n")
                current = ""
                for sp in sub_parts:
                    if len(current) + len(sp) < self.config.chunk_size * 3:
                        current += "\n\n" + sp if current else sp
                    else:
                        if current:
                            chunks.append(current)
                        current = sp
                if current:
                    chunks.append(current)
            else:
                chunks.append(part)
        return chunks

    def query(self, query_text: str) -> str:
        """查询任务级知识库，返回格式化上下文。"""
        if not self.base_id or not self.config.enable_retrieval_reading:
            return ""
        try:
            return self.km.query_context(
                self.base_id,
                query_text,
                top_k=self.config.top_k_chunks,
                max_chars=self.config.max_chars_per_query,
            )
        except Exception as e:
            logger.warning(f"TaskKnowledgeBase: 查询失败 {e}")
            return ""

    def delete(self):
        """任务完成后删除临时知识库。"""
        if self.base_id:
            try:
                self.km.delete_base(self.base_id)
                logger.info(f"TaskKnowledgeBase: 删除 {self.base_id}")
            except Exception as e:
                logger.warning(f"TaskKnowledgeBase: 删除失败 {e}")


class PaperReadingPipeline:
    """论文阅读管线 orchestrator。"""

    def __init__(self, config: Optional[PaperReadingConfig] = None):
        self.config = config or PaperReadingConfig()
        self.reader = PaperReader(self.config)
        self.extractor = PaperSectionExtractor(self.config)

    def _get_reading_dir(self, project_name: Optional[str]) -> Path:
        base = get_project_base_dir(project_name)
        d = base / "reading"
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def process_papers(
        self,
        papers: List[Dict[str, Any]],
        project_name: Optional[str] = None,
        task_id: Optional[str] = None,
        agent: Any = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[TaskKnowledgeBase]]:
        """处理论文列表：下载→解析→抽取→索引。

        返回：
        - 带 reading_notes 的 papers 列表
        - 任务级知识库（如果 task_id 提供且索引开启）
        """
        if not self.config.enabled:
            return papers, None

        reading_dir = self._get_reading_dir(project_name)
        task_kb = TaskKnowledgeBase(task_id, self.config) if task_id and self.config.enable_chunk_indexing else None

        # 取 top_k 下载
        papers_to_read = papers[: self.config.max_download_papers]
        tasks = [self._process_one(p, project_name, reading_dir, task_kb, agent) for p in papers_to_read]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 把 reading_notes 合并回原始 papers
        reading_notes_map = {}
        for r in results:
            if isinstance(r, PaperReadingResult):
                reading_notes_map[r.arxiv_id] = {
                    "parse_success": r.parse_success,
                    "extraction_success": r.extraction_success,
                    "structured": r.structured,
                    "pdf_path": str(r.pdf_path) if r.pdf_path else None,
                    "markdown_path": str(r.markdown_path) if r.markdown_path else None,
                    "error": r.error,
                }
            elif isinstance(r, Exception):
                logger.warning(f"PaperReadingPipeline: 异常 {r}")

        for p in papers:
            aid = self.reader._clean_arxiv_id(p.get("arxiv_id", ""))
            if aid in reading_notes_map:
                p["reading_notes"] = reading_notes_map[aid]

        logger.info(f"PaperReadingPipeline: 完成 {len(reading_notes_map)} 篇处理")
        return papers, task_kb

    async def _process_one(
        self,
        paper: Dict[str, Any],
        project_name: Optional[str],
        reading_dir: Path,
        task_kb: Optional[TaskKnowledgeBase],
        agent: Any,
    ) -> PaperReadingResult:
        """处理单篇论文。"""
        arxiv_id = self.reader._clean_arxiv_id(paper.get("arxiv_id", ""))
        title = paper.get("title", "")
        result = PaperReadingResult(arxiv_id=arxiv_id, title=title)

        # 1. 下载
        pdf_path = await self.reader.download(paper, project_name)
        if not pdf_path:
            result.error = "下载失败或缺少 PDF URL"
            return result
        result.pdf_path = pdf_path

        # 2. 解析
        parse_res = await self.reader.parse(pdf_path, arxiv_id, project_name)
        if not parse_res.get("success"):
            result.error = parse_res.get("error", "解析失败")
            return result
        result.parse_success = True

        markdown = parse_res.get("markdown", "") or parse_res.get("text", "")
        if self.config.save_raw_markdown:
            md_path = reading_dir / f"{arxiv_id}.md"
            md_path.write_text(markdown, encoding="utf-8")
            result.markdown_path = md_path

        # 3. 结构化抽取
        if agent and self.config.enable_structure_extraction:
            structured = await self.extractor.extract(paper, markdown, agent)
            if structured:
                result.extraction_success = True
                result.structured = structured
                if self.config.save_structured_json:
                    json_path = reading_dir / f"{arxiv_id}.json"
                    json_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
                    result.structured_path = json_path

        # 4. 分块索引
        if task_kb and self.config.enable_chunk_indexing:
            task_kb.add_paper_chunks(arxiv_id, title, markdown, result.structured)

        return result


# 兼容 import
__all__ = [
    "PaperReadingConfig",
    "PaperReader",
    "PaperSectionExtractor",
    "TaskKnowledgeBase",
    "PaperReadingPipeline",
    "PaperReadingResult",
]
