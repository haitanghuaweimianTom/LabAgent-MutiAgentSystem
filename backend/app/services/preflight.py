"""Preflight 决策服务 —— 任务提交时的数据/流程入口

职责：
1. 用 DataSchemaExtractor 静态分析用户上传的数据文件。
2. 调 LLM 做一次 ReAct-style 综合判断，输出：
   - problem_type
   - has_data_confidence
   - data_subjects
   - recommended_template / workflow / mode
   - data_adequacy（sufficient / insufficient / missing）
   - llm_should_collect + collection_plan
3. 在无数据或数据不足时，给出 collection_plan；由调用方决定是否执行。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..agents.base import BaseAgent
from ..config import get_settings
from ..core.paths import get_project_data_dir
from ..core.provider_config import get_default_provider
from ..services.data_schema import get_schema_extractor

logger = logging.getLogger(__name__)


class DataAdequacy(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    MISSING = "missing"


@dataclass
class PreflightReport:
    """Preflight 决策报告"""

    problem_type: str = "综合"
    has_data_confidence: float = 0.0
    data_subjects: List[str] = field(default_factory=list)
    recommended_template: str = "math_modeling"
    recommended_workflow: str = "standard"
    recommended_mode: str = "batch"
    data_adequacy: DataAdequacy = DataAdequacy.MISSING
    llm_should_collect: bool = False
    collection_plan: str = ""
    data_mismatch_warning: Optional[str] = None
    data_schemas: List[Dict[str, Any]] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_type": self.problem_type,
            "has_data_confidence": self.has_data_confidence,
            "data_subjects": self.data_subjects,
            "recommended_template": self.recommended_template,
            "recommended_workflow": self.recommended_workflow,
            "recommended_mode": self.recommended_mode,
            "data_adequacy": self.data_adequacy.value,
            "llm_should_collect": self.llm_should_collect,
            "collection_plan": self.collection_plan,
            "data_mismatch_warning": self.data_mismatch_warning,
            "data_schemas": self.data_schemas,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreflightReport":
        return cls(
            problem_type=data.get("problem_type", "综合"),
            has_data_confidence=float(data.get("has_data_confidence", 0.0)),
            data_subjects=list(data.get("data_subjects", [])),
            recommended_template=data.get("recommended_template", "math_modeling"),
            recommended_workflow=data.get("recommended_workflow", "standard"),
            recommended_mode=data.get("recommended_mode", "batch"),
            data_adequacy=DataAdequacy(data.get("data_adequacy", "missing")),
            llm_should_collect=bool(data.get("llm_should_collect", False)),
            collection_plan=data.get("collection_plan", ""),
            data_mismatch_warning=data.get("data_mismatch_warning"),
            data_schemas=list(data.get("data_schemas", [])),
            schema_version=data.get("schema_version", "1.0"),
        )


class DataMismatchError(Exception):
    """数据主题与题目不匹配"""

    def __init__(self, report: PreflightReport):
        self.report = report
        super().__init__(report.data_mismatch_warning or "数据主题与题目不匹配")


class DataCollectionFailedError(Exception):
    """LLM 自主搜集数据失败"""

    def __init__(self, collection_plan: str):
        self.collection_plan = collection_plan
        super().__init__("系统尝试自主搜集数据失败，请上传数据文件")


class _PreflightLLMClient(BaseAgent):
    """仅用于 Preflight 的轻量 LLM 调用客户端"""

    name = "preflight_llm_client"
    default_llm_backend = "minimax"

    def get_system_prompt(self) -> str:
        return (
            "你是一名严谨的科研流程规划师。你的任务是根据题目描述和数据特征，"
            "判断问题类型、数据是否充足、推荐合适的论文模板和工作流。"
            "你必须以 JSON 格式输出决策结果，不要输出任何解释文字。"
        )

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        # Preflight 不需要 execute，但 BaseAgent 要求实现
        return {}


class PreflightDecisionService:
    """Preflight 决策器"""

    # 允许的问题类型
    PROBLEM_TYPES = [
        "优化", "预测", "评价", "分类", "仿真", "网络", "物理", "测量", "综合", "未知"
    ]

    # 允许的工作流
    WORKFLOWS = ["standard", "quick", "deep_research", "code_focused", "research_paper"]

    # 允许的模式
    MODES = ["batch", "sequential"]

    # CCF-A 模板，默认优先推荐
    CCF_A_TEMPLATES = ["neurips_2024", "ieee_conference", "acm_sigconf", "springer_lncs"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider_id: Optional[str] = None,
    ):
        settings = get_settings()
        self._client = _PreflightLLMClient(
            api_key=api_key,
            api_base_url=api_base_url,
            model=model or settings.default_model,
            provider_id=provider_id,
            temperature=0.2,
            max_tokens=4096,
        )
        self._schema_extractor = get_schema_extractor()
        self._template_ids: Optional[List[str]] = None

    def _list_template_ids(self) -> List[str]:
        """懒加载模板 ID 列表"""
        if self._template_ids is None:
            try:
                from ..core.paper_templates import list_templates
                self._template_ids = [t.id for t in list_templates()]
            except Exception as e:
                logger.warning(f"加载模板列表失败: {e}")
                self._template_ids = [
                    "math_modeling", "coursework", "financial_analysis",
                    "research_survey", "ieee_conference", "neurips_2024",
                    "acm_sigconf", "springer_lncs",
                ]
        return self._template_ids

    async def decide(
        self,
        problem_text: str,
        data_files: Optional[List[str]] = None,
        template: Optional[str] = None,
        workflow_type: Optional[str] = None,
        mode: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> PreflightReport:
        """主决策入口

        Args:
            problem_text: 题目描述
            data_files: 已上传数据文件绝对路径列表
            template: 用户显式指定的模板（可选）
            workflow_type: 用户显式指定的工作流（可选）
            mode: 用户显式指定的模式（可选）
            project_name: 项目名，用于 self_collect 保存路径

        Returns:
            PreflightReport
        """
        data_files = data_files or []
        schemas = self._extract_schemas(data_files)

        # 调 LLM 做综合判断
        raw_decision = await self._call_llm_for_decision(
            problem_text=problem_text,
            schemas=schemas,
            user_template=template,
            user_workflow=workflow_type,
            user_mode=mode,
        )

        report = self._build_report(raw_decision, schemas, template, workflow_type, mode)

        # 如果用户明确指定了 template/workflow/mode，优先尊重用户选择
        if template:
            report.recommended_template = template
        if workflow_type:
            report.recommended_workflow = workflow_type
        if mode:
            report.recommended_mode = mode

        # 数据为空 → 强制 missing + collection_plan
        # 但 deep_research 工作流本身设计为自主搜索数据，不强制标记 MISSING
        effective_workflow = workflow_type or report.recommended_workflow
        if not data_files and effective_workflow != "deep_research":
            report.data_adequacy = DataAdequacy.MISSING
            report.has_data_confidence = 0.0
            if not report.collection_plan:
                report.collection_plan = self._default_collection_plan(problem_text, report.problem_type)
            report.llm_should_collect = True

        return report

    def _extract_schemas(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """对每个数据文件抽取 schema"""
        results = []
        for fp in file_paths:
            schema = self._schema_extractor.extract(fp)
            if schema:
                results.append(schema)
            else:
                logger.warning(f"Preflight 无法读取数据文件: {fp}")
        return results

    async def _call_llm_for_decision(
        self,
        problem_text: str,
        schemas: List[Dict[str, Any]],
        user_template: Optional[str],
        user_workflow: Optional[str],
        user_mode: Optional[str],
    ) -> Dict[str, Any]:
        """调 LLM 输出结构化决策 JSON"""
        template_list = self._list_template_ids()
        schema_text = self._schema_extractor.format_for_prompt(schemas) if schemas else "未提供数据文件。"

        user_prompt = self._build_decision_prompt(
            problem_text=problem_text,
            schema_text=schema_text,
            template_list=template_list,
            user_template=user_template,
            user_workflow=user_workflow,
            user_mode=user_mode,
        )

        messages = [
            {"role": "system", "content": self._client.get_system_prompt()},
            {"role": "user", "content": user_prompt},
        ]

        response = await self._client.call_llm(messages, temperature=0.2)
        content = self._extract_content(response)
        return self._parse_json(content)

    def _build_decision_prompt(
        self,
        problem_text: str,
        schema_text: str,
        template_list: List[str],
        user_template: Optional[str],
        user_workflow: Optional[str],
        user_mode: Optional[str],
    ) -> str:
        """构造 ReAct-style 决策 prompt"""
        return f"""请对以下科研任务进行预检决策。

## 题目描述
{problem_text}

## 数据特征
{schema_text}

## 可选模板
{json.dumps(template_list, ensure_ascii=False, indent=2)}

## 用户显式选择（可能为空）
- 模板: {user_template or "未指定"}
- 工作流: {user_workflow or "未指定"}
- 模式: {user_mode or "未指定"}

请按以下 JSON 格式输出决策结果（不要输出其他内容）：
{{
  "problem_type": "优化/预测/评价/分类/仿真/网络/物理/测量/综合/未知 之一",
  "has_data_confidence": 0.0-1.0,
  "data_subjects": ["数据主题1", "数据主题2"],
  "recommended_template": "必须从可选模板中选择一个",
  "recommended_workflow": "standard/quick/deep_research/code_focused/research_paper 之一",
  "recommended_mode": "batch/sequential 之一",
  "data_adequacy": "sufficient/insufficient/missing 之一",
  "llm_should_collect": true/false,
  "collection_plan": "如果数据不足或缺失，请给出具体的数据搜集计划：搜什么、去哪搜、预期格式。否则为空字符串。",
  "data_mismatch_warning": "如果数据主题与题目明显不匹配，给出警告；否则为空字符串。"
}}

注意：
- 模板与工作流已由系统绑定，请按以下映射推荐工作流：
  - math_modeling / financial_analysis → standard
  - coursework → quick
  - research_survey → deep_research
  - ieee_conference / neurips_2024 / acm_sigconf / springer_lncs → research_paper
- 如果题目偏向机器学习/深度学习理论研究，优先推荐 neurips_2024 或 ieee_conference。
- 如果题目偏向系统/多智能体/软件工程，优先推荐 acm_sigconf。
- 如果题目是中文数学建模赛题或明确要求建立数学模型，优先推荐 math_modeling。
- 如果题目只需要综述而无实验数据，可推荐 research_survey。
- has_data_confidence 要诚实反映数据是否足够支撑题目。
- 工作流为 deep_research 时，系统会自主搜集数据，不要强制标记 data_adequacy 为 MISSING。
"""

    @staticmethod
    def _extract_content(response: Dict[str, Any]) -> str:
        """从 call_llm 返回的统一格式中提取文本"""
        try:
            return response["choices"][0]["message"]["content"] or ""
        except Exception as e:
            logger.warning(f"解析 LLM 响应失败: {e}")
            return str(response)

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        """从 LLM 输出中解析 JSON，兼容 markdown 围栏"""
        content = content.strip()
        # 去掉 markdown 围栏
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 尝试从文本中提取第一个 JSON 对象
            match = re.search(r"\{{.*?\}}", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            logger.warning(f"LLM 输出不是合法 JSON: {content[:200]}")
            return {}

    def _build_report(
        self,
        raw: Dict[str, Any],
        schemas: List[Dict[str, Any]],
        user_template: Optional[str],
        user_workflow: Optional[str],
        user_mode: Optional[str],
    ) -> PreflightReport:
        """把 LLM 输出标准化为 PreflightReport"""
        template_list = self._list_template_ids()
        recommended_template = raw.get("recommended_template", "math_modeling")
        if recommended_template not in template_list:
            recommended_template = user_template or "math_modeling"

        recommended_workflow = raw.get("recommended_workflow", "standard")
        if recommended_workflow not in self.WORKFLOWS:
            recommended_workflow = user_workflow or "standard"

        recommended_mode = raw.get("recommended_mode", "batch")
        if recommended_mode not in self.MODES:
            recommended_mode = user_mode or "batch"

        problem_type = raw.get("problem_type", "综合")
        if problem_type not in self.PROBLEM_TYPES:
            problem_type = "综合"

        adequacy_str = raw.get("data_adequacy", "missing")
        try:
            data_adequacy = DataAdequacy(adequacy_str)
        except ValueError:
            data_adequacy = DataAdequacy.MISSING

        confidence = float(raw.get("has_data_confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        data_subjects = raw.get("data_subjects", [])
        if not isinstance(data_subjects, list):
            data_subjects = [str(data_subjects)]

        mismatch = raw.get("data_mismatch_warning") or None
        if mismatch and not isinstance(mismatch, str):
            mismatch = str(mismatch)
        # 如果 confidence 过低且数据非空，强制给出 mismatch 警告
        if confidence < 0.6 and schemas and not mismatch:
            mismatch = "数据与题目关联度低，建议重新上传匹配的数据文件。"

        return PreflightReport(
            problem_type=problem_type,
            has_data_confidence=confidence,
            data_subjects=[str(s) for s in data_subjects],
            recommended_template=recommended_template,
            recommended_workflow=recommended_workflow,
            recommended_mode=recommended_mode,
            data_adequacy=data_adequacy,
            llm_should_collect=bool(raw.get("llm_should_collect", False)),
            collection_plan=str(raw.get("collection_plan", "")),
            data_mismatch_warning=mismatch,
            data_schemas=schemas,
        )

    def _default_collection_plan(self, problem_text: str, problem_type: str) -> str:
        """无数据且无 LLM 计划时的默认搜集方案"""
        return (
            f"题目类型：{problem_type}。"
            f"请搜索与以下主题相关的公开数据集或文献：{problem_text[:100]}...。"
            "优先从 Kaggle、UCI Machine Learning Repository、Google Dataset Search、"
            "arXiv 摘要、政府开放数据平台获取 CSV/Excel/JSON 格式数据。"
        )

    async def self_collect_data(
        self,
        collection_plan: str,
        search_fn: Callable[[str], Any],
        task_id: str,
        project_name: Optional[str] = None,
        max_queries: int = 3,
    ) -> Tuple[bool, List[str]]:
        """根据 collection_plan 尝试自主搜集数据

        Args:
            collection_plan: LLM 给出的搜集计划文本
            search_fn: 搜索函数，接收 query 返回搜索结果（如 research_agent.execute）
            task_id: 任务 ID
            project_name: 项目名
            max_queries: 最大搜索查询数

        Returns:
            (success, new_file_paths)
        """
        logger.info(f"Task {task_id}: 开始自主搜集数据")
        target_dir = Path(get_project_data_dir(project_name))
        target_dir.mkdir(parents=True, exist_ok=True)

        # 从 collection_plan 中拆出候选查询（简单按行/分号拆分）
        queries = [q.strip("-• \t") for q in re.split(r"[\n;]", collection_plan) if len(q.strip()) > 5]
        queries = queries[:max_queries] if queries else [collection_plan[:200]]

        collected_files: List[str] = []
        for query in queries:
            try:
                result = await search_fn(query)
                # 期望 result 是 dict，可能包含 urls / papers / datasets
                urls = []
                if isinstance(result, dict):
                    urls.extend(result.get("urls", []))
                    urls.extend(result.get("datasets", []))
                    for paper in result.get("papers", []):
                        if isinstance(paper, dict):
                            urls.append(paper.get("url") or paper.get("pdf_url") or "")
                elif isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict):
                            urls.append(item.get("url") or item.get("pdf_url") or "")

                # 目前只做记录，不自动下载（避免安全风险）。实际下载可在 Phase 2 工具层补齐。
                for url in urls:
                    if url and isinstance(url, str):
                        logger.info(f"Task {task_id}: 发现候选数据 URL {url}")
                        # 占位：把 URL 写到 project_dir/self_collected_urls.txt
                        url_file = target_dir / "self_collected_urls.txt"
                        with open(url_file, "a", encoding="utf-8") as f:
                            f.write(f"{url}\n")
                        collected_files.append(str(url_file))
            except Exception as e:
                logger.warning(f"Task {task_id}: 自主搜集数据查询失败: {e}")

        # 保守策略：只有真正下载到文件才算 success
        # 当前版本先返回 True 表示已尝试，并把 URL 列表留给二次 preflight 或前端提示
        return len(collected_files) > 0, collected_files


# 全局单例
_preflight_service: Optional[PreflightDecisionService] = None


def get_preflight_service(
    api_key: Optional[str] = None,
    api_base_url: Optional[str] = None,
    model: Optional[str] = None,
    provider_id: Optional[str] = None,
) -> PreflightDecisionService:
    global _preflight_service
    if _preflight_service is None:
        _preflight_service = PreflightDecisionService(
            api_key=api_key,
            api_base_url=api_base_url,
            model=model,
            provider_id=provider_id,
        )
    return _preflight_service
