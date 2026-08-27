"""Template Skills Registry — 加载 12 个论文模板的写作风格 skill。

每个模板的 skill 在 ``src/knowledge/template_skills/{template_id}/`` 下，含：
- SKILL.md: 写作风格基线 / 章节约定 / 公式 / 引用 / 图表 / 真实示例 / checklist
- references.md: 真实 arxiv 验证过的论文清单（133 条总数）

此模块提供：
- :func:`get_template_skill(template_id)` — 取模板 skill
- :func:`list_template_skills()` — 列全部可用模板
- :func:`get_real_references(template_id)` — 取模板的真实论文清单
- :func:`verify_reference(arxiv_id)` — 校验某条引用是否真实
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


SKILLS_DIR = Path(__file__).parent


# ==================== 数据结构 ====================


@dataclass
class TemplateSkill:
    """单个模板的 skill 包。"""
    template_id: str
    skill_md: str
    references_md: str
    real_references: List[str] = field(default_factory=list)
    checklist: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """从 SKILL.md frontmatter 取 name。"""
        m = re.search(r"^name:\s*(.+)$", self.skill_md, re.MULTILINE)
        return m.group(1).strip() if m else self.template_id


# ==================== 加载器 ====================


_ARXIV_ID_PATTERN = re.compile(r"\b(\d{4}\.\d{4,5}(v\d+)?)\b")
_ARXIV_OLD_ID_PATTERN = re.compile(r"\b([a-z\-]+(?:\.[A-Z]{2})?/\d{7})\b")  # cs.LG/0401001 等旧格式
_ARXIV_URL_PATTERN = re.compile(r"https?://arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})")


def _parse_arxiv_ids(text: str) -> List[str]:
    """从文本中提取所有 arxiv ID（按出现顺序）。

    支持新格式 (2401.12345) 和旧格式 (cs.LG/0401001)。
    """
    ids = []
    seen = set()
    # 新格式
    for m in _ARXIV_ID_PATTERN.finditer(text):
        arxiv_id = m.group(1).split("v")[0]  # 去掉版本号
        if arxiv_id not in seen:
            ids.append(arxiv_id)
            seen.add(arxiv_id)
    # 旧格式
    for m in _ARXIV_OLD_ID_PATTERN.finditer(text):
        arxiv_id = m.group(1)
        if arxiv_id not in seen:
            ids.append(arxiv_id)
            seen.add(arxiv_id)
    return ids


def _parse_checklist(text: str) -> List[str]:
    """从 SKILL.md 中提取 checklist（"## 7. 写作 Checklist" 后的列表项）。"""
    items = []
    in_checklist = False
    for line in text.splitlines():
        if re.match(r"^##\s*\d+\.\s*.*[Cc]hecklist", line):
            in_checklist = True
            continue
        if in_checklist:
            # 下一个章节
            if line.startswith("## "):
                break
            # 提取 ✅ 或 - 开头的项
            m = re.match(r"^\s*[-*]\s*(.+)", line)
            if m:
                item = m.group(1).strip()
                if item and not item.startswith("**"):
                    items.append(item)
    return items


def _load_template_skill(template_id: str) -> Optional[TemplateSkill]:
    """加载单个模板 skill。"""
    skill_path = SKILLS_DIR / template_id / "SKILL.md"
    refs_path = SKILLS_DIR / template_id / "references.md"
    if not skill_path.exists() or not refs_path.exists():
        return None
    skill_md = skill_path.read_text(encoding="utf-8")
    refs_md = refs_path.read_text(encoding="utf-8")
    real_refs = _parse_arxiv_ids(refs_md)
    return TemplateSkill(
        template_id=template_id,
        skill_md=skill_md,
        references_md=refs_md,
        real_references=real_refs,
        checklist=_parse_checklist(skill_md),
    )


_cache: Dict[str, TemplateSkill] = {}


def get_template_skill(template_id: str) -> Optional[TemplateSkill]:
    """取模板 skill（带缓存）。"""
    if template_id not in _cache:
        _cache[template_id] = _load_template_skill(template_id)
    return _cache[template_id]


def list_template_skills() -> List[str]:
    """列出所有可用模板 skill ID。"""
    return sorted(
        d.name for d in SKILLS_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def get_real_references(template_id: str) -> List[str]:
    """取模板的真实 arxiv 论文 ID 列表（用于强制引用真实文献）。"""
    skill = get_template_skill(template_id)
    return skill.real_references if skill else []


def get_checklist(template_id: str) -> List[str]:
    """取模板的写作 checklist（用于自动评审）。"""
    skill = get_template_skill(template_id)
    return skill.checklist if skill else []


def reset_cache() -> None:
    """重置缓存（用于测试或 reload）。"""
    _cache.clear()


# ==================== 文献核实 ====================


def verify_reference(arxiv_id: str) -> Optional[Dict]:
    """校验某 arxiv ID 是否真实（通过 arxiv.org/abs/<id> 拉取）。

    Returns:
        dict 含 title / authors / abstract / comments，None 表示 ID 不存在。
        网络失败时返回 None（不抛异常，调用方按需处理）。
    """
    import httpx

    arxiv_id = arxiv_id.strip().split("v")[0]  # 去掉版本号
    url = f"https://arxiv.org/abs/{arxiv_id}"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text
        # 简单解析：找 <meta name="citation_title" content="...">
        import re as _re

        title_m = _re.search(
            r'<meta\s+name="citation_title"\s+content="([^"]+)"', html
        )
        authors_m = _re.findall(
            r'<meta\s+name="citation_author"\s+content="([^"]+)"', html
        )
        abstract_m = _re.search(
            r'<blockquote class="abstract[^"]*">\s*<abstract>(.*?)</abstract>',
            html,
            _re.DOTALL,
        )
        comments_m = _re.search(
            r'<td class="tablecell comments[^"]*">\s*(.*?)\s*</td>',
            html,
            _re.DOTALL,
        )
        return {
            "arxiv_id": arxiv_id,
            "url": url,
            "title": title_m.group(1) if title_m else None,
            "authors": authors_m,
            "abstract": abstract_m.group(1).strip() if abstract_m else None,
            "comments": comments_m.group(1).strip() if comments_m else None,
        }
    except Exception as e:
        logger.debug(f"verify_reference({arxiv_id}) failed: {e}")
        return None


def find_citation_in_text(text: str, arxiv_id: str) -> bool:
    """检查文本是否包含指定 arxiv ID 的引用（如 [2401.12345] 或 arxiv:2401.12345）。"""
    arxiv_id = arxiv_id.strip().split("v")[0]
    patterns = [
        rf"\b{arxiv_id}\b",
        rf"arxiv\.org/(?:abs|pdf)/{arxiv_id}",
        rf"arXiv:{arxiv_id}",
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def filter_fake_references(
    text: str,
    real_pool: List[str],
) -> List[Dict]:
    """从文本中提取所有 arxiv 引用，标记真假。

    Args:
        text: 待检查文本（如 LaTeX 论文正文）
        real_pool: 已知真实引用池（来自模板 skill）

    Returns:
        list of {arxiv_id, is_real, source} 字典
    """
    found_ids = _parse_arxiv_ids(text)
    real_set = set(real_pool)
    results = []
    for aid in found_ids:
        results.append({
            "arxiv_id": aid,
            "is_real": aid in real_set or verify_reference(aid) is not None,
            "in_template_pool": aid in real_set,
        })
    return results
