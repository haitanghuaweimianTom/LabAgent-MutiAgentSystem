"""Semantic Scholar API 论文元数据增强 Provider"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from ...config import get_settings

from ..rate_limiter import AsyncTokenBucket
from .base import PaperMetadataProvider
from .registry import metadata_registry

logger = logging.getLogger(__name__)


class RateLimitedError(Exception):
    """Semantic Scholar API 请求被限流，且重试后仍失败。"""
    pass


@metadata_registry.register("semantic_scholar")
class SemanticScholarProvider(PaperMetadataProvider):
    """Semantic Scholar 元数据增强 Provider。

    通过 Semantic Scholar Graph API 批量查询论文元数据：
    - 被引次数（citationCount）
    - 参考文献数量（referenceCount）
    - 高影响力引用（influentialCitationCount）
    - 期刊/会议（venue）
    - DOI
    - 研究领域（fieldsOfStudy）
    - 精确发表日期（publicationDate）
    - TL;DR 短摘要
    - 开放获取 PDF

    官方文档：https://api.semanticscholar.org/api-docs/
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    BATCH_SIZE = 100
    DEFAULT_FIELDS = (
        "paperId,externalIds,title,authors,year,abstract,venue,fieldsOfStudy,"
        "publicationDate,citationCount,referenceCount,influentialCitationCount,"
        "openAccessPdf,tldr"
    )

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        if self.api_key is None:
            try:
                self.api_key = get_settings().semantic_scholar_api_key
            except Exception:
                self.api_key = None
        # 有 key: 1 RPS；无 key: 100/5min = 0.333 RPS
        rate = 1.0 if self.api_key else 0.333
        self.rate_limiter = AsyncTokenBucket(rate=rate)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=self._headers(),
            follow_redirects=True,
        )

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    @staticmethod
    def _normalize_arxiv_id(arxiv_id: str) -> str:
        """去掉 arXiv ID 的版本后缀，如 2203.08975v2 -> 2203.08975。"""
        if not arxiv_id:
            return arxiv_id
        # 去除前后空白，取 v 之前的部分
        base = arxiv_id.strip().split("v")[0]
        return base

    async def enrich_papers(self, arxiv_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量根据 arXiv ID 获取补充元数据。返回的 key 使用调用方传入的原始 arXiv ID。"""
        results: Dict[str, Dict[str, Any]] = {}
        if not arxiv_ids:
            return results

        # 去重并保持顺序；建立 base_id -> original_id 映射（多个原始 ID 可能映射到同一 base_id）
        base_to_originals: Dict[str, List[str]] = {}
        for aid in arxiv_ids:
            base = self._normalize_arxiv_id(aid)
            if not base:
                continue
            base_to_originals.setdefault(base, []).append(aid)

        unique_base_ids = list(base_to_originals.keys())

        for i in range(0, len(unique_base_ids), self.BATCH_SIZE):
            batch = unique_base_ids[i : i + self.BATCH_SIZE]
            batch_results = await self._batch_query(batch)
            # batch_results 的 key 是 base_id，转回原始 arxiv_id
            for base_id, data in batch_results.items():
                for original_id in base_to_originals.get(base_id, [base_id]):
                    results[original_id] = data

        return results

    async def _batch_query(self, arxiv_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """调用 POST /paper/batch，带速率限制和重试。"""
        ids = [f"ARXIV:{aid}" for aid in arxiv_ids]
        payload = {"ids": ids}
        url = f"{self.BASE_URL}/paper/batch"
        params = {"fields": self.DEFAULT_FIELDS}

        for attempt in range(3):
            await self.rate_limiter.acquire()
            try:
                resp = await self.client.post(url, params=params, json=payload)

                if resp.status_code == 429:
                    wait = 2 ** attempt * (5 if not self.api_key else 1)
                    logger.warning(f"Semantic Scholar rate limited, retry in {wait}s")
                    await asyncio.sleep(wait)
                    if attempt == 2:
                        raise RateLimitedError("Semantic Scholar API rate limited after retries")
                    continue

                resp.raise_for_status()
                papers = resp.json()
                return self._parse_papers(papers)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.warning("Semantic Scholar batch query returned 404")
                    return {}
                logger.warning(f"Semantic Scholar batch query failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"Semantic Scholar batch query error (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2 ** attempt)

        return {}

    def _parse_papers(self, papers: List[Optional[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        """解析 SS 返回的论文列表，返回 arxiv_id -> 元数据映射。"""
        results: Dict[str, Dict[str, Any]] = {}
        if not papers:
            return results

        for paper in papers:
            if not paper or not isinstance(paper, dict):
                continue

            external_ids = paper.get("externalIds") or {}
            arxiv_id = external_ids.get("ArXiv")
            if not arxiv_id:
                continue

            s2_paper_id = paper.get("paperId")
            tldr = paper.get("tldr")
            tldr_text = tldr.get("text") if isinstance(tldr, dict) else None

            open_access_pdf = paper.get("openAccessPdf")
            oa_pdf_url = open_access_pdf.get("url") if isinstance(open_access_pdf, dict) else None

            authors = paper.get("authors") or []
            author_names = [a["name"] for a in authors if isinstance(a, dict) and a.get("name")]

            results[arxiv_id] = {
                "doi": external_ids.get("DOI"),
                "s2_paper_id": s2_paper_id,
                "s2_url": f"https://www.semanticscholar.org/paper/{s2_paper_id}" if s2_paper_id else None,
                "citation_count": self._to_int(paper.get("citationCount")),
                "reference_count": self._to_int(paper.get("referenceCount")),
                "influential_citation_count": self._to_int(paper.get("influentialCitationCount")),
                "venue": paper.get("venue"),
                "fields_of_study": paper.get("fieldsOfStudy") or [],
                "publication_date": paper.get("publicationDate"),
                "tldr": tldr_text,
                "open_access_pdf": oa_pdf_url,
                # 以下字段仅当 SS 优于 arXiv 时使用，当前作为补充保留
                "ss_title": paper.get("title"),
                "ss_authors": author_names,
                "ss_year": self._to_int(paper.get("year")),
            }

        return results

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def search_papers(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """通过关键词搜索论文（暂未使用，保留扩展）。"""
        url = f"{self.BASE_URL}/paper/search"
        params = {
            "query": query,
            "fields": self.DEFAULT_FIELDS,
            "limit": limit,
            "offset": 0,
        }
        await self.rate_limiter.acquire()
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def get_related_papers(self, arxiv_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """获取与某篇 arXiv 论文相关的论文推荐。"""
        url = f"{self.BASE_URL}/paper/ARXIV:{arxiv_id}/related"
        params = {"fields": self.DEFAULT_FIELDS, "limit": limit}
        await self.rate_limiter.acquire()
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def close(self) -> None:
        await self.client.aclose()

    def __del__(self):
        try:
            asyncio.get_running_loop().create_task(self.close())
        except RuntimeError:
            pass
