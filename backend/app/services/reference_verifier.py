"""参考文献双重验真 — API检索 + HTTP存在性验证

LLM最常编造的是不存在的论文（伪造作者、标题、DOI）。
本模块对每篇文献执行：
1. API验证：DOI → CrossRef；arXiv ID → arXiv API
2. HTTP存在性验证：确认URL可访问
3. 标题匹配验证：API返回标题 vs 论文标题相似度 > 0.8
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# 标题相似度阈值
TITLE_SIMILARITY_THRESHOLD = 0.8


@dataclass
class VerificationResult:
    """单篇文献验证结果"""
    verified: bool
    source: str  # "crossref" | "arxiv" | "semantic_scholar" | "http_check" | "skipped"
    title_match: float = 0.0  # 0-1
    url_accessible: bool = False
    api_title: str = ""
    error: Optional[str] = None


def _normalize_title(title: str) -> str:
    """标准化标题用于比较：小写、去标点、去多余空格"""
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _title_similarity(a: str, b: str) -> float:
    """简单标题相似度：基于token重叠的Jaccard相似度"""
    na = set(_normalize_title(a).split())
    nb = set(_normalize_title(b).split())
    if not na or not nb:
        return 0.0
    intersection = na & nb
    union = na | nb
    return len(intersection) / len(union)


async def _verify_doi(doi: str, client: httpx.AsyncClient) -> VerificationResult:
    """通过CrossRef API验证DOI"""
    try:
        url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            api_title = ""
            if "message" in data and "title" in data["message"]:
                titles = data["message"]["title"]
                if titles:
                    api_title = titles[0]
            return VerificationResult(
                verified=True,
                source="crossref",
                title_match=1.0,  # DOI匹配即视为标题匹配
                url_accessible=True,
                api_title=api_title,
            )
        elif resp.status_code == 404:
            return VerificationResult(verified=False, source="crossref", error="DOI不存在")
        else:
            return VerificationResult(verified=False, source="crossref", error=f"HTTP {resp.status_code}")
    except Exception as e:
        return VerificationResult(verified=False, source="crossref", error=str(e))


async def _verify_arxiv(arxiv_id: str, client: httpx.AsyncClient) -> VerificationResult:
    """通过arXiv API验证arXiv ID，失败时回退到Semantic Scholar"""
    clean_id = re.sub(r"v\d+$", "", arxiv_id.strip())

    # 尝试 arXiv API
    try:
        url = f"http://export.arxiv.org/api/query?id_list={clean_id}"
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            text = resp.text
            if "<entry>" in text:
                title_match = re.search(r"<title>(.*?)</title>", text, re.DOTALL)
                api_title = title_match.group(1).strip() if title_match else ""
                return VerificationResult(
                    verified=True, source="arxiv",
                    title_match=1.0, url_accessible=True, api_title=api_title,
                )
            else:
                return VerificationResult(verified=False, source="arxiv", error="arXiv ID不存在")
    except Exception:
        pass  # arXiv API 不可用，尝试 Semantic Scholar

    # 回退: Semantic Scholar
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{clean_id}?fields=title"
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            api_title = data.get("title", "")
            if api_title:
                return VerificationResult(
                    verified=True, source="semantic_scholar",
                    title_match=1.0, url_accessible=True, api_title=api_title,
                )
    except Exception:
        pass

    return VerificationResult(verified=False, source="arxiv", error="arXiv API和Semantic Scholar均不可用")


async def _verify_url(url: str, client: httpx.AsyncClient) -> VerificationResult:
    """HTTP HEAD请求验证URL存在性"""
    try:
        resp = await client.head(url, timeout=10.0, follow_redirects=True)
        accessible = resp.status_code < 400
        return VerificationResult(
            verified=accessible,
            source="http_check",
            url_accessible=accessible,
            error=None if accessible else f"HTTP {resp.status_code}",
        )
    except Exception as e:
        return VerificationResult(verified=False, source="http_check", error=str(e))


async def verify_reference(
    ref: Dict[str, Any],
    client: Optional[httpx.AsyncClient] = None,
    check_title: bool = True,
) -> VerificationResult:
    """验证单篇参考文献的真实性

    验证优先级：
    1. DOI → CrossRef API
    2. arXiv ID → arXiv API
    3. URL → HTTP HEAD
    """
    own_client = client is None
    if own_client:
        # 清除 SOCKS 代理（httpx 不支持）
        import os
        for var in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            if var in os.environ and "socks" in os.environ.get(var, "").lower():
                del os.environ[var]
        client = httpx.AsyncClient(
            headers={"User-Agent": "MathModel-System/1.0 (reference verification)"},
            follow_redirects=True,
            proxy=None,
        )

    try:
        doi = (ref.get("doi") or "").strip()
        arxiv_id = (ref.get("arxiv_id") or "").strip()
        url = (ref.get("url") or "").strip()
        title = (ref.get("title") or "").strip()

        # 1. DOI验证
        if doi:
            result = await _verify_doi(doi, client)
            if result.verified and check_title and title and result.api_title:
                result.title_match = _title_similarity(title, result.api_title)
                if result.title_match < TITLE_SIMILARITY_THRESHOLD:
                    result.verified = False
                    result.error = f"标题不匹配 (相似度={result.title_match:.2f}): API标题='{result.api_title}'"
            return result

        # 2. arXiv ID验证
        if arxiv_id:
            result = await _verify_arxiv(arxiv_id, client)
            if result.verified and check_title and title and result.api_title:
                result.title_match = _title_similarity(title, result.api_title)
                if result.title_match < TITLE_SIMILARITY_THRESHOLD:
                    result.verified = False
                    result.error = f"标题不匹配 (相似度={result.title_match:.2f}): API标题='{result.api_title}'"
            return result

        # 3. URL验证
        if url and url.startswith("http"):
            return await _verify_url(url, client)

        # 无可用验证信息
        return VerificationResult(
            verified=False,
            source="skipped",
            error="无DOI/arXiv ID/URL可供验证",
        )
    finally:
        if own_client:
            await client.aclose()


async def verify_all_references(
    refs: List[Dict[str, Any]],
    max_concurrent: int = 5,
    check_title: bool = True,
) -> List[VerificationResult]:
    """批量验证参考文献

    Args:
        refs: 参考文献列表
        max_concurrent: 最大并发验证数
        check_title: 是否检查标题匹配

    Returns:
        与refs对应的验证结果列表
    """
    if not refs:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded_verify(ref):
        async with semaphore:
            return await verify_reference(ref, check_title=check_title)

    # 清除 SOCKS 代理
    import os
    for var in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if var in os.environ and "socks" in os.environ.get(var, "").lower():
            del os.environ[var]

    async with httpx.AsyncClient(
        headers={"User-Agent": "MathModel-System/1.0 (reference verification)"},
        follow_redirects=True,
        proxy=None,
    ) as client:
        results = []
        for ref in refs:
            try:
                result = await verify_reference(ref, client=client, check_title=check_title)
                results.append(result)
            except Exception as e:
                results.append(VerificationResult(
                    verified=False, source="error", error=str(e)
                ))

    verified_count = sum(1 for r in results if r.verified)
    total_count = len(results)
    logger.info(f"[ReferenceVerifier] 验证完成: {verified_count}/{total_count} 通过")

    return results
