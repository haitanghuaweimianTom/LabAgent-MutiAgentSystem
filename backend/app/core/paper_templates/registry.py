"""论文模板注册表。

设计目标：
- 把 Writer Agent 中硬编码的 4 套模板（CUMCM / 课程 / 金融 / 科研综述）从代码迁出，
  改成可由 ``templates/*.json`` 文件声明。
- 新增一个 CCF-A 会议模板只需要"写一个 JSON + 放一个 .cls 文件"，
  不必修改任何 Agent 源代码。
- 注册表按 ``template_id`` 暴露；**找不到时 fallback 到 ``math_modeling``**，
  保证向后兼容（旧调用方传 ``"math_modeling"`` 永远有效）。

模板文件结构参见本目录的 ``templates/cumcm.json``，所有字段均有合理默认值。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 模板目录：paper_templates/templates/*.json
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# 默认 / fallback 模板 ID。
# 当调用方传 ``template_id="math_modeling"`` 或传一个不存在的 ID 时，
# 注册表都回退到这一项。
DEFAULT_TEMPLATE_ID = "math_modeling"


@dataclass
class ChapterPlan:
    """单个章节的写作计划。

    字段含义：
    - ``id``：章节唯一标识（如 ``abstract``、``methodology``）。
    - ``title``：在论文中显示的标题（含编号，如 ``"1 Introduction"``）。
    - ``section_level``：0=front matter (abstract/keywords/appendix)；
      1=正文章节；2=子章节。在正文中应使用 ``\\section`` / ``\\subsection``。
    - ``prompt_role``：章节级 system prompt 中关于"这章写什么"的一段指令。
    - ``requirements``：硬约束列表，LLM 必须按这些要求写作。
    - ``required_figures``（可选）：本章必须出现的图表 ID 列表，用于编排 figures。
    """

    id: str
    title: str
    section_level: int
    prompt_role: str
    requirements: List[str] = field(default_factory=list)
    required_figures: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterPlan":
        return cls(
            id=data["id"],
            title=data["title"],
            section_level=int(data.get("section_level", 1)),
            prompt_role=data.get("prompt_role", ""),
            requirements=list(data.get("requirements", []) or []),
            required_figures=list(data.get("required_figures", []) or []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PaperTemplate:
    """一套完整的论文模板。

    关键字段：
    - ``id``：模板 ID（API 入参 ``template_id``），全局唯一。
    - ``domain``：领域标签（``math_modeling`` / ``coursework`` /
      ``financial_analysis`` / ``research_paper`` / ``survey``）。
    - ``documentclass``：LaTeX 文档类（``cumcmthesis`` / ``article`` /
      ``IEEEtran`` / ``acmart`` / ``neurips_2024`` / ``llncs``）。
    - ``cls_file``：.cls 文件相对项目根的路径；空字符串表示不依赖 cls。
    - ``bib_style``：BibTeX 样式（如 ``ieeetr`` / ``splncs04`` / ``plain``）。
    - ``language``：主语言，``zh`` / ``en``，影响 ctex/字体选择。
    - ``acceptance_threshold``：章节评审分数门槛（百分制）。
    - ``chapter_plan``：章节列表，详见 :class:`ChapterPlan`。
    - ``system_prompt``：写作 Agent 的整体 system prompt。
    - ``preamble``：LaTeX 文档前言（``\\documentclass`` 到 ``\\begin{document}`` 之前）。
    - ``metadata_defaults``：默认 metadata（学校、队名、作者、邮件等），
      用户可在任务提交时覆盖。
    - ``compile_options``：LaTeX 编译选项 ``{engine, extra_packages}``。
    """

    id: str
    name: str
    domain: str
    documentclass: str
    cls_file: str = ""
    bib_style: str = "plain"
    language: str = "zh"
    acceptance_threshold: int = 75
    min_pages: int = 8
    max_pages: int = 30
    citation_style: str = "numeric"
    description: str = ""
    chapter_plan: List[ChapterPlan] = field(default_factory=list)
    system_prompt: str = ""
    preamble: str = ""
    appendix_template: str = ""
    metadata_defaults: Dict[str, Any] = field(default_factory=dict)
    compile_options: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    # ---------- 派生方法 ----------

    def chapters_by_id(self) -> Dict[str, ChapterPlan]:
        return {ch.id: ch for ch in self.chapter_plan}

    def get_metadata_defaults(self) -> Dict[str, Any]:
        """返回模板默认元数据（未来可扩展为用户覆盖）。"""
        return dict(self.metadata_defaults or {})

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperTemplate":
        chapter_plan = [ChapterPlan.from_dict(c) for c in data.get("chapter_plan", []) or []]
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            domain=data.get("domain", "general"),
            documentclass=data.get("documentclass", "article"),
            cls_file=data.get("cls_file", ""),
            bib_style=data.get("bib_style", "plain"),
            language=data.get("language", "zh"),
            acceptance_threshold=int(data.get("acceptance_threshold", 75)),
            min_pages=int(data.get("min_pages", 8)),
            max_pages=int(data.get("max_pages", 30)),
            citation_style=data.get("citation_style", "numeric"),
            description=data.get("description", ""),
            chapter_plan=chapter_plan,
            system_prompt=data.get("system_prompt", ""),
            preamble=data.get("preamble", ""),
            appendix_template=data.get("appendix_template", ""),
            metadata_defaults=dict(data.get("metadata_defaults", {}) or {}),
            compile_options=dict(data.get("compile_options", {}) or {}),
            extra=dict(data.get("extra", {}) or {}),
        )


# ========================= 注册表 =========================


class TemplateRegistry:
    """线程安全的论文模板注册表。

    用法：
    - 启动时 ``load_builtin_templates()`` 扫描 ``templates/`` 目录加载所有 JSON。
    - 业务侧 ``registry.get(template_id)`` 获取模板；找不到时回退到默认。
    - 动态注册可用 ``register(template)`` 注入运行时新增模板（来自 UI / API）。
    """

    def __init__(self) -> None:
        self._templates: Dict[str, PaperTemplate] = {}
        self._lock = threading.RLock()
        self._loaded = False

    # ---- 加载 ----

    def load_builtin_templates(self, templates_dir: Optional[Path] = None) -> int:
        """扫描 ``templates/*.json`` 加载所有模板。返回成功加载数量。"""
        target = Path(templates_dir) if templates_dir else _TEMPLATES_DIR
        if not target.is_dir():
            logger.warning("Templates dir not found: %s", target)
            return 0

        loaded = 0
        for json_path in sorted(target.glob("*.json")):
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                template = PaperTemplate.from_dict(data)
                self.register(template, overwrite=True)
                loaded += 1
                logger.info("Loaded paper template: %s -> %s", template.id, json_path.name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to load template %s: %s", json_path, exc)
        with self._lock:
            self._loaded = True
        return loaded

    def ensure_loaded(self) -> None:
        with self._lock:
            if not self._loaded:
                self.load_builtin_templates()

    # ---- 注册 / 查询 ----

    def register(self, template: PaperTemplate, *, overwrite: bool = False) -> None:
        with self._lock:
            if not overwrite and template.id in self._templates:
                raise ValueError(f"Template id already registered: {template.id}")
            self._templates[template.id] = template

    def get(self, template_id: Optional[str]) -> PaperTemplate:
        """按 ID 获取模板。**找不到时回退到默认** ``math_modeling``。"""
        self.ensure_loaded()
        if not template_id:
            return self._templates[DEFAULT_TEMPLATE_ID]
        with self._lock:
            tpl = self._templates.get(template_id)
        if tpl is None:
            logger.warning(
                "Template '%s' not found; falling back to '%s'",
                template_id,
                DEFAULT_TEMPLATE_ID,
            )
            return self._templates[DEFAULT_TEMPLATE_ID]
        return tpl

    def has(self, template_id: str) -> bool:
        self.ensure_loaded()
        with self._lock:
            return template_id in self._templates

    def list_ids(self) -> List[str]:
        self.ensure_loaded()
        with self._lock:
            return sorted(self._templates.keys())

    def list_templates(self) -> List[PaperTemplate]:
        self.ensure_loaded()
        with self._lock:
            return [self._templates[k] for k in sorted(self._templates.keys())]

    def __len__(self) -> int:
        self.ensure_loaded()
        with self._lock:
            return len(self._templates)

    def __contains__(self, template_id: object) -> bool:
        return isinstance(template_id, str) and self.has(template_id)


# ========================= 单例访问 =========================

_registry: Optional[TemplateRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> TemplateRegistry:
    """获取全局单例注册表。**首次访问时自动加载内置模板。**"""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = TemplateRegistry()
                _registry.load_builtin_templates()
    return _registry


def load_template(template_id: Optional[str]) -> PaperTemplate:
    """便捷函数：按 ID 取一个模板。"""
    return get_registry().get(template_id)


def register_template(template: PaperTemplate, *, overwrite: bool = False) -> None:
    """便捷函数：动态注册一个模板。"""
    get_registry().register(template, overwrite=overwrite)
