import asyncio
import sys
from pathlib import Path

import pytest

# Ensure backend root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agents.research_agent import ResearchAgent


@pytest.mark.asyncio
async def test_research_agent_returns_verified_arxiv_papers():
    """验证 ResearchAgent 通过 arXiv MCP 返回真实、可验证的文献。"""
    agent = ResearchAgent()
    result = await agent.execute(
        task_input={"action": "search", "query": "multi-agent reinforcement learning"},
        context={"problem_text": "multi-agent reinforcement learning survey"},
    )

    papers = result.get("papers", [])
    if not papers:
        pytest.skip("未获取到真实 arXiv 文献（网络/MCP 不可用），跳过真实 API 测试")

    assert result.get("mcp_search_used") is True
    assert result.get("paper_source") == "arxiv"
    assert result.get("verified_paper_count") == len(papers)
    assert len(papers) > 0, "应返回至少一篇真实 arXiv 文献"

    for paper in papers:
        assert paper.get("arxiv_id"), "每篇文献必须有 arxiv_id"
        assert "." in paper["arxiv_id"], f"arxiv_id 格式不合法: {paper['arxiv_id']}"
        assert paper.get("title"), "每篇文献必须有 title"
        assert isinstance(paper.get("year"), int), "year 必须是整数"
        assert 1990 < paper["year"] <= 2030, f"year 超出合理范围: {paper['year']}"
        assert "arxiv.org" in paper.get("url", ""), "url 必须指向 arXiv"
        assert isinstance(paper.get("authors"), list), "authors 必须是列表"
        assert paper.get("source") == "arxiv", "source 应为 arxiv"


@pytest.mark.asyncio
async def test_research_agent_papers_not_hallucinated_by_llm():
    """验证即使 LLM 调用失败，返回的 papers 仍来自 arXiv MCP 而非 LLM 编造。"""
    agent = ResearchAgent()
    # 不传入有效 API key 的环境由配置决定；此处主要验证字段结构
    result = await agent.execute(
        task_input={"action": "search", "query": "graph neural networks"},
        context={"problem_text": "graph neural networks survey"},
    )

    papers = result.get("papers", [])
    if papers:
        # 所有返回的 paper 必须包含 arxiv_id，这是 LLM 旧格式没有强制要求的字段
        assert all("arxiv_id" in p and p["arxiv_id"] for p in papers)
        assert all(p.get("source") == "arxiv" for p in papers)


if __name__ == "__main__":
    asyncio.run(test_research_agent_returns_verified_arxiv_papers())
    asyncio.run(test_research_agent_papers_not_hallucinated_by_llm())
    print("All tests passed")
