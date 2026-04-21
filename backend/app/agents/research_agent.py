"""研究Agent - 搜集相关资料、文献、数据"""
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
    default_model = "minimax-m2.7"

    def get_system_prompt(self) -> str:
        return """你是一个专业的研究助手，专门为数学建模问题搜集相关资料。
职责：
1. 搜索相关学术文献
2. 查找相关数学模型和算法
3. 搜集相关公开数据集
4. 整理归纳搜索结果

输出格式（严格JSON）：
{
    "papers": [{"title": "", "authors": "", "year": 0, "abstract": "", "url": ""}],
    "datasets": [{"name": "", "source": "", "description": ""}],
    "methods": [{"name": "", "description": "", "paper": ""}],
    "summary": ""
}"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        query = task_input.get("query", context.get("problem_text", "")[:100])
        logger.info(f"ResearchAgent searching: {query}")

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"请搜索以下问题的相关资料：{query}\n\n背景：{context.get('problem_text', '')[:200]}"},
        ]

        try:
            response = await self.call_llm(messages=messages)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
                result["summary"] = result.get("summary", f"找到{len(result.get('papers', []))}篇相关文献")
                return result
        except Exception as e:
            logger.warning(f"ResearchAgent LLM call failed: {e}")

        return {
            "papers": [],
            "datasets": [],
            "methods": [],
            "summary": f"资料搜索完成（模拟模式）"
        }
