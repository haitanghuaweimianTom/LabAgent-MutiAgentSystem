"""Paper templates - 可插拔的论文模板注册表。

模板以 JSON 形式存放在 ``templates/`` 目录，运行期由 :class:`TemplateRegistry`
加载并提供按 ``template_id`` 检索的能力。**CUMCM 退化为默认模板之一**，
新增 CCF-A 会议模板只需"新增一个 JSON + 放一个 .cls 文件"，不改任何 Agent 代码。

对外暴露：
- :class:`PaperTemplate`：模板数据模型。
- :class:`ChapterPlan`：章节数据模型。
- :func:`get_registry`：单例访问入口。
- :func:`load_template`：按 ID 取一个模板（找不到时 fallback ``math_modeling``）。
"""
from .registry import (
    DEFAULT_TEMPLATE_ID,
    ChapterPlan,
    PaperTemplate,
    TemplateRegistry,
    get_registry,
    load_template,
    register_template,
)

__all__ = [
    "DEFAULT_TEMPLATE_ID",
    "ChapterPlan",
    "PaperTemplate",
    "TemplateRegistry",
    "get_registry",
    "load_template",
    "register_template",
]
