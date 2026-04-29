"""
文档模型与分块
==============

借鉴 cherry-studio 的文档预处理设计。
"""

from dataclasses import dataclass, field
from typing import List, Optional
import re


@dataclass
class Document:
    """文档数据类"""
    id: str
    title: str
    content: str
    source: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class DocumentChunker:
    """文档分块器"""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 128,
        separator: str = "\n"
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator

    def chunk(self, document: Document) -> List[Document]:
        """将文档分块"""
        text = document.content
        if len(text) <= self.chunk_size:
            return [document]

        chunks = []
        start = 0
        chunk_idx = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]

            # 尝试在分隔符处截断
            if end < len(text):
                last_sep = chunk_text.rfind(self.separator)
                if last_sep > self.chunk_size * 0.5:
                    end = start + last_sep + len(self.separator)
                    chunk_text = text[start:end]

            chunk_id = f"{document.id}_chunk_{chunk_idx}"
            chunks.append(Document(
                id=chunk_id,
                title=f"{document.title} (片段 {chunk_idx + 1})",
                content=chunk_text.strip(),
                source=document.source,
                metadata={
                    **document.metadata,
                    "chunk_index": chunk_idx,
                    "parent_id": document.id,
                }
            ))

            start = end - self.chunk_overlap
            chunk_idx += 1

        return chunks

    def chunk_text(self, text: str, doc_id: str = "doc", title: str = "") -> List[Document]:
        """直接分块文本"""
        doc = Document(id=doc_id, title=title, content=text)
        return self.chunk(doc)
