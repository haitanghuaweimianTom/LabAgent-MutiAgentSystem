"""实验设计 Agent —— Phase 2 流水线扩容。

定位：在建模（modeler）和求解（solver）之间插入"实验设计"步骤，
让系统在动手写代码前明确：

- baselines（基线方法 / 强基线 / SoTA）
- datasets（数据集 / 标注 / 来源 / 规模）
- metrics（评价指标 / 显著性检验）
- hardware_budget（GPU/CPU/内存预算）
- ablation_plan（消融实验组件表）
- splits（train/val/test 划分或 K-fold）

支持两种 action：
- ``design``：仅产出实验方案 JSON（不实际跑实验；默认）
- ``execute``：在 ``hardware_budget`` 允许时尝试本地小规模冒烟，
  失败回退到只产出方案。

设计原则：
- 严格控制幻觉：只产出 JSON，不编造具体实验结果数字。
- 通用领域：不做 CUMCM 领域假设；CCF-A 论文可复用于 ML / 系统 / 算法等。
- 模板驱动：与 :mod:`app.core.paper_templates` 协同，
  ``research_paper`` 等模板会主动触发。
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)


# 系统提示词（领域无关，CCF-A 风格）
EXPERIMENTATION_SYSTEM = """你是一个科研实验设计专家。你的任务是为给定问题设计严谨、可复现的实验方案。

【严格控制幻觉】
- 只产出方案 JSON，**不要**编造任何具体的实验结果数字
- baselines 只写方法名称（如 "Random Forest", "BERT-base"），不写数字
- datasets 只写公开名称（如 "MNIST", "CIFAR-10", "GLUE"），不写百分比
- 指标只写名称（如 "Accuracy", "F1", "BLEU-4"），不写真实值

【输出 schema（严格 JSON，无任何其他文字）】
{
  "baselines": [
    {"name": "方法名", "category": "baseline|strong|sota|ablation", "rationale": "为何选这个 baseline (≤30字)"},
    ...
  ],
  "datasets": [
    {"name": "数据集名", "size": "样本数（如 50k）", "source": "公开/私有", "license": "许可证（如 MIT/CC-BY-SA）"},
    ...
  ],
  "metrics": [
    {"name": "指标名", "direction": "higher_is_better|lower_is_better", "significance_test": "paired-t|wilcoxon|bootstrap|无"},
    ...
  ],
  "hardware_budget": {
    "gpu": "如 '1× A100 80GB' 或 'unknown'",
    "cpu": "如 '8 vCPU 32GB' 或 'unknown'",
    "training_time_estimate": "如 '<6h' 或 'unknown'",
    "feasible": true|false
  },
  "ablation_plan": [
    {"component": "组件名", "purpose": "剥离该组件验证其贡献 (≤30字)"},
    ...
  ],
  "splits": {
    "method": "train/val/test 或 K-fold 或 time-based",
    "ratios": "如 '8:1:1'",
    "seed": 42
  },
  "risks": ["可能的风险 1", ...]
}
"""


@AgentFactory.register("experimentation_agent")
class ExperimentationAgent(BaseAgent):
    """实验设计 Agent。"""

    name = "experimentation_agent"
    label = "实验设计专家"
    description = "设计严谨可复现的实验方案（baselines / datasets / metrics / ablation）"
    default_model = ""

    def get_system_prompt(self) -> str:
        return EXPERIMENTATION_SYSTEM

    async def execute(
        self,
        task_input: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行实验设计或实验执行。

        Args:
            task_input: 至少包含 ``problem_text``；可选 ``action``（``design``/``execute``）、
                ``sub_problems``、``modeling_result``、``solver_result``、``project_name``、``task_id``。
            context: 上下文（result 等）。

        Returns:
            标准化输出 dict：
            {
                "action": "design" | "execute",
                "plan": {baselines, datasets, metrics, hardware_budget, ablation_plan, splits, risks},
                "raw_text": "LLM 原始 JSON 字符串",
                "executed": bool,
                "experiment_result": {...} | None,
                "error": None | str,
            }
        """
        action = task_input.get("action", "design")
        problem_text = task_input.get("problem_text", context.get("problem_text", ""))
        sub_problems = task_input.get("sub_problems", [])
        modeling_result = task_input.get("modeling_result", {})
        solver_result = task_input.get("solver_result", {})
        project_name = task_input.get("project_name") or context.get("project_name")
        task_id = task_input.get("task_id") or context.get("task_id")

        if not problem_text:
            return {
                "action": action,
                "plan": self._empty_plan(),
                "raw_text": "",
                "executed": False,
                "experiment_result": None,
                "error": "missing problem_text",
            }

        # 构建 user prompt
        user_prompt = self._build_user_prompt(problem_text, sub_problems, modeling_result)

        try:
            raw_text = await self._call_llm_for_plan(user_prompt)
            plan = self._parse_plan(raw_text)
            executed = False
            experiment_result = None
            if action == "execute":
                executed, experiment_result = await self._try_execute(plan, modeling_result, solver_result, project_name, task_id)
            return {
                "action": action,
                "plan": plan,
                "raw_text": raw_text,
                "executed": executed,
                "experiment_result": experiment_result.to_dict() if experiment_result else None,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"experimentation_agent failed: {exc}; returning empty plan")
            return {
                "action": action,
                "plan": self._empty_plan(),
                "raw_text": "",
                "executed": False,
                "experiment_result": None,
                "error": str(exc),
            }

    # ---------- 内部方法 ----------

    def _build_user_prompt(
        self,
        problem_text: str,
        sub_problems: List[Dict[str, Any]],
        modeling_result: Dict[str, Any],
    ) -> str:
        parts: List[str] = ["【问题描述】", problem_text.strip()[:2000]]
        if sub_problems:
            parts.append("\n【子问题】")
            for sp in sub_problems[:5]:
                parts.append(f"- {sp.get('name', sp.get('id', '?'))}: {sp.get('description', '')[:200]}")
        if modeling_result:
            parts.append("\n【已有建模结果（用于辅助 baseline / metrics 设计）】")
            parts.append(json.dumps(modeling_result, ensure_ascii=False)[:1500])
        parts.append(
            "\n【请按系统提示词定义的 schema 输出 JSON，"
            "不要包含任何文字解释，只输出 JSON。】"
        )
        return "\n".join(parts)

    async def _call_llm_for_plan(self, user_prompt: str) -> str:
        """调 LLM 产出 plan JSON。失败时返回 ``{}``。"""
        # 优先用 base.call_llm（统一 LLM 调用，含重试+降级）
        try:
            messages = [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": user_prompt},
            ]
            response = await self.call_llm(messages=messages, temperature=0.2)
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            if isinstance(response, str):
                return response
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"call_llm path failed: {exc}")

        # 兜底：返回最小空 plan
        return json.dumps(self._empty_plan(), ensure_ascii=False)

    def _parse_plan(self, raw_text: str) -> Dict[str, Any]:
        """从 LLM 原始输出解析 plan。解析失败时回退到 empty plan。"""
        if not raw_text:
            return self._empty_plan()
        # 尝试提取 JSON 块
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if not match:
            return self._empty_plan()
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return self._empty_plan()

        # 校验与归一化
        return {
            "baselines": data.get("baselines", []) or [],
            "datasets": data.get("datasets", []) or [],
            "metrics": data.get("metrics", []) or [],
            "hardware_budget": data.get("hardware_budget", {}) or {},
            "ablation_plan": data.get("ablation_plan", []) or [],
            "splits": data.get("splits", {}) or {},
            "risks": data.get("risks", []) or [],
        }

    async def _try_execute(
        self,
        plan: Dict[str, Any],
        modeling_result: Dict[str, Any],
        solver_result: Dict[str, Any],
        project_name: Optional[str],
        task_id: Optional[str],
    ) -> tuple:
        """真正执行实验计划。

        返回 (executed: bool, experiment_result: ExperimentExecutorResult | None)。
        """
        budget = plan.get("hardware_budget") or {}
        # 默认允许执行；若 LLM 明确标记不可行，则跳过
        if budget.get("feasible") is False:
            logger.info("[ExperimentationAgent] hardware_budget.feasible=False，跳过实验执行")
            return False, None

        try:
            from ..services.experiment_executor import get_experiment_executor
            executor = get_experiment_executor()
            result = executor.execute_experiment_plan(
                plan=plan,
                modeling_result=modeling_result,
                solver_result=solver_result,
                project_name=project_name,
                task_id=task_id,
            )
            return result.executed, result
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[ExperimentationAgent] 实验执行失败: {exc}")
            return False, None

    def _try_smoke_execute(self, plan: Dict[str, Any]) -> bool:
        """已废弃：原有冒烟执行 stub，保留以兼容旧调用。"""
        return False

    @staticmethod
    def _empty_plan() -> Dict[str, Any]:
        return {
            "baselines": [],
            "datasets": [],
            "metrics": [],
            "hardware_budget": {"feasible": False, "note": "no LLM call made"},
            "ablation_plan": [],
            "splits": {},
            "risks": [],
        }
