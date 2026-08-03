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


# ============================================================================
# v8.4.6: 用户意图识别的规范化常量 —— 全仓单一可信源
# - PROBLEM_TYPES: 问题类型允许值（preflight / analyzer / orchestrator 共用）
# - KEYWORD_TEMPLATE_MAP: 关键词 → 模板 ID 强先验，LLM 输出非法/缺模板时兜底
# - WORKFLOW_TEMPLATE_COMPAT: 模板 ↔ 工作流一致性校验表
# 之前 PROBLEM_TYPES 在 preflight.py / analyzer_agent.py / langgraph_orchestrator.py
# 三处各自定义且不一致（v8.4.5 审计 #4），现统一从本模块导入。
# ============================================================================

# 问题类型允许值（规范化列表，三处共用）
PROBLEM_TYPES: List[str] = [
    "优化", "预测", "评价", "分类", "仿真", "网络", "物理", "测量", "综合", "未知",
]

# 竞赛关键词 —— 最高优先级，命中即 → math_modeling（竞赛格式不可覆盖）
# v8.4.6: 单独提取以避免和 math_modeling 的通用方法关键词混在一起被 neurips 抢匹配
_COMPETITION_KEYWORDS: List[str] = [
    "建模竞赛", "CUMCM", "数学建模", "全国大学生数学建模", "美赛", "MCM", "ICM",
]

# 关键词 → 模板 ID 映射（中英文混合，按命中优先级排序；首匹配生效）
# 用途：(a) 作为强先验注入 LLM prompt；(b) LLM 输出非 JSON / 缺 template 时的兜底
# v8.4.6: 优先级排序 —— 越具体的意图越靠前（survey/financial/coursework 优先于
# 通用 math_modeling/neurips），避免"深度学习综述"被 neurips 抢匹配。
# 竞赛关键词（→ math_modeling）在 _match_template_by_keywords 中先行扫描，优先级最高。
KEYWORD_TEMPLATE_MAP: "Dict[str, List[str]]" = {
    "research_survey": [
        # 综述/调研类（无需数据采集）—— survey 意图覆盖一切
        "综述", "调研", "现状", "文献综述", "review", "survey", "进展", "前沿",
    ],
    "financial_analysis": [
        # 金融分析 —— 域特定，优先于通用建模
        "金融", "股票", "投资", "风险评估", "收益", "证券", "期货", "期权",
        "量化", "回测", "组合投资",
    ],
    "coursework": [
        "课程作业", "期末项目", "实验报告", "coursework", "assignment",
    ],
    "neurips_2024": [
        # 深度学习/机器学习理论研究 —— 优先于 math_modeling 的通用方法关键词
        "神经网络", "LSTM", "深度学习", "机器学习", "transformer", "attention",
        "CNN", "RNN", "GAN", "强化学习", "对比学习", "自监督", "diffusion",
        "表征学习", "预训练",
    ],
    "math_modeling": [
        # 通用建模方法关键词（预测/回归/分类/优化/微分方程/统计/仿真/评价）
        # 竞赛关键词见 _COMPETITION_KEYWORDS（最高优先级，先行扫描）
        "预测模型", "回归", "分类", "优化", "线性规划", "整数规划", "非线性规划",
        "排队论", "微分方程", "统计分析", "时间序列", "ARIMA", "灰色预测",
        "层次分析", "AHP", "TOPSIS", "熵权法", "蒙特卡罗", "仿真", "评价",
        "调度", "路径规划", "TSP",
    ],
    "acm_sigconf": [
        # ACM 偏系统/工程/软件/数据库
        "软件工程", "多智能体", "系统设计", "数据库", "人机交互",
    ],
    "ieee_conference": [
        # IEEE 偏通信/信号/控制/机器人
        "通信", "信号处理", "控制工程", "机器人", "物联网",
    ],
    "springer_lncs": [
        # LNCS 偏 CV/模式识别
        "计算机视觉", "模式识别",
    ],
}

# 模板 ↔ 工作流一致性校验表
# - "allowed": 模板允许的工作流集合（None 表示全部允许）
# - "blocked": 模板禁止路由到的工作流集合
# 用于 _validate_template_workflow_consistency，纠正 LLM 给出的语义冲突组合
WORKFLOW_TEMPLATE_COMPAT: "Dict[str, Dict[str, Any]]" = {
    "research_survey": {
        # 综述类：走 deep_research（文献检索），禁止 iterative_solver（无需建模/求解）
        "allowed": ["deep_research", "research_paper"],
        "blocked": [],
    },
    "financial_analysis": {
        # 金融分析：standard 工作流 + financial_analyst_agent（由 _select_modeling_agent 路由）
        "allowed": ["standard"],
        "blocked": ["quick", "code_focused"],
    },
    "math_modeling": {
        "allowed": ["standard", "deep_research", "research_paper"],
        "blocked": [],
    },
    "coursework": {
        "allowed": ["quick", "standard"],
        "blocked": [],
    },
    "presentation": {
        # PPT 演示文稿：办公类，默认 quick 短链；允许 standard 长链（用户自定义）
        "allowed": ["quick", "standard"],
        "blocked": [],
    },
    "neurips_2024": {
        "allowed": ["research_paper", "deep_research"],
        "blocked": ["quick"],
    },
    "ieee_conference": {
        "allowed": ["research_paper", "deep_research"],
        "blocked": ["quick"],
    },
    "acm_sigconf": {
        "allowed": ["research_paper", "deep_research"],
        "blocked": ["quick"],
    },
    "springer_lncs": {
        "allowed": ["research_paper", "deep_research"],
        "blocked": ["quick"],
    },
}


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
    default_llm_backend = ""
    # v8.4.4: Preflight 只做模板/工作流分类决策，不需要知识库检索。
    # 跳过 KB 注入，避免遍历全部 KB 建 embedding（59个KB串行建引擎会
    # 阻塞事件循环数分钟，导致 submit 超时 + 后续 LLM 调用发不出）。
    skip_kb_injection: bool = True

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

    # v8.4.6: PROBLEM_TYPES 改为引用模块级常量（单一可信源），analyzer/orchestrator 也从此导入
    PROBLEM_TYPES = PROBLEM_TYPES

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

        report = self._build_report(raw_decision, schemas, template, workflow_type, mode, problem_text)

        # 如果用户明确指定了 template/workflow/mode，优先尊重用户选择
        if template:
            report.recommended_template = template
        if workflow_type:
            report.recommended_workflow = workflow_type
        if mode:
            report.recommended_mode = mode

        # v8.4.6: research_survey 是文献综述类，语义上不需要数据采集。
        # 跳过 data-collection preflight，直接标记 sufficient + 不触发 self_collect，
        # 避免 LLM 被 prompt 误导成 missing+should_collect 再被 v8.4.5 降级（审计 #2/#3）。
        effective_template = template or report.recommended_template
        if effective_template == "research_survey":
            report.data_adequacy = DataAdequacy.SUFFICIENT
            report.has_data_confidence = max(report.has_data_confidence, 0.6)
            report.llm_should_collect = False
            if not report.collection_plan:
                report.collection_plan = ""
            return report

        # 数据为空 → 根据工作流决定是否强制 missing
        # deep_research: 自主搜索，不拦截
        # quick/standard/code_focused: 不强制 missing，允许无数据运行
        # 只有明确需要数据的工作流才拦截
        effective_workflow = workflow_type or report.recommended_workflow
        workflows_needing_data = {"research_paper"}  # 需要数据的工作流
        if not data_files and effective_workflow in workflows_needing_data:
            report.data_adequacy = DataAdequacy.MISSING
            report.has_data_confidence = 0.0
            if not report.collection_plan:
                report.collection_plan = self._default_collection_plan(problem_text, report.problem_type)
            report.llm_should_collect = True
        elif not data_files and effective_workflow not in ("deep_research", "quick", "standard", "code_focused"):
            # 其他未知工作流，默认标记 missing
            report.data_adequacy = DataAdequacy.MISSING
            report.has_data_confidence = 0.0
            if not report.collection_plan:
                report.collection_plan = self._default_collection_plan(problem_text, report.problem_type)
            report.llm_should_collect = True

        # v8.4.5: 修正「LLM 判 missing 但工作流允许无数据」仍被拦截的 bug。
        # quick/standard/code_focused/deep_research 设计上允许无数据运行（建模在沙箱内
        # 生成或 deep_research 自主搜索），即使 LLM 判了 missing 也不应触发 submit 的
        # 数据门禁拦截。将这类工作流的 missing 降级为 sufficient，保留 collection_plan
        # 供 self_collect 分支使用（用户若选自采集仍可采，但不强制）。
        if not data_files and effective_workflow in ("deep_research", "quick", "standard", "code_focused"):
            if report.data_adequacy == DataAdequacy.MISSING:
                report.data_adequacy = DataAdequacy.SUFFICIENT
                report.has_data_confidence = max(report.has_data_confidence, 0.5)
                report.llm_should_collect = False

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
        """构造 ReAct-style 决策 prompt。

        v8.4.6: 把 KEYWORD_TEMPLATE_MAP 作为强先验注入 prompt，让 LLM 优先按
        关键词命中推荐模板；同时澄清 research_survey 无需数据采集（审计 #2/#3）。
        """
        # 把关键词表压成 prompt 友好的文本（仅展示候选模板的关键词）
        keyword_hints = []
        for tpl_id, keywords in KEYWORD_TEMPLATE_MAP.items():
            if tpl_id not in template_list:
                continue
            keyword_hints.append(f"  - {tpl_id}: {', '.join(keywords[:8])}")
        keyword_text = "\n".join(keyword_hints) if keyword_hints else "  (无)"

        return f"""请对以下科研任务进行预检决策。

## 题目描述
{problem_text}

## 数据特征
{schema_text}

## 可选模板
{json.dumps(template_list, ensure_ascii=False, indent=2)}

## 关键词 → 模板 强先验映射（请优先按此映射选模板）
{keyword_text}

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
  - research_survey → deep_research（仅文献检索，无需数据采集）
  - ieee_conference / neurips_2024 / acm_sigconf / springer_lncs → research_paper
- 请优先按上方「关键词 → 模板 强先验映射」选择模板；题目命中某模板关键词时直接推荐该模板。
- 如果题目偏向机器学习/深度学习理论研究，优先推荐 neurips_2024 或 ieee_conference。
- 如果题目偏向系统/多智能体/软件工程，优先推荐 acm_sigconf。
- 如果题目是中文数学建模赛题或明确要求建立数学模型，优先推荐 math_modeling。
- 如果题目只需文献综述/调研而无实验数据，推荐 research_survey。
- has_data_confidence 要诚实反映数据是否足够支撑题目。
- research_survey 是文献综述类，语义上不需要数据采集：当推荐模板为 research_survey 时，
  data_adequacy 设为 sufficient、llm_should_collect 设为 false、collection_plan 留空。
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
        """从 LLM 输出中解析 JSON，兼容 markdown 围栏与杂散文案。

        v8.4.6: 修复原 ``\\{{.*?\\}}`` 正则只匹配双花括号的 bug，改用与
        ``langgraph_orchestrator._extract_json_obj`` 一致的花括号深度匹配，
        能从 `````json ... ```` 围栏 + 前后解释文字中稳健提取首个 JSON 对象。
        """
        if not content:
            return {}
        s = content.strip()
        # 去掉 markdown 围栏（``` / ```json）
        if s.startswith("```"):
            lines = s.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        # 直接尝试整段解析
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        # 兜底：花括号深度匹配，提取首个完整 {...} 对象
        start = s.find("{")
        if start >= 0:
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(s)):
                c = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(s[start:i + 1])
                        except json.JSONDecodeError:
                            pass
        logger.warning(f"LLM 输出不是合法 JSON: {content[:200]}")
        return {}

    @staticmethod
    def _match_template_by_keywords(problem_text: str, allowed_templates: Optional[List[str]] = None) -> Optional[str]:
        """v8.4.6: 关键词 → 模板 ID 兜底匹配。

        当 LLM 输出非 JSON 或 recommended_template 缺失/非法时调用。
        优先级：_COMPETITION_KEYWORDS（→ math_modeling）> KEYWORD_TEMPLATE_MAP 首匹配。
        ``allowed_templates`` 限定候选范围（如已加载的模板 ID 列表），None 表示不限。
        """
        if not problem_text:
            return None
        text_lower = problem_text.lower()
        # 优先级 0：竞赛关键词 → math_modeling（竞赛格式不可覆盖）
        if "math_modeling" in (allowed_templates or ["math_modeling"]):
            for kw in _COMPETITION_KEYWORDS:
                if kw.lower() in text_lower:
                    return "math_modeling"
        # 优先级 1+：按 KEYWORD_TEMPLATE_MAP 顺序首匹配
        for tpl_id, keywords in KEYWORD_TEMPLATE_MAP.items():
            if allowed_templates and tpl_id not in allowed_templates:
                continue
            for kw in keywords:
                if kw.lower() in text_lower:
                    return tpl_id
        return None

    @staticmethod
    def _validate_template_workflow_consistency(
        template: str, workflow: str
    ) -> Tuple[str, Optional[str]]:
        """v8.4.6: 校验模板 ↔ 工作流一致性，自动纠正语义冲突组合。

        Returns:
            (corrected_workflow, warning) —— corrected_workflow 是纠正后的工作流；
            warning 非 None 时说明发生了自动纠正（调用方可记日志/告警）。
        """
        compat = WORKFLOW_TEMPLATE_COMPAT.get(template)
        if not compat:
            return workflow, None
        allowed = compat.get("allowed")
        blocked = compat.get("blocked", [])
        if workflow in blocked:
            # 命中显式禁止项 → 取 allowed 首项兜底
            corrected = allowed[0] if allowed else "standard"
            return corrected, (
                f"模板 {template} 不允许工作流 {workflow}，已纠正为 {corrected}"
            )
        if allowed and workflow not in allowed:
            # 不在 allowed 列表 → 取 allowed 首项兜底
            corrected = allowed[0]
            return corrected, (
                f"模板 {template} 建议工作流 {corrected}（LLM 给的 {workflow} 不在允许列表），已纠正"
            )
        return workflow, None

    def _build_report(
        self,
        raw: Dict[str, Any],
        schemas: List[Dict[str, Any]],
        user_template: Optional[str],
        user_workflow: Optional[str],
        user_mode: Optional[str],
        problem_text: str = "",
    ) -> PreflightReport:
        """把 LLM 输出标准化为 PreflightReport。

        v8.4.6: 三处加固
        - LLM 输出非 JSON / 缺 template / template 非法时，用 KEYWORD_TEMPLATE_MAP 兜底
        - 模板 ↔ 工作流一致性校验（_validate_template_workflow_consistency）
        - problem_type 用规范化 PROBLEM_TYPES 校验
        """
        template_list = self._list_template_ids()
        recommended_template = raw.get("recommended_template", "") or ""
        if recommended_template not in template_list:
            # v8.4.6: LLM 给的模板非法或缺省 → 关键词兜底 → 用户指定 → 默认 math_modeling
            kb_fallback = self._match_template_by_keywords(problem_text, template_list)
            recommended_template = (
                kb_fallback or user_template or "math_modeling"
            )
            if kb_fallback:
                logger.info(f"Preflight: LLM 模板非法/缺失，关键词兜底为 {kb_fallback}")

        recommended_workflow = raw.get("recommended_workflow", "standard") or "standard"
        if recommended_workflow not in self.WORKFLOWS:
            recommended_workflow = user_workflow or "standard"

        recommended_mode = raw.get("recommended_mode", "batch") or "batch"
        if recommended_mode not in self.MODES:
            recommended_mode = user_mode or "batch"

        # v8.4.6: 模板 ↔ 工作流一致性校验（纠正 LLM 给出的语义冲突组合）
        corrected_workflow, warn = self._validate_template_workflow_consistency(
            recommended_template, recommended_workflow
        )
        if warn:
            logger.info(f"Preflight: {warn}")
            recommended_workflow = corrected_workflow

        problem_type = raw.get("problem_type", "综合") or "综合"
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
        problem_text: str = "",
        problem_type: str = "",
    ) -> Tuple[bool, List[str]]:
        """根据 collection_plan 尝试自主搜集数据（v5.3.0: 实际下载而非只记录 URL）。

        v8.4.5: 新增 problem_text/problem_type 参数。金融选题优先走 akshare
        采集真实行情数据（新浪源，免 key），通用场景仍走 research_agent 搜索。

        Args:
            collection_plan: LLM 给出的搜集计划文本
            search_fn: 搜索函数，接收 query 返回搜索结果（如 research_agent.execute）
            task_id: 任务 ID
            project_name: 项目名
            max_queries: 最大搜索查询数
            problem_text: 题目原文（用于识别金融标的等）
            problem_type: 问题类型

        Returns:
            (success, new_file_paths) —— file_paths 是真实落盘的文件相对路径
        """
        logger.info(f"Task {task_id}: 开始自主搜集数据")
        from .self_collector import collect_urls, extract_urls_from_search_result, collect_financial_data

        collected_files: List[str] = []

        # ── 第一路：金融选题 → akshare 直采真实行情（免 key，新浪源稳定）──
        if problem_text:
            try:
                _, fin_paths = await collect_financial_data(
                    problem_text=problem_text,
                    project_name=project_name,
                    source_query=collection_plan[:80],
                )
                if fin_paths:
                    collected_files.extend(fin_paths)
                    logger.info(f"Task {task_id}: akshare 金融采集到 {len(fin_paths)} 个文件")
            except Exception as e:
                logger.warning(f"Task {task_id}: 金融数据采集异常: {e}")

        # ── 第二路：通用数据集采集（内置表 → GitHub → Kaggle 多路）──
        # 覆盖非金融模板（CCF-A 论文、ML、课程作业等）。金融选题已采到则跳过。
        if problem_text and not collected_files:
            try:
                from .self_collector import collect_datasets_multi
                _, ds_paths = await collect_datasets_multi(
                    problem_text=problem_text,
                    project_name=project_name,
                    source_query=collection_plan[:80],
                )
                if ds_paths:
                    collected_files.extend(ds_paths)
                    logger.info(f"Task {task_id}: 通用数据集采集到 {len(ds_paths)} 个文件")
            except Exception as e:
                logger.warning(f"Task {task_id}: 通用数据集采集异常: {e}")

        # ── 第三路：通用网页/论文搜索 → 抽 URL 下载（最终兜底）──
        if not collected_files:
            from .self_collector import collect_urls as _collect_urls, extract_urls_from_search_result as _extract
            queries = [q.strip("-• \t") for q in re.split(r"[\n;]", collection_plan) if len(q.strip()) > 5]
            queries = queries[:max_queries] if queries else [collection_plan[:200]]
            for query in queries:
                try:
                    result = await search_fn(query)
                    urls = extract_urls_from_search_result(result)
                    if not urls:
                        continue
                    # v5.3.0: 实际下载文件到 self_collected/
                    download_results = await collect_urls(
                        urls,
                        project_name=project_name,
                        source_query=query,
                        concurrency=4,
                        timeout_sec=30,
                        max_size_mb=50,
                    )
                    for dr in download_results:
                        if dr.filename:
                            logger.info(
                                f"Task {task_id}: 下载成功 {dr.url} → {dr.filename} ({dr.size}B)"
                            )
                            # 返回相对路径（v8.4.6: 从实际落盘路径计算，修复无项目时路径错位）
                            # 原实现硬编码 outputs/_global/data/self_collected/，但无项目时
                            # get_project_data_subdir(None) 返回 backend/data/uploads/self_collected/，
                            # 路径不匹配 → resolve_data_path 找不到 → data_quality_check 报 file_missing。
                            from ..core.paths import _PROJECT_ROOT, get_project_data_subdir
                            try:
                                actual = get_project_data_subdir(project_name, "self_collected") / dr.filename
                                rel = str(actual.relative_to(_PROJECT_ROOT))
                                collected_files.append(rel)
                            except Exception:
                                collected_files.append(dr.filename)
                        else:
                            logger.info(
                                f"Task {task_id}: 跳过 {dr.url} ({dr.error})"
                            )
                except Exception as e:
                    logger.warning(f"Task {task_id}: 自主搜集数据查询失败: {e}")

        # success = 至少下载到 1 个文件
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
