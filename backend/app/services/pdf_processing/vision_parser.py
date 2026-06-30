"""多模态视觉 PDF 解析器 —— 用于复杂图表、扫描页、公式密集页"""
import asyncio
import base64
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import PdfParser, PdfParserResult, pdf_parser_registry

logger = logging.getLogger(__name__)


@pdf_parser_registry.register("vision")
class VisionPdfParser(PdfParser):
    """基于多模态 LLM 的视觉 PDF 解析器（按页调用）。

    适用场景：
    - 扫描版 PDF（无文本层）
    - 复杂表格/图表页面
    - 公式排版混乱页面

    限制：
    - 受 API 速率限制，默认最多处理 5 页
    - 成本高于本地解析，建议作为辅助
    """

    name = "vision"
    label = "多模态视觉"
    description = "按页调用多模态 LLM 识别复杂版面（限速使用）"

    def __init__(self, provider_id: Optional[str] = None, model: Optional[str] = None, rate: float = 0.5):
        self.provider_id = provider_id
        self.model = model
        self.rate = rate
        self._bucket: Optional[Any] = None

    def is_available(self) -> bool:
        try:
            import fitz  # noqa: F401
            return True
        except Exception:
            return False

    async def parse(
        self,
        file_path: Path,
        pages: Optional[List[int]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> PdfParserResult:
        options = options or {}
        result = PdfParserResult()
        max_pages = options.get("vision_max_pages", 5)
        prompt = options.get(
            "vision_prompt",
            "请识别这张 PDF 页面中的所有内容。保留标题、段落、公式（用 LaTeX 表示）、表格（用 Markdown 表格）和图表描述。"
            "如果是数学建模赛题，请完整输出题目描述、已知条件、数据附件说明。",
        )

        try:
            import fitz
        except ImportError as e:
            result.errors.append(f"PyMuPDF 未安装: {e}")
            return result

        try:
            doc = fitz.open(str(file_path))
            total_pages = len(doc)
            target_pages = pages or list(range(1, total_pages + 1))
            target_pages = [p for p in target_pages if 1 <= p <= total_pages][:max_pages]

            result.pages = len(target_pages)
            result.metadata = {"total_pages": total_pages, "vision_pages": len(target_pages)}

            # 初始化速率限制器
            from ..rate_limiter import AsyncTokenBucket
            bucket = AsyncTokenBucket(rate=self.rate)

            tasks = []
            for page_number in target_pages:
                tasks.append(self._parse_one_page(doc, page_number, prompt, bucket, options))

            page_results = await asyncio.gather(*tasks, return_exceptions=True)

            texts = []
            for pr in page_results:
                if isinstance(pr, Exception):
                    result.errors.append(str(pr))
                    continue
                result.page_contents.append(pr)
                texts.append(f"\n## 第 {pr['page_number']} 页\n{pr['text']}")

            result.text = "\n".join(texts).strip()
            doc.close()
        except Exception as e:
            logger.exception("Vision PDF 解析失败")
            result.errors.append(f"解析失败: {e}")

        return result

    async def _parse_one_page(
        self,
        doc: Any,
        page_number: int,
        prompt: str,
        bucket: Any,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        import fitz

        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(dpi=options.get("dpi", 200))
        img_bytes = pix.tobytes("png")
        base64_image = base64.b64encode(img_bytes).decode("utf-8")

        await bucket.acquire()

        messages = self._build_messages(base64_image, prompt, options)
        text = await self._call_vision(messages, options)

        return {
            "page_number": page_number,
            "text": text,
            "markdown": text,
            "images": [],
            "tables": [],
        }

    def _build_messages(self, base64_image: str, prompt: str, options: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_format = options.get("api_format", "openai_chat")
        if api_format == "anthropic":
            return [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64_image,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
        return [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

    async def _call_vision(self, messages: List[Dict[str, Any]], options: Dict[str, Any]) -> str:
        """调用 BaseAgent.call_llm 实现多模态识别"""
        from ....agents.base import BaseAgent

        provider_id = options.get("vision_provider") or self.provider_id
        model = options.get("vision_model") or self.model
        api_format = options.get("api_format", "openai_chat")

        agent = BaseAgent(
            model=model,
            provider_id=provider_id or "",
            llm_backend="",
            temperature=0.1,
            max_tokens=4096,
        )
        # 强制 API 格式
        if provider_id:
            from ....core.provider_config import get_custom_provider
            provider = get_custom_provider(provider_id)
            if provider:
                api_format = provider.get("meta", {}).get("api_format", api_format)

        response = await agent.call_llm(messages=messages, temperature=0.1)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() or "视觉识别未返回内容"
