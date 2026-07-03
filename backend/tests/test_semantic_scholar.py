import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.paper_metadata import SemanticScholarProvider, get_metadata_enricher
from app.services.paper_metadata.semantic_scholar import RateLimitedError
from app.services.rate_limiter import AsyncTokenBucket


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch):
    """清除代理环境变量，避免 httpx 使用不支持的 SOCKS 代理。"""
    for var in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.asyncio
async def test_semantic_scholar_enrich_papers_returns_metadata():
    """验证 Semantic Scholar 能根据 arXiv ID 返回真实元数据。"""
    provider = SemanticScholarProvider()
    # 使用几篇知名论文的 arXiv ID
    arxiv_ids = ["1706.03762", "2203.08975"]

    try:
        results = await provider.enrich_papers(arxiv_ids)
    except RateLimitedError as e:
        pytest.skip(f"Semantic Scholar 限流，跳过真实 API 测试: {e}")

    assert isinstance(results, dict)
    assert len(results) > 0, "至少应返回一篇论文的元数据"

    for arxiv_id in arxiv_ids:
        if arxiv_id not in results:
            continue
        data = results[arxiv_id]
        assert data.get("s2_paper_id"), f"{arxiv_id} 应有 s2_paper_id"
        assert data.get("s2_url"), f"{arxiv_id} 应有 s2_url"
        assert isinstance(data.get("citation_count"), int), f"{arxiv_id} citation_count 应为整数"
        assert data["citation_count"] >= 0, f"{arxiv_id} citation_count 不应为负"
        assert data.get("venue") is None or isinstance(data["venue"], str)

    await provider.close()


@pytest.mark.asyncio
async def test_semantic_scholar_enrich_unknown_paper_returns_empty():
    """验证对不存在的 arXiv ID 返回空结果，不抛异常。"""
    provider = SemanticScholarProvider()
    results = await provider.enrich_papers(["9999.00000"])
    assert results == {}
    await provider.close()


@pytest.mark.asyncio
async def test_semantic_scholar_batch_splitting():
    """验证超过 BATCH_SIZE 的 ID 列表会自动分片。"""
    provider = SemanticScholarProvider()
    # 构造大量重复的已知 ID，测试分片逻辑
    base_id = "1706.03762"
    ids = [base_id] * 150

    try:
        results = await provider.enrich_papers(ids)
    except RateLimitedError as e:
        pytest.skip(f"Semantic Scholar 限流，跳过真实 API 测试: {e}")

    # 去重后应只剩一个
    assert base_id in results
    assert len(results) == 1
    await provider.close()


@pytest.mark.asyncio
async def test_async_token_bucket_limits_rate():
    """验证 AsyncTokenBucket 能限制请求速率。"""
    bucket = AsyncTokenBucket(rate=2.0, capacity=2.0)
    start = asyncio.get_event_loop().time()

    for _ in range(5):
        await bucket.acquire()

    elapsed = asyncio.get_event_loop().time() - start
    # 5 个 token @ 2 RPS，至少需要 (5-2)/2 = 1.5 秒
    assert elapsed >= 1.4, f"速率限制未生效，实际耗时 {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_get_metadata_enricher_registry():
    """验证注册表能正确返回 semantic_scholar provider。"""
    enricher = get_metadata_enricher("semantic_scholar")
    assert isinstance(enricher, SemanticScholarProvider)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
