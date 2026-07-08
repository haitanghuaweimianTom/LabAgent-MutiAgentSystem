#!/usr/bin/env python3
"""
Multi-engine MCP Server for web search.
Supports: DuckDuckGo, Bing, WeChat articles (via Sogou).
"""

import asyncio
import json
import os
import sys
import urllib.parse
from typing import Any, Dict, List, Optional

# 清除 SOCKS 代理环境变量（httpx 不支持 socks:// 协议）
for _var in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
    if _var in os.environ:
        val = os.environ[_var].lower()
        if "socks" in val:
            del os.environ[_var]

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


app = Server("multi-search")


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    tools = [
        Tool(
            name="web_search",
            description="Search the web using DuckDuckGo. Returns search results with title, URL, and snippet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results (default: 5)", "default": 5}
                },
                "required": ["query"]
            }
        ),
    ]

    if HAS_REQUESTS:
        tools.extend([
            Tool(
                name="bing_search",
                description="Search the web using Bing. Returns search results with title, URL, and snippet.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "description": "Max results (default: 5)", "default": 5}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="wechat_search",
                description="Search WeChat public account articles via Sogou. Returns article titles, URLs, and snippets.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (Chinese keywords work best)"},
                        "max_results": {"type": "integer", "description": "Max results (default: 5)", "default": 5}
                    },
                    "required": ["query"]
                }
            ),
        ])

    return tools


def _bing_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search Bing and return results."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resp = requests.get(f'https://www.bing.com/search?q={urllib.parse.quote(query)}', headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')
    results = []

    for item in soup.select('li.b_algo')[:max_results]:
        title_el = item.select_one('h2 a')
        snippet_el = item.select_one('.b_caption p') or item.select_one('.b_algoSlug')

        if title_el:
            title = title_el.get_text(strip=True)
            # Try to get the actual URL from the redirect
            href = title_el.get('href', '')
            if '/ck/a?' in href:
                # Extract actual URL from Bing redirect
                try:
                    from urllib.parse import parse_qs, urlparse
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    if 'r' in qs:
                        href = qs['r'][0]
                except Exception:
                    pass

            snippet = snippet_el.get_text(strip=True) if snippet_el else ''
            results.append({'title': title, 'url': href, 'body': snippet})

    return results


def _wechat_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search WeChat articles via Sogou."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    encoded_query = urllib.parse.quote(query)
    resp = requests.get(
        f'https://weixin.sogou.com/weixin?type=2&query={encoded_query}',
        headers=headers,
        timeout=15
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')
    results = []

    for item in soup.select('.news-box .news-list li')[:max_results]:
        title_el = item.select_one('h3 a')
        snippet_el = item.select_one('.txt-info')
        account_el = item.select_one('.account')

        if title_el:
            title = title_el.get_text(strip=True)
            href = title_el.get('href', '')
            if href and not href.startswith('http'):
                href = f'https://weixin.sogou.com{href}'

            snippet = snippet_el.get_text(strip=True) if snippet_el else ''
            account = account_el.get_text(strip=True) if account_el else ''

            result = {'title': title, 'url': href, 'body': snippet}
            if account:
                result['account'] = account
            results.append(result)

    return results


def _format_results(query: str, results: List[Dict[str, str]], source: str) -> str:
    """Format search results."""
    if not results:
        return f"No results found for: {query}"

    lines = [f"{source} search results for \"{query}\" ({len(results)} results):\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title', 'No title')}")
        lines.append(f"   URL: {r.get('url', 'No URL')}")
        if r.get('account'):
            lines.append(f"   Account: {r['account']}")
        if r.get('body'):
            lines.append(f"   {r['body']}")
        lines.append('')

    return "\n".join(lines)


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    query = arguments.get("query", "")
    max_results = arguments.get("max_results", 5)

    try:
        if name == "web_search":
            if DDGS is None:
                return [TextContent(type="text", text="Error: ddgs package not installed")]
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            formatted = _format_results(query, [{
                'title': r.get('title', ''),
                'url': r.get('href', ''),
                'body': r.get('body', '')
            } for r in results], "DuckDuckGo")
            return [TextContent(type="text", text=formatted)]

        elif name == "bing_search":
            if not HAS_REQUESTS:
                return [TextContent(type="text", text="Error: requests/beautifulsoup4 not installed")]
            results = _bing_search(query, max_results)
            formatted = _format_results(query, results, "Bing")
            return [TextContent(type="text", text=formatted)]

        elif name == "wechat_search":
            if not HAS_REQUESTS:
                return [TextContent(type="text", text="Error: requests/beautifulsoup4 not installed")]
            results = _wechat_search(query, max_results)
            formatted = _format_results(query, results, "WeChat")
            return [TextContent(type="text", text=formatted)]

    except Exception as e:
        return [TextContent(type="text", text=f"Search error: {str(e)}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
