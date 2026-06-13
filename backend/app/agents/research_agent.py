"""研究Agent - 搜集相关资料、文献、数据

支持：
- 普通文献搜索（LLM 生成）
- 深度研究模式（多轮搜索 + MCP 工具真实检索）
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)


@AgentFactory.register("research_agent")
class ResearchAgent(BaseAgent):
    name = "research_agent"
    label = "研究员"
    description = "搜集相关资料、文献、数据"
    default_model = ""

    def get_system_prompt(self, action: str = "search") -> str:
        if action == "search_background":
            return """你是一个专业的研究助手，专门搜集问题的背景信息和最新趋势。
职责：
1. 搜索问题的历史背景和发展脉络
2. 查找最新的研究趋势和热点
3. 搜集权威来源的背景资料

输出格式（严格JSON）：
{
    "papers": [{"arxiv_id": "", "title": "", "authors": [""], "year": 0, "abstract": "", "url": ""}],
    "trends": ["趋势1", "趋势2"],
    "background_summary": "背景综述",
    "summary": ""
}

格式要求：
- 英文内容使用英文双引号 "" 和单引号 ''
- 中文内容使用中文双引号 "" 和单引号 ''
- 论文标题中的专有名词、术语需使用正确的引号格式
"""
        elif action == "search_methods":
            return """你是一个专业的研究助手，专门搜集数学模型、算法和解决方法。
职责：
1. 搜索相关的数学模型和算法
2. 查找类似问题的解决方法
3. 搜集公开数据集和基准测试

输出格式（严格JSON）：
{
    "methods": [{"name": "", "description": "", "paper": ""}],
    "datasets": [{"name": "", "source": "", "description": ""}],
    "model_summary": "方法综述",
    "summary": ""
}

格式要求：
- 英文内容使用英文双引号 "" 和单引号 ''
- 中文内容使用中文双引号 "" 和单引号 ''
- 方法名称、论文标题中的专有名词需使用正确的引号格式
"""
        return """你是一个专业的研究助手，专门为数学建模问题搜集相关资料。
职责：
1. 搜索相关学术文献
2. 查找相关数学模型和算法
3. 搜集相关公开数据集
4. 整理归纳搜索结果

输出格式（严格JSON）：
{
    "papers": [{"arxiv_id": "", "title": "", "authors": [""], "year": 0, "abstract": "", "url": ""}],
    "datasets": [{"name": "", "source": "", "description": ""}],
    "methods": [{"name": "", "description": "", "paper": ""}],
    "summary": ""
}

格式要求：
- 英文内容使用英文双引号 "" 和单引号 ''
- 中文内容使用中文双引号 "" 和单引号 ''
- 论文标题中的专有名词、术语需使用正确的引号格式
"""

    def _infer_arxiv_categories(self, query: str) -> List[str]:
        """根据查询关键词推断相关 arXiv 分类，提高检索相关性。"""
        q = query.lower()
        categories = []
        if any(k in q for k in ["multi-agent", "multi agent", "agent", "reinforcement learning", "rl", "mdp", "game theory"]):
            categories.extend(["cs.MA", "cs.AI", "cs.LG"])
        if any(k in q for k in ["nlp", "language model", "transformer", "llm", "bert", "gpt", "attention"]):
            categories.extend(["cs.CL", "cs.LG", "cs.AI"])
        if any(k in q for k in ["vision", "image", "cnn", "detection", "segmentation", "diffusion"]):
            categories.extend(["cs.CV", "cs.LG"])
        if any(k in q for k in ["optimization", "linear programming", "integer programming", "scheduling", "routing", "knapsack", "math model", "operations research"]):
            categories.extend(["math.OC", "cs.DS", "cs.AI"])
        if any(k in q for k in ["statistics", "regression", "classification", "clustering", "time series", "forecast", "machine learning"]):
            categories.extend(["stat.ML", "cs.LG", "stat.AP"])
        if any(k in q for k in ["graph", "network", "gnn", "topology"]):
            categories.extend(["cs.SI", "cs.LG", "cs.AI"])
        if not categories:
            categories = ["cs.AI", "cs.LG"]
        # 去重并保持顺序
        return list(dict.fromkeys(categories))

    def _parse_arxiv_papers(self, raw_result: Any, query: str = "") -> List[Dict[str, Any]]:
        """解析 arxiv_server MCP 返回结果，提取结构化 Paper 列表。

        返回字段与 backend/app/schemas/paper.py 中的 Paper 模型对齐。
        """
        papers: List[Dict[str, Any]] = []
        if not raw_result:
            return papers

        text = raw_result.strip() if isinstance(raw_result, str) else ""
        if not text:
            return papers

        # 去除可能的 markdown code block 包装
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end <= start:
                logger.warning("arXiv MCP result is not valid JSON")
                return papers
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                logger.warning("Failed to extract JSON from arXiv MCP result")
                return papers

        if not isinstance(data, dict):
            logger.warning("arXiv MCP result is not a JSON object")
            return papers

        raw_papers = data.get("papers", [])
        if not isinstance(raw_papers, list):
            logger.warning("arXiv MCP result 'papers' field is not a list")
            return papers

        for rp in raw_papers:
            if not isinstance(rp, dict):
                continue
            arxiv_id = rp.get("id", "").strip()
            if not arxiv_id:
                continue

            published = rp.get("published", "")
            year = 0
            if published and len(published) >= 4:
                try:
                    year = int(published[:4])
                except ValueError:
                    year = 0

            abstract = rp.get("abstract", "")
            if abstract.startswith("[EXTERNAL CONTENT] "):
                abstract = abstract[len("[EXTERNAL CONTENT] "):]

            authors = rp.get("authors", [])
            if not isinstance(authors, list):
                authors = [str(authors)] if authors else []

            categories = rp.get("categories", [])
            if not isinstance(categories, list):
                categories = [str(categories)] if categories else []

            url = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = rp.get("url", "")
            if pdf_url and not pdf_url.startswith("http"):
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

            papers.append({
                "arxiv_id": arxiv_id,
                "title": rp.get("title", "").strip(),
                "authors": authors,
                "year": year,
                "abstract": abstract.strip(),
                "url": url,
                "pdf_url": pdf_url,
                "categories": categories,
                "published": published,
                "source": "arxiv",
                "search_query": query,
            })

        logger.info(f"Parsed {len(papers)} verified papers from arXiv MCP (query='{query[:60]}')")
        return papers

    async def _enrich_with_semantic_scholar(
        self, papers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """用 Semantic Scholar 批量增强论文元数据。失败时返回原始数据，不影响主流程。"""
        if not papers:
            return papers

        try:
            from ..services.paper_metadata import get_metadata_enricher

            enricher = get_metadata_enricher("semantic_scholar")
            arxiv_ids = [p["arxiv_id"] for p in papers if p.get("arxiv_id")]
            if not arxiv_ids:
                return papers

            logger.info(f"Enriching {len(arxiv_ids)} papers with Semantic Scholar")
            enrichments = await asyncio.wait_for(
                enricher.enrich_papers(arxiv_ids),
                timeout=15.0,
            )
            logger.info(f"Semantic Scholar returned enrichment for {len(enrichments)} papers")

            for paper in papers:
                arxiv_id = paper.get("arxiv_id")
                if not arxiv_id or arxiv_id not in enrichments:
                    continue

                ss_data = enrichments[arxiv_id]
                # 仅补充字段，不覆盖 arXiv 核心字段
                for key in [
                    "doi",
                    "citation_count",
                    "reference_count",
                    "influential_citation_count",
                    "venue",
                    "fields_of_study",
                    "publication_date",
                    "s2_paper_id",
                    "s2_url",
                    "tldr",
                    "open_access_pdf",
                ]:
                    if ss_data.get(key) is not None and paper.get(key) is None:
                        paper[key] = ss_data[key]

                # 标记元数据来源
                sources = set(paper.get("metadata_sources", []))
                sources.add("semantic_scholar")
                paper["metadata_sources"] = sorted(sources)

                # 如果 SS 提供了更精确的发表日期，补充到 published（仅当原 published 为空时）
                if not paper.get("published") and ss_data.get("publication_date"):
                    paper["published"] = ss_data["publication_date"]

            return papers
        except asyncio.TimeoutError:
            logger.warning("Semantic Scholar enrichment timed out, returning original papers")
            return papers
        except Exception as e:
            logger.warning(f"Semantic Scholar enrichment failed: {e}")
            return papers

    def _score_papers(self, papers: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """基于查询关键词对论文进行相关性评分（0-100）。"""
        if not papers or not query:
            return papers

        query_terms = [t.strip().lower() for t in query.replace(",", " ").split() if len(t.strip()) > 1]
        if not query_terms:
            query_terms = [query.lower()]

        for paper in papers:
            title = (paper.get("title") or "").lower()
            abstract = (paper.get("abstract") or "").lower()
            categories = [c.lower() for c in (paper.get("categories") or [])]
            fields = [f.lower() for f in (paper.get("fields_of_study") or [])]

            score = 0.0
            # 标题匹配权重高
            for term in query_terms:
                if term in title:
                    score += 25
                if term in abstract:
                    score += 10
                if any(term in c for c in categories):
                    score += 8
                if any(term in f for f in fields):
                    score += 6

            # 引用次数加分（封顶）
            citation_count = paper.get("citation_count") or 0
            if citation_count:
                score += min(citation_count / 50, 15)

            # 有 TL;DR 和 venue 加分
            if paper.get("tldr"):
                score += 5
            if paper.get("venue"):
                score += 5

            paper["relevance_score"] = min(round(score, 1), 100)

        # 按相关性降序
        papers.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)
        return papers

    def _top_k_papers(self, papers: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """取 Top-K 相关论文。"""
        return papers[:top_k]

    async def _extract_paper_sections(
        self, papers: List[Dict[str, Any]], query: str = ""
    ) -> List[Dict[str, Any]]:
        """用 LLM 从论文摘要中抽取方法、结论、数据集、局限性等结构化信息。"""
        if not papers:
            return papers

        system_prompt = """你是一个学术文献信息抽取专家。请根据论文标题和摘要，抽取以下结构化信息，严格返回JSON：
{
    "methods": "论文使用的主要方法/模型/算法（2-3句）",
    "conclusion": "主要结论/贡献（2-3句）",
    "datasets": ["使用的数据集名称或来源"],
    "limitations": "局限性或未来工作（1-2句）",
    "key_findings": ["关键发现1", "关键发现2"]
}
如果某项信息在摘要中无法推断，用空字符串或空数组表示。"""

        for paper in papers:
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")
            if not abstract:
                continue

            prompt = f"""查询主题：{query or '相关研究'}

论文标题：{title}
论文摘要：
{abstract[:3000]}

请抽取结构化信息。"""

            try:
                response = await self.call_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ]
                )
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    extraction = json.loads(content[start:end])
                    paper["extraction"] = extraction
            except Exception as e:
                logger.warning(f"抽取论文 {paper.get('arxiv_id')} 信息失败: {e}")

        return papers

    async def _call_mcp_search(self, query: str, tool_name: str = "web_search") -> Optional[str]:
        """通过 MCP 工具进行真实搜索（如果可用）"""
        import asyncio
        try:
            from ..mcp import get_mcp_manager
            from ..mcp.client import MCPClient, MCPServerConfig as ClientConfig

            mcp_mgr = get_mcp_manager()
            server_name = None
            mcp_tool_name = None
            mcp_tool_args: Dict[str, Any] = {"query": query}

            # 查找可用的搜索服务器并映射到合适的 MCP 工具
            if tool_name == "web_search":
                for name in ["web_search", "bing_search", "brave_search"]:
                    if name in mcp_mgr.servers:
                        server_name = name
                        break
            elif tool_name in ("paper_search", "arxiv_search", "scholar_search"):
                # 优先使用 arxiv_server（返回结构化真实数据，可验证）
                if "arxiv_server" in mcp_mgr.servers:
                    server_name = "arxiv_server"
                    mcp_tool_name = "search_papers"
                    # arxiv-mcp-server 支持：query, max_results, categories, sort_by, date_from, date_to
                    mcp_tool_args = {
                        "query": query,
                        "max_results": 10,
                        "sort_by": "relevance",
                        "categories": self._infer_arxiv_categories(query),
                    }
                elif "scholarly_research" in mcp_mgr.servers:
                    server_name = "scholarly_research"
                    mcp_tool_name = "research_search"
                    if tool_name == "arxiv_search":
                        mcp_tool_args["source"] = "arxiv"
                    elif tool_name == "scholar_search":
                        mcp_tool_args["source"] = "google_scholar"
                else:
                    # fallback to web_search
                    for name in ["web_search", "bing_search", "brave_search"]:
                        if name in mcp_mgr.servers:
                            server_name = name
                            break
            if not server_name:
                return None

            srv = mcp_mgr.servers[server_name]
            if not srv.enabled:
                return None

            config = ClientConfig(
                name=server_name,
                command=srv.command,
                args=srv.args,
                env=srv.env,
            )
            client = MCPClient(config)
            try:
                await asyncio.wait_for(client.connect(), timeout=10.0)
                tools = await asyncio.wait_for(client.list_tools(), timeout=10.0)
                if not tools:
                    return None

                # 如果未指定工具名，使用第一个可用工具
                if mcp_tool_name is None:
                    mcp_tool_name = tools[0]["name"]
                else:
                    # 确认指定工具存在，否则 fallback 到第一个
                    available = {t["name"] for t in tools}
                    if mcp_tool_name not in available:
                        mcp_tool_name = tools[0]["name"]

                # arxiv_server 需要更长超时（API 限速）
                call_timeout = 90.0 if server_name == "arxiv_server" else 30.0

                result = await asyncio.wait_for(
                    client.call_tool(mcp_tool_name, mcp_tool_args),
                    timeout=call_timeout,
                )
                return result
            except asyncio.TimeoutError:
                logger.warning("MCP search timed out")
                return None
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"MCP search failed: {e}")
            return None
        import asyncio
        try:
            from ..mcp import get_mcp_manager
            from ..mcp.client import MCPClient, MCPServerConfig as ClientConfig

            mcp_mgr = get_mcp_manager()
            server_name = None
            mcp_tool_name = None
            mcp_tool_args: Dict[str, Any] = {"query": query}

            # 查找可用的搜索服务器并映射到合适的 MCP 工具
            if tool_name == "web_search":
                for name in ["web_search", "bing_search", "brave_search"]:
                    if name in mcp_mgr.servers:
                        server_name = name
                        break
            elif tool_name in ("paper_search", "arxiv_search", "scholar_search"):
                # 优先使用 arxiv_server（返回结构化真实数据，可验证）
                if "arxiv_server" in mcp_mgr.servers:
                    server_name = "arxiv_server"
                    mcp_tool_name = "search_papers"
                    # arxiv-mcp-server 支持：query, max_results, categories, sort_by, date_from, date_to
                    mcp_tool_args = {
                        "query": query,
                        "max_results": 10,
                        "sort_by": "relevance",
                        "categories": self._infer_arxiv_categories(query),
                    }
                elif "scholarly_research" in mcp_mgr.servers:
                    server_name = "scholarly_research"
                    mcp_tool_name = "research_search"
                    if tool_name == "arxiv_search":
                        mcp_tool_args["source"] = "arxiv"
                    elif tool_name == "scholar_search":
                        mcp_tool_args["source"] = "google_scholar"
                else:
                    # fallback to web_search
                    for name in ["web_search", "bing_search", "brave_search"]:
                        if name in mcp_mgr.servers:
                            server_name = name
                            break
            if not server_name:
                return None

            srv = mcp_mgr.servers[server_name]
            if not srv.enabled:
                return None

            config = ClientConfig(
                name=server_name,
                command=srv.command,
                args=srv.args,
                env=srv.env,
            )
            client = MCPClient(config)
            try:
                await asyncio.wait_for(client.connect(), timeout=10.0)
                tools = await asyncio.wait_for(client.list_tools(), timeout=10.0)
                if not tools:
                    return None

                # 如果未指定工具名，使用第一个可用工具
                if mcp_tool_name is None:
                    mcp_tool_name = tools[0]["name"]
                else:
                    # 确认指定工具存在，否则 fallback 到第一个
                    available = {t["name"] for t in tools}
                    if mcp_tool_name not in available:
                        mcp_tool_name = tools[0]["name"]

                # arxiv_server 需要更长超时（API 限速）
                call_timeout = 90.0 if server_name == "arxiv_server" else 30.0

                result = await asyncio.wait_for(
                    client.call_tool(mcp_tool_name, mcp_tool_args),
                    timeout=call_timeout,
                )
                return result
            except asyncio.TimeoutError:
                logger.warning("MCP search timed out")
                return None
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"MCP search failed: {e}")
            return None

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        action = task_input.get("action", "search")
        query = task_input.get("query", context.get("problem_text", ""))
        logger.info(f"ResearchAgent action={action}, query={query[:80]}")

        # 步骤1：尝试使用 MCP 工具进行真实搜索
        mcp_result: Optional[str] = None
        verified_papers: List[Dict[str, Any]] = []
        mcp_search_used = False
        mcp_server_used: Optional[str] = None

        if action in ("search", "deep_search", "search_background", "search_methods"):
            if action == "search_methods":
                mcp_result = await self._call_mcp_search(query, tool_name="paper_search")
            elif action == "search_background":
                mcp_result = await self._call_mcp_search(query, tool_name="web_search")
            else:
                # search / deep_search 默认走 arXiv 真实学术检索
                mcp_result = await self._call_mcp_search(query, tool_name="arxiv_search")

            if mcp_result:
                mcp_search_used = True
                logger.info(f"MCP search returned {len(mcp_result)} chars")
                # 仅对学术搜索 action 解析真实论文
                if action in ("search", "deep_search", "search_methods"):
                    verified_papers = self._parse_arxiv_papers(mcp_result, query)
                    logger.info(f"Verified papers from MCP: {len(verified_papers)}")
                    # 【新增】用 Semantic Scholar 批量增强元数据
                    if verified_papers:
                        verified_papers = await self._enrich_with_semantic_scholar(verified_papers)

        # 步骤1.5：相关性评分与 Top-K 过滤
        top_k = task_input.get("top_k", 10)
        if verified_papers:
            verified_papers = self._score_papers(verified_papers, query)
            verified_papers = self._top_k_papers(verified_papers, top_k=top_k)
            logger.info(f"Top-{top_k} papers selected after relevance scoring")

        # 步骤1.6：深度调研模式抽取方法/结论/数据集/局限性
        if action == "deep_search" and verified_papers:
            logger.info(f"Deep extraction for {len(verified_papers)} papers")
            verified_papers = await self._extract_paper_sections(verified_papers, query)

        # 步骤2：构建用户 prompt
        system_prompt = self.get_system_prompt(action)
        user_content = f"请搜索以下问题的相关资料：{query}\n\n背景：{context.get('problem_text', '')[:300]}"

        if verified_papers:
            papers_json = json.dumps(verified_papers, ensure_ascii=False, indent=2)
            user_content += (
                f"\n\n【已验证的真实文献（来自 arXiv）】\n"
                f"{papers_json[:6000]}\n\n"
                f"要求：\n"
                f"1. 上述文献的 title、authors、year、abstract、url、arxiv_id 已验证真实，不要修改\n"
                f"2. 请基于上述文献生成 summary、methods、datasets 等衍生字段\n"
                f"3. 输出 JSON 中 papers 字段必须直接复用上述文献列表（保持字段和顺序一致）\n"
                f"4. 如果文献不足，可在 methods 中补充一般性方法描述，但不要在 papers 中编造不存在的数据"
            )
        elif mcp_result:
            user_content += (
                f"\n\n【网络检索结果】\n"
                f"{mcp_result[:4000]}\n\n"
                f"请基于以上检索结果和您的知识，整理出完整的JSON格式研究报告。"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # 步骤3：调用 LLM 生成衍生字段
        try:
            response = await self.call_llm(messages=messages, context=context)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])

                # 可靠性关键：用已验证文献强制覆盖 LLM 生成的 papers，防止幻觉
                if verified_papers:
                    result["papers"] = verified_papers
                    result["mcp_search_used"] = True
                    result["verified_paper_count"] = len(verified_papers)
                    result["paper_source"] = "arxiv"
                else:
                    result["mcp_search_used"] = mcp_search_used

                result["summary"] = result.get(
                    "summary",
                    f"从 arXiv 检索到 {len(result.get('papers', []))} 篇相关文献" if verified_papers else f"找到{len(result.get('papers', []))}篇相关文献",
                )
                return result
        except Exception as e:
            logger.warning(f"ResearchAgent LLM call failed: {e}")

        # 步骤4：LLM 失败但已有验证文献时，直接返回文献列表
        if verified_papers:
            return {
                "papers": verified_papers,
                "datasets": [],
                "methods": [],
                "summary": f"从 arXiv 检索到 {len(verified_papers)} 篇相关文献",
                "mcp_search_used": True,
                "verified_paper_count": len(verified_papers),
                "paper_source": "arxiv",
            }

        # 步骤5：最终 fallback（模拟模式或原始 MCP 结果）
        fallback: Dict[str, Any] = {
            "papers": [],
            "datasets": [],
            "methods": [],
            "summary": "资料搜索完成（模拟模式）",
        }
        if action == "search_background":
            fallback["trends"] = []
            fallback["background_summary"] = ""
        elif action == "search_methods":
            fallback["model_summary"] = ""
        if mcp_result:
            fallback["mcp_search_used"] = True
            fallback["raw_mcp_result"] = mcp_result[:2000]
        return fallback
