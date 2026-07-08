#!/usr/bin/env python3
"""
Simple DuckDuckGo MCP Server for web search.
Uses the duckduckgo-search Python package directly.
"""

import asyncio
import json
import sys
from typing import Any, Dict, List, Optional

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
        print("Error: ddgs package not installed. Run: pip install ddgs", file=sys.stderr)
        sys.exit(1)


app = Server("duckduckgo-search")


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="web_search",
            description="Search the web using DuckDuckGo. Returns search results with title, URL, and snippet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    if name == "web_search":
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 5)
        
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            
            if not results:
                return [TextContent(
                    type="text",
                    text=f"No results found for: {query}"
                )]
            
            # Format results
            lines = [f"Web search results for \"{query}\" ({len(results)} results):\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.get('title', 'No title')}")
                lines.append(f"   URL: {r.get('href', 'No URL')}")
                lines.append(f"   {r.get('body', 'No snippet')}\n")
            
            return [TextContent(type="text", text="\n".join(lines))]
        
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Search error: {str(e)}"
            )]
    
    return [TextContent(
        type="text",
        text=f"Unknown tool: {name}"
    )]


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
