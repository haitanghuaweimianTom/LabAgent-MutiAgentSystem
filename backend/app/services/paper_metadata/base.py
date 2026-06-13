"""论文元数据增强 Provider 抽象基类"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class PaperMetadataProvider(ABC):
    """论文元数据增强源抽象基类。

    每个实现代表一个外部学术数据源（Semantic Scholar / Crossref / OpenAlex 等），
    负责根据 arXiv ID 列表批量获取并返回补充元数据。
    """

    name: str = ""

    @abstractmethod
    async def enrich_papers(self, arxiv_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """根据 arXiv ID 列表批量获取补充元数据。

        Args:
            arxiv_ids: arXiv ID 列表（如 ["2203.08975", "2004.08883"]）。

        Returns:
            字典：arxiv_id -> 元数据字典。未查询到的 ID 不出现在结果中。
            元数据字典应包含与 Paper 模型对应的可选字段，如：
            doi, citation_count, reference_count, influential_citation_count,
            venue, fields_of_study, publication_date, s2_paper_id, s2_url,
            tldr, open_access_pdf 等。
        """
        raise NotImplementedError

    async def search_papers(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """（可选）根据关键词搜索论文并返回原始结果列表。"""
        raise NotImplementedError(f"{self.__class__.__name__} does not support search_papers")

    async def get_related_papers(self, arxiv_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """（可选）根据 arXiv ID 获取相关论文推荐。"""
        raise NotImplementedError(f"{self.__class__.__name__} does not support get_related_papers")

    @property
    def is_available(self) -> bool:
        """当前 provider 是否可用（可执行一次轻量检查，默认返回 True）。"""
        return True
