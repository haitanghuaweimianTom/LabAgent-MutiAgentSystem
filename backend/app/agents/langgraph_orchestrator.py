"""LangGraph 编排器（Phase 3）。

目标：用 ``langgraph.StateGraph`` 替换 ``orchestrator.py`` 中的硬编码 if-else 控制流。
当前版本为骨架实现：节点与条件边已定义，节点内部逐步填充。

开关：``backend/app/config.py`` 中的 ``use_langgraph_orchestrator``。
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

try:
    from langgraph.graph import StateGraph, END
    from langgraph.graph.message import add_messages
    LANGGRAPH_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False
    StateGraph = Any  # type: ignore
    END = "__end__"  # type: ignore
    add_messages = None  # type: ignore
    logging.getLogger(__name__).warning(f"langgraph 未安装或导入失败: {exc}")

from ..core.chat_room import create_chat_room, get_chat_room
from ..core.event_bus import get_event_bus
from ..core.memory import get_memory_manager
from ..services.result_validator import get_result_validator, get_cross_validator
from ..services.code_manifest import parse_manifest_from_dict, validate_manifest
from ..services.contract_validator import get_contract_validator
from ..services.fact_checker import get_fact_checker
from ..core.paths import get_project_output_dir
from ..core.state_store import get_task_result_store, _ref_key

logger = logging.getLogger(__name__)


# ===== v8.2: 组件化注入的 Base Template =====
# 受限模式下，Coder 只生成组件代码，系统自动注入到这些模板中

_BASE_TEMPLATE_MATH_MODELING = '''"""数学建模求解脚本（组件化注入模板）。"""
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, mean_squared_error

# {{COMPONENTS}}

def main():
    """主函数：加载数据、训练模型、输出结果。"""
    # 数据加载（由系统注入）
    # data = pd.read_csv("data.csv")

    # 模型训练（由组件注入）
    # model, results = train_model(data)

    # 结果输出
    # print(f"Accuracy: {results['accuracy']:.4f}")
    # print(f"F1 Score: {results['f1']:.4f}")

if __name__ == "__main__":
    main()
'''

_BASE_TEMPLATE_CCF_A = '''"""CCF-A 论文实验脚本（组件化注入模板）。"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import json
import sys

# {{COMPONENTS}}

def main():
    """主函数：训练模型、评估、输出指标。"""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 数据准备（由系统注入）
    # dataset = load_dataset()
    # loader = DataLoader(dataset, batch_size=32, shuffle=True)

    # 模型构建（由组件注入）
    # model = build_model().to(device)

    # 训练循环（由组件注入）
    # train(model, loader, device)

    # 评估
    # metrics = evaluate(model, loader, device)
    # print(json.dumps(metrics))

if __name__ == "__main__":
    main()
'''


class TaskState(TypedDict, total=False):
    """LangGraph 共享状态。

    包含三类字段：
    - 原有字段：维持与现有 15-Agent 架构的兼容性
    - 新增字段（v8.2 防沙箱死亡螺旋）：
      - error_count: 沙箱连续错误计数，用于熔断判定
      - execution_mode: 执行模式，"restricted"(组件化注入) | "jailbreak"(自由写代码)
      - ast_audit_passed: AST 审计是否通过（防造假 + 防崩溃双重检查）
      - metrics_trend: 指标历史趋势，用于判断模板瓶颈
      - circuit_breaker_threshold: 动态熔断阈值（越狱后降为 1）
    """

    messages: List[Dict[str, Any]]
    files: List[str]
    preflight: Optional[Dict[str, Any]]
    current_step: str
    paper_template: str
    workflow_type: str
    mode: str
    phase: str
    retry_count: int
    escalation_count: int
    solver_attempts: List[Dict[str, Any]]
    artifact_paths: List[str]
    cannot_solve_report: Optional[Dict[str, Any]]
    task_id: str
    problem_text: str
    project_name: Optional[str]
    knowledge_base_id: Optional[str]
    knowledge_base_ids: Optional[List[str]]  # v5.3.0: 多 KB 注入
    results: Dict[str, Any]
    sub_problems: List[Dict[str, Any]]
    should_pause: bool
    use_critique: bool  # 是否启用 Writer 自评质量循环
    requirement_plan: Optional[Dict[str, Any]]  # 需求分解结果
    innovation_analysis: Optional[Dict[str, Any]]  # 创新发现分析
    experiment_iterations: int  # 实验迭代次数
    task_summary: Optional[Dict[str, Any]]  # 任务总结报告
    user_messages: List[Dict[str, Any]]  # 用户在执行期间输入的消息
    last_input_check: float  # 上次检查用户消息的时间戳
    claims_trace: List[Dict[str, Any]]  # v8.1: claims↔日志追溯表
    # ===== v8.2: 防沙箱死亡螺旋三机制 =====
    error_count: int  # 沙箱连续错误计数（成功时重置为 0）
    execution_mode: str  # 执行模式: "restricted" | "jailbreak"
    ast_audit_passed: bool  # AST 审计是否通过（防造假 + 防崩溃）
    metrics_trend: List[float]  # 指标历史趋势（用于判断模板瓶颈）
    circuit_breaker_threshold: int  # 动态熔断阈值（默认 3，越狱后降为 1）
    # ===== v8.3: Contextual Bandit 自适应决策 =====
    bandit_action_id: int  # Bandit 上次选择的动作 ID
    bandit_context: List[float]  # Bandit 上次的上下文特征向量
    # ===== v8.4.3: 多智能体投票决策（是否联网检索论文/代码）=====
    research_decision: Optional[Dict[str, Any]]  # 投票结果：{allow_t0,allow_t1,allow_t2,tally,voters,round1,...}


@dataclass
class LangGraphConfig:
    """LangGraph 编排器配置。"""

    max_solver_iterations: int = 5
    max_solver_escalations: int = 2
    enable_peer_review: bool = True
    enable_experiment_design: bool = True
    enable_fact_check: bool = True


class LangGraphOrchestrator:
    """基于 LangGraph StateGraph 的任务编排器。"""

    # CCF-A 顶会模板集合
    _CCF_A_TEMPLATES = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs"}

    # 不需要建模的模板（调研/综述类）
    _TEMPLATES_NO_MODELING = {"research_survey", "research_review", "literature_review"}

    # 不需要建模的工作流类型
    _WORKFLOWS_NO_MODELING = {"deep_research", "survey"}

    def __init__(
        self,
        agents: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ):
        self.agents = agents
        self.cfg = LangGraphConfig(**(config or {}))
        self._result_store = get_task_result_store()
        self._graph = self._build_graph() if LANGGRAPH_AVAILABLE else None

        # v8.3: Contextual Bandit 自适应重试决策
        from ..core.contextual_bandit import ContextualBanditDecision
        model_dir = str(Path(__file__).resolve().parent.parent.parent / "data" / "models")
        self._bandit = ContextualBanditDecision(model_dir=model_dir)

    def _resolve_results(self, state: TaskState) -> Dict[str, Any]:
        """把 state 中的 result 引用还原为实际 Agent 输出。"""
        refs = state.get("results", {})
        task_id = state["task_id"]
        resolved: Dict[str, Any] = {}
        for agent_name, value in refs.items():
            if isinstance(value, str) and value.startswith("__ref__"):
                resolved[agent_name] = self._result_store.get(task_id, agent_name, {})
            else:
                resolved[agent_name] = value
        return resolved

    def _set_result(self, state: TaskState, agent_name: str, output: Any) -> Dict[str, Any]:
        """把 Agent 输出写入外部 store，并返回用于 state 的引用 dict。"""
        task_id = state["task_id"]
        self._result_store.set(task_id, agent_name, output)
        return {agent_name: _ref_key(agent_name)}

    # ------------------------------------------------------------------
    # 建模 Agent 选择
    # ------------------------------------------------------------------
    @classmethod
    def _select_modeling_agent(cls, template: str, workflow_type: str) -> str:
        """根据模板和工作流类型选择合适的建模 Agent。

        Returns:
            空字符串表示跳过建模；否则返回对应 Agent 名称。
        """
        if template in cls._TEMPLATES_NO_MODELING or workflow_type in cls._WORKFLOWS_NO_MODELING:
            return ""
        if template == "financial_analysis":
            return "financial_analyst_agent"
        if template in cls._CCF_A_TEMPLATES or workflow_type == "research_paper":
            return "algorithm_engineer_agent"
        return "modeler_agent"

    # ------------------------------------------------------------------
    # 归一化方法
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_algorithm_engineer_output(raw: dict) -> dict:
        """将 algorithm_engineer_agent 的原始输出归一化为标准 modeler_agent 格式。

        把 problem_formulation / proposed_method / experiment_design / code_hints 等
        映射到兼容 solver/writer 的 sub_problem_models 结构。
        """
        if not raw or not isinstance(raw, dict):
            return {"sub_problem_models": []}

        formulation = raw.get("problem_formulation", {})
        method = raw.get("proposed_method", {})

        # 提取变量：优先使用 hyperparameters，回退到 notation
        variables = []
        for hp in method.get("hyperparameters", []):
            if isinstance(hp, dict):
                variables.append(
                    {
                        "name": str(hp.get("name", "")),
                        "description": str(hp.get("description", "")),
                        "type": "连续",
                        "range": f"default={hp.get('default', '')}",
                    }
                )
        if not variables:
            for k, v in formulation.get("notation", {}).items():
                variables.append({"name": str(k), "description": str(v), "type": "连续", "range": "待确定"})

        # 提取约束
        constraints = []
        for c in formulation.get("constraints", []):
            if isinstance(c, dict):
                constraints.append(
                    {
                        "name": c.get("name", "约束"),
                        "expression": c.get("expression", str(c)),
                        "type": c.get("type", "不等式"),
                    }
                )
            elif isinstance(c, str):
                constraints.append({"name": "约束", "expression": c, "type": "不等式"})

        normalized_model = {
            "sub_problem_index": 0,
            "sub_problem_name": "整体问题",
            "model_type": "algorithm_design",
            "model_name": method.get("name", "") or method.get("name_cn", "Proposed Method"),
            "decision_variables": variables,
            "parameters": [],
            "objective_function": formulation.get("objective", ""),
            "constraints": constraints,
            "algorithm": {
                "name": method.get("name", ""),
                "description": method.get("core_idea", ""),
            },
            "model_assumptions": formulation.get("assumptions", []),
            "model_advantages": method.get("key_innovation", []),
            "model_limitations": method.get("limitations", []),
            "_agent_source": "algorithm_engineer_agent",
            "_raw_output": raw,
        }

        return {"sub_problem_models": [normalized_model]}

    @staticmethod
    def _normalize_financial_analyst_output(raw: dict) -> dict:
        """将 financial_analyst_agent 的原始输出归一化为标准 modeler_agent 格式。

        从 financial_model / data_requirements / risk_analysis / backtest_design 提取字段。
        """
        if not raw or not isinstance(raw, dict):
            return {"sub_problem_models": []}

        formulation = raw.get("problem_formulation", {})
        financial_model = raw.get("financial_model", {})
        risk = raw.get("risk_analysis", {})

        # 提取变量：优先使用 parameters，回退到 key_variables
        variables = []
        for p in financial_model.get("parameters", []):
            if isinstance(p, dict):
                variables.append(
                    {
                        "name": str(p.get("name", "")),
                        "description": str(p.get("meaning", "")),
                        "type": "连续",
                        "range": f"estimation={p.get('estimation', '')}",
                    }
                )
        if not variables:
            for k, v in formulation.get("key_variables", {}).items():
                variables.append({"name": str(k), "description": str(v), "type": "连续", "range": "待确定"})

        # 提取约束：从风险/局限中转换
        constraints = []
        for lim in risk.get("limitations", []):
            if isinstance(lim, str):
                constraints.append({"name": "风险/局限", "expression": lim, "type": "不等式"})

        normalized_model = {
            "sub_problem_index": 0,
            "sub_problem_name": "整体问题",
            "model_type": "financial_model",
            "model_name": financial_model.get("name", "") or financial_model.get("name_cn", "Financial Model"),
            "decision_variables": variables,
            "parameters": [],
            "objective_function": financial_model.get("model_specification", ""),
            "constraints": constraints,
            "algorithm": {
                "name": financial_model.get("name", ""),
                "description": financial_model.get("core_idea", ""),
            },
            "model_assumptions": formulation.get("assumptions", []),
            "model_advantages": [f"Domain: {formulation.get('domain', '')}"] if formulation.get("domain") else [],
            "model_limitations": risk.get("limitations", []),
            "_agent_source": "financial_analyst_agent",
            "_raw_output": raw,
        }

        return {"sub_problem_models": [normalized_model]}

    # ------------------------------------------------------------------
    # 防编造校验
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_no_fabrication(agent_name: str, output: dict) -> dict:
        """检测 Agent 输出中可能的编造内容。

        Args:
            agent_name: Agent 名称，用于选择特定校验规则。
            output: Agent 原始输出字典。

        Returns:
            包含 _fabrication_flags、_fabrication_score、_validated_at 的字典。
        """
        flags: List[str] = []
        score = 0.0

        # 通用规则：检测无参考文献标记的作者-年份引用
        text = json.dumps(output, ensure_ascii=False)

        # 匹配 (Author et al., YYYY) 或 (Author, YYYY) 模式
        author_year_pattern = re.compile(r'\([A-Z][a-z]+(?:\s+et\s+al\.?)?,\s*\d{4}[a-z]?\)')
        author_year_matches = author_year_pattern.findall(text)

        # 检测是否有对应的 [N] 编号引用
        ref_pattern = re.compile(r'\[\d+\]')
        ref_matches = ref_pattern.findall(text)

        if author_year_matches and len(ref_matches) < len(author_year_matches) * 0.5:
            flags.append(
                f"检测到 {len(author_year_matches)} 处作者-年份引用，"
                f"但只有 {len(ref_matches)} 处编号引用，可能存在编造引用"
            )
            score += min(0.3, len(author_year_matches) * 0.05)

        # 特定 Agent 规则
        if agent_name == "financial_analyst_agent":
            # 检测无来源说明的具体价格/收益率
            price_pattern = re.compile(r'\$\d+\.\d{2}')
            yield_pattern = re.compile(r'[+-]?\d+\.\d+%')
            price_matches = price_pattern.findall(text)
            yield_matches = yield_pattern.findall(text)

            # 检查是否有数据来源关键词
            source_keywords = ["Yahoo Finance", "Bloomberg", "Wind", "CSMAR", "国泰安",
                             "来源", "source", "data from", "historical"]
            has_source = any(kw.lower() in text.lower() for kw in source_keywords)

            if (price_matches or yield_matches) and not has_source:
                flags.append(
                    f"检测到 {len(price_matches)} 处价格数据和 {len(yield_matches)} 处收益率数据，"
                    f"但未找到数据来源说明"
                )
                score += min(0.4, (len(price_matches) + len(yield_matches)) * 0.03)

        elif agent_name == "algorithm_engineer_agent":
            # 检测无引用的具体 baseline 数字（如 95.2%、F1=0.89）
            baseline_pattern = re.compile(r'\b(?:\d{2,3}\.\d%|F1\s*=\s*0\.\d+|Acc\s*=\s*\d+\.\d%|'
                                          r'Accuracy\s*=\s*\d+\.\d%|Precision\s*=\s*\d+\.\d%|'
                                          r'Recall\s*=\s*\d+\.\d%)')
            baseline_matches = baseline_pattern.findall(text)

            # 检查是否有引用或来源说明
            citation_keywords = ["cite", "reported", "from", "according to", "文献",
                                 "论文", "待确认", "待实验验证", "需查阅原文"]
            has_citation = any(kw.lower() in text.lower() for kw in citation_keywords)

            if baseline_matches and not has_citation:
                flags.append(
                    f"检测到 {len(baseline_matches)} 处具体性能数字，"
                    f"但未找到引用或来源说明"
                )
                score += min(0.4, len(baseline_matches) * 0.08)

        score = min(1.0, score)

        return {
            "_fabrication_flags": flags,
            "_fabrication_score": round(score, 3),
            "_validated_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    async def run(
        self,
        task_id: str,
        problem_text: str,
        workflow: Optional[List[Dict[str, Any]]] = None,
        data_files: Optional[List[str]] = None,
        mode: str = "batch",
        project_name: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None,  # v5.3.0: 多 KB
        template: str = "math_modeling",
        workflow_type: str = "standard",
        preflight_report: Optional[Dict[str, Any]] = None,
        use_critique: bool = True,
    ) -> Dict[str, Any]:
        """运行完整工作流。"""
        if not LANGGRAPH_AVAILABLE or self._graph is None:
            raise RuntimeError("langgraph 未安装，无法使用 LangGraphOrchestrator")

        room = create_chat_room(task_id, problem_text)
        mm = get_memory_manager()
        wm, em = mm.create_task_memory(task_id)
        wm.update_problem(text=problem_text[:500], template=template, workflow_type=workflow_type)
        em.record("coordinator", "task_start", f"LangGraph 任务开始：{problem_text[:100]}")

        # v5.3.0: 兼容旧单 KB
        if knowledge_base_ids is None and knowledge_base_id:
            knowledge_base_ids = [knowledge_base_id]

        initial_state: TaskState = {
            "messages": [],
            "files": data_files or [],
            "preflight": preflight_report,
            "current_step": "preflight_decision",
            "paper_template": template,
            "workflow_type": workflow_type,
            "mode": mode,
            "phase": "phase1",
            "retry_count": 0,
            "escalation_count": 0,
            "solver_attempts": [],
            "artifact_paths": [],
            "cannot_solve_report": None,
            "task_id": task_id,
            "problem_text": problem_text,
            "project_name": project_name,
            "knowledge_base_id": knowledge_base_id,
            "knowledge_base_ids": knowledge_base_ids,
            "results": {},
            "sub_problems": [],
            "should_pause": False,
            "revision_count": 0,
            "use_critique": use_critique,
            "user_messages": [],
            "last_input_check": time.time(),
            "claims_trace": [],  # v8.1: claims↔日志追溯表
            # v8.2: 防沙箱死亡螺旋三机制初始状态
            "error_count": 0,
            "execution_mode": "restricted",  # 默认受限模式，组件化注入
            "ast_audit_passed": False,
            "metrics_trend": [],
            "circuit_breaker_threshold": 3,  # 默认 3 次错误触发熔断
            # v8.3: Contextual Bandit 初始状态
            "bandit_action_id": 0,
            "bandit_context": [0.0] * 7,
        }

        # 检查是否可以从 checkpoint 恢复（断点续传）
        restored_state = self._restore_from_checkpoint(task_id, initial_state)
        if restored_state is not initial_state:
            logger.info(f"[LangGraph:{task_id}] 从 checkpoint 恢复，继续执行")
            self._post_chat(task_id, "coordinator", "🔄 从断点恢复，继续执行...")

        try:
            # v8.4: 图节点数增至 40，单条最长路径（pre 链 + 主链 + post 校验链）变长，
            # 加上条件重试/experiment 迭代，默认 recursion_limit=25 不够，放宽至 80。
            final_state = await self._graph.ainvoke(
                restored_state,
                config={"recursion_limit": 80},
            )
            # 持久化结果
            self._save_results(task_id, final_state)
            em.record("coordinator", "task_end", f"LangGraph 任务完成：{final_state.get('current_step', 'done')}")

            # Agent 记忆自进化：从任务结果回写到每个 Agent 的独立记忆
            try:
                self._evolve_agent_profiles(task_id, final_state, problem_text)
            except Exception as e:
                logger.warning(f"AgentProfile 自进化失败（不影响任务结果）: {e}")

            # 将任务级知识库合并到项目知识库（保留论文内容供未来任务参考）
            task_kb_id = final_state.get("task_kb_id")
            if task_kb_id:
                try:
                    from ..core.knowledge_manager import get_knowledge_manager
                    km = get_knowledge_manager()
                    task_base = km._bases.get(task_kb_id)
                    if task_base and project_name:
                        # 查找或创建项目级知识库
                        proj_kb_name = f"project_{project_name}"
                        proj_base = None
                        for bid, b in km._bases.items():
                            if b.name == proj_kb_name:
                                proj_base = b
                                break
                        if not proj_base:
                            proj_base = km.create_base(
                                name=proj_kb_name,
                                description=f"项目 {project_name} 的论文知识库",
                                scope="project",
                            )
                        # 合并论文分块
                        if hasattr(task_base, 'items') and task_base.items:
                            for item in task_base.items:
                                proj_base.items.append(item)
                            km._save_bases()
                            logger.info(f"任务级知识库已合并到项目知识库: {proj_kb_name} ({len(task_base.items)} 篇)")
                        # 删除任务级 KB
                        km.delete_base(task_kb_id)
                        logger.info(f"任务级知识库已清理: {task_kb_id}")
                except Exception as e:
                    logger.debug(f"合并任务级知识库失败: {e}")

            return {
                "task_id": task_id,
                "status": "completed",
                "results": self._resolve_results(final_state),
                "sub_problems": final_state.get("sub_problems", []),
                "solver_attempts": len(final_state.get("solver_attempts", [])),
                "current_step": final_state.get("current_step", ""),
                "cannot_solve_report": final_state.get("cannot_solve_report"),
            }
        except Exception as exc:
            logger.error(f"LangGraph run failed for {task_id}: {exc}", exc_info=True)
            em.record("coordinator", "task_error", f"LangGraph 任务失败：{exc}")
            raise

    def _restore_from_checkpoint(self, task_id: str, initial_state: TaskState) -> TaskState:
        """尝试从 checkpoint 恢复任务状态。如果无 checkpoint 或恢复失败，返回 initial_state。"""
        from ..core.task_persistence import load_task_checkpoints, load_task_metadata

        try:
            meta = load_task_metadata(task_id)
            if not meta:
                return initial_state

            status = meta.get("status", "")
            if status not in ("interrupted", "paused", "running"):
                return initial_state

            checkpoints = load_task_checkpoints(task_id)
            if not checkpoints:
                return initial_state

            # 按时间排序，取最新的 checkpoint
            checkpoints.sort(key=lambda x: x.get("saved_at", ""))
            last_checkpoint = checkpoints[-1]
            last_step = last_checkpoint.get("step", "")
            last_payload = last_checkpoint.get("payload", {})

            logger.info(f"[LangGraph:{task_id}] 恢复 checkpoint: step={last_step}, saved_at={last_checkpoint.get('saved_at')}")

            # 重建 results（从所有 checkpoints 聚合）
            restored_results = {}
            for cp in checkpoints:
                step_name = cp.get("step", "")
                payload = cp.get("payload", {})
                if step_name and payload:
                    restored_results[step_name] = payload

            # 从 task_result.json 加载已有结果（更完整）
            try:
                from ..core.task_persistence import load_task_result
                task_result = load_task_result(task_id)
                if task_result and task_result.get("output"):
                    restored_results.update(task_result["output"])
            except Exception:
                pass

            # 确定恢复后的 current_step（用于路由到下一个节点）
            step_to_node = {
                "analyzer_agent": "analyzer_done",
                "data_agent": "data_done",
                "research_agent": "research_done",
                "modeler_agent": "modeler_done",
                "algorithm_engineer_agent": "algorithm_engineer_done",
                "financial_analyst_agent": "financial_analyst_done",
                "solver_agent": "iterative_solver_done",
                "experiment_agent": "experiment_done",
                "writer_agent": "writer_done",
                "peer_review_agent": "peer_review_done",
                "figure_agent": "figure_done",
                "fact_check_agent": "fact_check_done",
            }
            current_step = step_to_node.get(last_step, "preflight_decision_done")

            # 构建恢复后的 state
            restored_state: TaskState = {
                **initial_state,
                "current_step": current_step,
                "results": restored_results,
                "phase": meta.get("phase", initial_state.get("phase", "phase1")),
                "revision_count": meta.get("revision_count", 0),
                "retry_count": meta.get("retry_count", 0),
                "escalation_count": meta.get("escalation_count", 0),
            }

            # 恢复子问题列表（如果存在）
            analyzer_result = restored_results.get("analyzer_agent", {})
            if analyzer_result and analyzer_result.get("sub_problems"):
                restored_state["sub_problems"] = analyzer_result["sub_problems"]

            # 恢复 cannot_solve_report
            if meta.get("cannot_solve_report"):
                restored_state["cannot_solve_report"] = meta["cannot_solve_report"]

            return restored_state

        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 从 checkpoint 恢复失败: {e}，将从头开始")
            return initial_state

    def _evolve_agent_profiles(
        self,
        task_id: str,
        final_state: Dict[str, Any],
        problem_text: str,
    ):
        """任务完成后回写每个 Agent 的独立经验。"""
        from ..core.agent_memory import get_agent_profile

        results = self._resolve_results(final_state)
        sub_problems = final_state.get("sub_problems", [])
        problem_type = (results.get("analyzer_agent") or {}).get("problem_type", "")

        # 各 Agent 经验收集规则
        evolution_map = {
            "analyzer_agent": self._extract_analyzer_case,
            "modeler_agent": self._extract_modeler_case,
            "solver_agent": self._extract_solver_case,
            "writer_agent": self._extract_writer_case,
            "research_agent": self._extract_research_case,
            "algorithm_engineer_agent": self._extract_modeler_case,
            "financial_analyst_agent": self._extract_modeler_case,
        }

        for agent_name, extractor in evolution_map.items():
            try:
                profile = get_agent_profile(agent_name)
                output = results.get(agent_name, {})
                if not output:
                    continue
                case_type, method, outcome, impact, summary = extractor(output, problem_text, problem_type, final_state)
                if case_type and method:
                    profile.add_case(
                        case_type=case_type,
                        task_id=task_id,
                        problem_type=problem_type,
                        method=method,
                        outcome=outcome,
                        impact_score=impact,
                        summary=summary,
                    )
                    logger.debug(f"Agent {agent_name} 经验回写: {case_type} (impact={impact:.2f})")
            except Exception as e:
                logger.debug(f"Agent {agent_name} 经验回写失败: {e}")

    @staticmethod
    def _extract_analyzer_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        sub_problems = output.get("sub_problems", [])
        return (
            "success" if sub_problems else None,
            f"问题分解: {len(sub_problems)} 个子问题" if sub_problems else "",
            f"识别问题类型: {problem_type}",
            0.6,
            f"题目类型={problem_type}, 子问题数={len(sub_problems)}",
        )

    @staticmethod
    def _extract_modeler_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        models = output.get("sub_problem_models", [])
        if not models:
            return None, "", "", 0.0, ""
        methods = ", ".join(m.get("model_type", "未知") for m in models[:3])
        return (
            "success",
            f"建模: {methods}",
            f"为 {len(models)} 个子问题建立模型",
            0.7,
            f"模型类型={methods}",
        )

    @staticmethod
    def _extract_solver_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        solutions = output.get("sub_problem_solutions", [])
        attempts = state.get("solver_attempts", [])
        if not solutions:
            return "failure", "求解失败", "求解全部失败", 0.4, "求解失败案例"
        success_rate = sum(1 for s in solutions if s.get("results", {}).get("execution_success", True)) / len(solutions)
        return (
            "success" if success_rate > 0.7 else "failure",
            f"求解: 成功率 {success_rate:.0%}",
            f"{len(solutions)} 个子问题求解（尝试 {len(attempts)} 次）",
            0.6 + success_rate * 0.3,
            f"成功率={success_rate:.2f}, 尝试次数={len(attempts)}",
        )

    @staticmethod
    def _extract_writer_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        chapters = output.get("chapters", []) or []
        latex = output.get("latex_code", "") or output.get("latex", "")
        if not latex:
            return None, "", "", 0.0, ""
        chapter_count = len(chapters) if chapters else latex.count("\\section")
        return (
            "success",
            f"写作: {chapter_count} 章节",
            f"生成 {chapter_count} 章节 LaTeX（{len(latex)} 字符）",
            0.7,
            f"章节数={chapter_count}, LaTeX长度={len(latex)}",
        )

    @staticmethod
    def _extract_research_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        papers = output.get("papers", []) or []
        if not papers:
            return None, "", "", 0.0, ""
        return (
            "success",
            f"文献检索: {len(papers)} 篇",
            f"从 arXiv 检索 {len(papers)} 篇论文",
            min(0.8, 0.4 + len(papers) * 0.05),
            f"检索到{len(papers)}篇相关论文",
        )

    # ------------------------------------------------------------------
    # 数据驱动的 Agent 裁剪配置（按 problem_type 跳过不必要的 Agent）
    # ------------------------------------------------------------------

    # 不需要 data_agent（纯理论 / 算法类）
    _PROBLEM_TYPES_NO_DATA = {"网络", "物理", "仿真", "测量", "综合"}

    # 不需要 research_agent（已知领域或纯方法论）
    _PROBLEM_TYPES_NO_RESEARCH = {
        "物理", "测量",
        # v8.4.2: 扩展"无需文献检索"的问题类型——纯建模/算法题靠数学方法即可，
        # 强制走 MCP 联网搜文献既慢又易因搜索超时拖垮任务（如 TSP/运筹/线性规划）。
        "优化",   # TSP/路径规划/线性规划/整数规划——纯数学建模，不需文献支撑
        "仿真",   # 仿真建模——基于机理/数值方法，通常不需文献
        "未知",   # 类型不明时不过度搜索，避免无效联网
    }

    @classmethod
    def _should_skip_data(cls, problem_type: str, has_data_files: bool) -> bool:
        """判断是否跳过 data_agent。"""
        if not has_data_files:
            return True
        if problem_type in cls._PROBLEM_TYPES_NO_DATA:
            return True
        return False

    @classmethod
    def _should_skip_research(cls, problem_type: str, workflow_type: str) -> bool:
        """判断是否跳过 research_agent。"""
        if workflow_type in ("quick", "code_focused"):
            return True
        if problem_type in cls._PROBLEM_TYPES_NO_RESEARCH:
            return True
        return False

    # ------------------------------------------------------------------
    # v8.4.3: 多智能体投票决策节点（research_vote）
    # ------------------------------------------------------------------
    # T0（维基/百度百科/普通网页）默认放行，无需投票；
    # T1（arXiv 论文 MCP）需过半数投票放行；
    # T2（GitHub/CSDN 代码检索）仅复杂任务且过半数投票放行。
    # 快路径：纯建模/仿真/物理类问题类型直接 no-research，0 次 LLM 调用。
    # 降级：投票 LLM 调用失败→回退白名单 _should_skip_research，不卡死任务。
    _VOTER_DESC = {
        "analyzer_agent": "题目本质分析者：判断该题是否需要外部文献/前沿知识支撑",
        "modeler_agent": "建模消费者：判断建模是否需要方法/算法参考",
        "peer_review_agent": "严谨审查者：判断论文无引用支撑是否站不住脚",
        "writer_agent": "写作视角：判断论文论述是否需要文献/代码佐证",
        "financial_analyst_agent": "金融视角：判断金融风险分析是否需要前沿方法/数据源",
        "algorithm_engineer_agent": "算法视角：判断是否需要检索算法实现参考",
        "coordinator": "全局视角：综合任务目标判断检索必要性",
    }
    # 复杂任务模板/工作流（触发 5 人大 panel + 开放 T2 代码检索）
    _COMPLEX_TEMPLATES = {"financial_analysis", "research_survey", "frontier_academic"}
    _COMPLEX_WORKFLOWS = {"deep_research", "research_paper"}

    async def _node_research_vote(self, state: TaskState) -> TaskState:
        """多智能体投票：是否联网检索论文(T1)/代码(T2)。analyzer 后、parallel_analysis 前。"""
        import asyncio

        state = await self._check_user_input(state)
        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_phase_change(task_id, "research_vote", "研究决策投票：多智能体讨论是否联网检索")
        self._update_progress(task_id, state["problem_text"], 18, "研究决策投票中")

        problem_text = state["problem_text"]
        analyzer_out = self._resolve_results(state).get("analyzer_agent", {}) or {}
        problem_type = analyzer_out.get("problem_type", "未知")
        template = state.get("paper_template", "math_modeling")
        workflow = state.get("workflow_type", "standard")

        # ---- 快路径：纯建模/已知领域 → 0 LLM，直接 no-research ----
        if self._should_skip_research(problem_type, workflow):
            decision = {
                "allow_t0": True, "allow_t1": False, "allow_t2": False,
                "mode": "fast_path",
                "reason": f"问题类型={problem_type}，纯建模/已知领域，无需文献检索",
                "tally": {"t1": "0/0 (快路径)", "t2": "0/0 (快路径)"},
                "voters": [], "round1": [],
            }
            logger.info(f"[LangGraph:{task_id}] research_vote: fast_path (problem_type={problem_type}) → no research")
            self._post_chat(task_id, "coordinator", f"研究决策：问题类型「{problem_type}」为纯建模/已知领域，跳过文献检索")
            bus.emit_agent_complete(task_id, "research_vote", "research_vote", "快路径：无需文献检索")
            return {**state, "research_decision": decision, "current_step": "research_vote_done"}

        # ---- 复杂度判定 → panel 规模 ----
        is_complex = (template in self._COMPLEX_TEMPLATES) or (workflow in self._COMPLEX_WORKFLOWS)
        base_pool = ["analyzer_agent", "modeler_agent", "peer_review_agent"]
        extra_pool = ["writer_agent", "financial_analyst_agent", "algorithm_engineer_agent", "coordinator"]
        voters = [(r, self._VOTER_DESC.get(r, r)) for r in base_pool if r in self.agents]
        if is_complex:
            for r in extra_pool:
                if r in self.agents and r not in [v[0] for v in voters] and len(voters) < 5:
                    voters.append((r, self._VOTER_DESC.get(r, r)))
        if not voters:
            # 无可用选民 → 保守放行 T1（维持原行为），不卡死
            decision = {"allow_t0": True, "allow_t1": True, "allow_t2": False,
                        "mode": "no_voters_fallback", "reason": "无可用选民，保守放行 T1"}
            logger.warning(f"[LangGraph:{task_id}] research_vote: 无可用选民，回退放行 T1")
            return {**state, "research_decision": decision, "current_step": "research_vote_done"}

        majority = len(voters) // 2 + 1
        panel_desc = f"{len(voters)}人panel（{'复杂任务' if is_complex else '普通任务'}，过半需{majority}票）"

        # v8.4.6: 投票上下文——注入共享黑板 + problem_type，让选民走 call_llm 时
        # 能读到 WorkingMemory 黑板 + Lessons 跨任务经验 + 自身 AgentProfile
        # （原 _call_llm_once 裸调绕过全部记忆注入）。
        voter_context = {
            "problem_type": problem_type,
            "template": template,
            "working_memory": self._get_working_memory(task_id),
        }

        # ---- Round 1：讨论（并行，各自给立场+理由）----
        round1_thunks = [self._voter_discuss(r, d, problem_text, problem_type, template, is_complex, voter_context)
                         for r, d in voters]
        round1_results = await asyncio.gather(*round1_thunks, return_exceptions=True)
        round1 = []
        for (role, desc), res in zip(voters, round1_results):
            if isinstance(res, Exception) or not isinstance(res, dict):
                round1.append({"role": role, "stance_t1": "unknown", "stance_t2": "unknown",
                               "reason": f"讨论失败: {str(res)[:80] if isinstance(res, Exception) else '空'}"})
            else:
                round1.append({"role": role, **res})
        round1_brief = "\n".join(
            f"- {r['role']}: T1={r.get('stance_t1','?')} T2={r.get('stance_t2','?')}（{r.get('reason','')[:80]}）"
            for r in round1
        )

        # ---- Round 2：投票（并行，看到 round1 后正式投票）----
        round2_thunks = [self._voter_vote(r, d, problem_text, problem_type, template, is_complex, round1_brief, voter_context)
                        for r, d in voters]
        round2_results = await asyncio.gather(*round2_thunks, return_exceptions=True)
        votes_t1, votes_t2 = 0, 0
        voter_records = []
        for (role, desc), res in zip(voters, round2_results):
            rec = {"role": role}
            if isinstance(res, Exception) or not isinstance(res, dict):
                rec.update({"vote_t1": "error", "vote_t2": "error", "reason": str(res)[:80] if isinstance(res, Exception) else "空"})
            else:
                v1 = str(res.get("vote_t1", "no")).strip().lower() in ("yes", "true", "1", "是", "y")
                v2 = str(res.get("vote_t2", "no")).strip().lower() in ("yes", "true", "1", "是", "y")
                rec.update({"vote_t1": "yes" if v1 else "no", "vote_t2": "yes" if v2 else "no",
                            "reason": str(res.get("reason", ""))[:120]})
                if v1:
                    votes_t1 += 1
                if v2:
                    votes_t2 += 1
            voter_records.append(rec)

        allow_t1 = votes_t1 >= majority
        allow_t2 = votes_t2 >= majority and is_complex  # T2 仅复杂任务且过半

        decision = {
            "allow_t0": True,  # T0 永远放行
            "allow_t1": allow_t1,
            "allow_t2": allow_t2,
            "mode": "vote",
            "panel": panel_desc,
            "is_complex": is_complex,
            "majority": majority,
            "tally": {"t1": f"{votes_t1}/{len(voters)}", "t2": f"{votes_t2}/{len(voters)}"},
            "voters": voter_records,
            "round1": round1,
        }
        t1_verdict = "✅放行" if allow_t1 else "❌否决"
        t2_verdict = "✅放行" if allow_t2 else "❌否决"
        logger.info(
            f"[LangGraph:{task_id}] research_vote: {panel_desc} | "
            f"T1={votes_t1}/{len(voters)}({t1_verdict}) T2={votes_t2}/{len(voters)}({t2_verdict})"
        )
        self._post_chat(task_id, "coordinator",
            f"研究决策投票完成（{panel_desc}）：论文检索 T1={votes_t1}/{len(voters)}{t1_verdict}，"
            f"代码检索 T2={votes_t2}/{len(voters)}{t2_verdict}")
        bus.emit_agent_complete(task_id, "research_vote", "research_vote",
            f"T1={votes_t1}/{len(voters)}({t1_verdict}) T2={votes_t2}/{len(voters)}({t2_verdict})")
        return {**state, "research_decision": decision, "current_step": "research_vote_done"}

    async def _voter_discuss(self, role: str, desc: str, problem_text: str,
                             problem_type: str, template: str, is_complex: bool,
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Round 1：选民给出初步立场+理由。"""
        agent = self._get_voter_agent(role)
        if not agent:
            return {"stance_t1": "unknown", "stance_t2": "unknown", "reason": f"agent {role} 不可用"}
        prompt = (
            f"你是数学建模多Agent系统中的【{role}】，职责：{desc}。\n"
            f"当前任务：\n- 问题：{problem_text[:500]}\n- 问题类型：{problem_type}\n"
            f"- 论文模板：{template}\n- 是否复杂任务：{'是' if is_complex else '否'}\n\n"
            f"请从你的角色视角判断：本任务是否需要 (a) 联网检索学术论文 T1（arXiv）？"
            f"(b) 联网检索代码/实现 T2（GitHub/CSDN，仅复杂任务有意义）？\n"
            f"给出你的初步立场和1-2句理由。严格输出JSON："
            f'{{"stance_t1": "yes|no", "stance_t2": "yes|no", "reason": "你的理由"}}'
        )
        try:
            # v8.4.6: 走 call_llm（带 context）→ 接入 AgentProfile + Lessons + 共享黑板记忆。
            # 原 _call_llm_once 裸调绕过全部记忆注入，选民完全"失忆"。
            resp = await agent.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                context=context,
            )
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            data = self._extract_json_obj(content)
            return {"stance_t1": data.get("stance_t1", "unknown"),
                    "stance_t2": data.get("stance_t2", "unknown"),
                    "reason": str(data.get("reason", ""))}
        except Exception as e:
            return {"stance_t1": "unknown", "stance_t2": "unknown", "reason": f"LLM 调用失败: {str(e)[:80]}"}

    async def _voter_vote(self, role: str, desc: str, problem_text: str,
                          problem_type: str, template: str, is_complex: bool,
                          round1_brief: str,
                          context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Round 2：看到 round1 后正式投票（可参考或反对其他 Agent 观点）。"""
        agent = self._get_voter_agent(role)
        if not agent:
            return {"vote_t1": "no", "vote_t2": "no", "reason": f"agent {role} 不可用"}
        prompt = (
            f"你是数学建模多Agent系统中的【{role}】，职责：{desc}。\n"
            f"当前任务：\n- 问题：{problem_text[:400]}\n- 问题类型：{problem_type} | "
            f"模板：{template} | 复杂任务：{'是' if is_complex else '否'}\n\n"
            f"其他Agent的初步讨论：\n{round1_brief}\n\n"
            f"现在请正式投票（可参考也可反对其他Agent的观点）：\n"
            f"T1=是否联网检索学术论文(arXiv)？ T2=是否联网检索代码/实现(GitHub/CSDN)？"
            f"（T2仅复杂任务有意义）\n严格输出JSON："
            f'{{"vote_t1": "yes|no", "vote_t2": "yes|no", "reason": "1句理由"}}'
        )
        try:
            # v8.4.6: 走 call_llm（带 context）→ 接入记忆（AgentProfile + Lessons + 黑板）。
            resp = await agent.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                context=context,
            )
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            return self._extract_json_obj(content)
        except Exception as e:
            return {"vote_t1": "no", "vote_t2": "no", "reason": f"LLM 调用失败: {str(e)[:80]}"}

    def _get_voter_agent(self, role: str):
        """获取选民对应的 agent 实例（用其 _call_llm_once 调 LLM）。coordinator 无独立 agent 时借用 analyzer。"""
        if role == "coordinator":
            return self.agents.get("coordinator") or self.agents.get("analyzer_agent")
        return self.agents.get(role)

    @staticmethod
    def _extract_json_obj(text: str) -> Dict[str, Any]:
        """从 LLM 输出中提取首个 JSON 对象（容忍前后文案 + markdown 代码块）。"""
        if not text:
            return {}
        import json as _json
        s = text.strip()
        # 去 markdown 代码块
        if s.startswith("```"):
            s = s.split("```", 2)
            s = s[1] if len(s) > 1 else text
            if s.startswith("json"):
                s = s[4:]
        # 找第一个 {...}
        start = s.find("{")
        if start < 0:
            return {}
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return _json.loads(s[start:i + 1])
                    except Exception:
                        return {}
        return {}

    # ------------------------------------------------------------------
    # HITL: 用户输入检查
    # ------------------------------------------------------------------
    async def _check_user_input(self, state: TaskState) -> TaskState:
        """每个节点完成后调用 — 检查用户输入并注入 context"""
        task_id = state["task_id"]
        room = get_chat_room(task_id)
        if not room:
            return state

        last_check = state.get("last_input_check", 0)
        user_msgs = room.get_user_messages_since(since=last_check)

        if not user_msgs:
            return state

        # 转换为 dict 格式
        new_msgs = [{"sender": m.sender, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in user_msgs]

        # 记录到 state
        all_msgs = state.get("user_messages", [])
        all_msgs.extend(new_msgs)

        # 通知用户已收到
        room.post("coordinator", f"📝 已收到 {len(new_msgs)} 条用户反馈，正在调整...", "broadcast")

        return {
            **state,
            "user_messages": all_msgs,
            "last_input_check": time.time(),
        }

    # ------------------------------------------------------------------
    # 条件路由（改造后）
    # ------------------------------------------------------------------
    def _route_after_research_or_data(self, state: TaskState) -> str:
        """research/data 完成后决定下一站。"""
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent = self._select_modeling_agent(template, workflow_type)
        if not modeling_agent:
            logger.info(f"[LangGraph] 跳过 modeler/solver（template={template}, workflow={workflow_type}）→ writer")
            return "writer"
        # 映射到 graph 节点名称
        if modeling_agent == "modeler_agent":
            return "modeler"
        if modeling_agent == "algorithm_engineer_agent":
            return "algorithm_engineer"
        if modeling_agent == "financial_analyst_agent":
            return "financial_analyst"
        return "writer"

    def _route_after_analyzer(self, state: TaskState) -> str:
        """analyzer 之后按 problem_type + 数据情况条件路由到 data / research / 建模。"""
        problem_type = (self._resolve_results(state).get("analyzer_agent", {}) or {}).get("problem_type", "")
        has_data = bool(state.get("files"))

        skip_data = self._should_skip_data(problem_type, has_data)
        skip_research = self._should_skip_research(problem_type, state.get("workflow_type", "standard"))

        # 都跳过 → 直接到建模 Agent
        if skip_data and skip_research:
            template = state.get("paper_template", "math_modeling")
            workflow_type = state.get("workflow_type", "standard")
            modeling_agent = self._select_modeling_agent(template, workflow_type)
            if not modeling_agent:
                logger.info(f"[LangGraph] 跳过 data、research 和建模（template={template}）→ writer")
                return "writer"
            if modeling_agent == "modeler_agent":
                return "modeler"
            if modeling_agent == "algorithm_engineer_agent":
                return "algorithm_engineer"
            if modeling_agent == "financial_analyst_agent":
                return "financial_analyst"
            return "writer"

        # 只跳过 data → research
        if skip_data:
            logger.info("[LangGraph] 跳过 data → research")
            return "research"
        # 只跳过 research → data → 建模
        if skip_research:
            logger.info("[LangGraph] 跳过 research → data")
            return "data"
        # 正常顺序
        return "data"

    def _route_after_data(self, state: TaskState) -> str:
        """data 之后决定是否走 research。"""
        problem_type = (self._resolve_results(state).get("analyzer_agent", {}) or {}).get("problem_type", "")
        if self._should_skip_research(problem_type, state.get("workflow_type", "standard")):
            template = state.get("paper_template", "math_modeling")
            workflow_type = state.get("workflow_type", "standard")
            modeling_agent = self._select_modeling_agent(template, workflow_type)
            if not modeling_agent:
                return "writer"
            if modeling_agent == "modeler_agent":
                return "modeler"
            if modeling_agent == "algorithm_engineer_agent":
                return "algorithm_engineer"
            if modeling_agent == "financial_analyst_agent":
                return "financial_analyst"
            return "writer"
        return "research"

    def _route_after_research(self, state: TaskState) -> str:
        """research 后决定是否进入讨论。"""
        workflow = state.get("workflow_type", "standard")
        # deep_research 和 research_paper 模式进入讨论
        if workflow in ("deep_research", "research_paper"):
            return "discuss"
        # 其他模式直接选择建模 Agent
        template = state.get("paper_template", "math_modeling")
        modeling_agent = self._select_modeling_agent(template, workflow)
        if not modeling_agent:
            return "writer"
        if modeling_agent == "modeler_agent":
            return "modeler"
        if modeling_agent == "algorithm_engineer_agent":
            return "algorithm_engineer"
        if modeling_agent == "financial_analyst_agent":
            return "financial_analyst"
        return "writer"

    def _route_after_discuss_approach(self, state: TaskState) -> str:
        """团队讨论后决定下一步：建模求解 or 直接写作（调研/综述类跳过建模）。"""
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent = self._select_modeling_agent(template, workflow_type)
        if not modeling_agent:
            logger.info(f"[LangGraph] 讨论后跳过建模（template={template}, workflow={workflow_type}）→ writer")
            return "writer"
        if modeling_agent == "modeler_agent":
            return "modeler"
        if modeling_agent == "algorithm_engineer_agent":
            return "algorithm_engineer"
        if modeling_agent == "financial_analyst_agent":
            return "financial_analyst"
        return "writer"

    def _route_to_experiment_or_solver(self, state: TaskState) -> str:
        """CCF-A 模板且开启实验设计时，先走 experiment 节点。"""
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}
        if self.cfg.enable_experiment_design and template in ccf_a:
            logger.info(f"[LangGraph] template={template} 启用实验执行 → experiment")
            return "experiment"
        return "iterative_solver"

    def _route_after_experiment(self, state: TaskState) -> str:
        """实验后路由：迭代优化或进入求解器。"""
        step = state.get("current_step", "")
        if step == "experiment_iterating":
            return "experiment"  # 回到实验节点继续迭代
        return "iterative_solver"

    def _route_to_sandbox_or_writer(self, state: TaskState) -> str:
        """v8.2: iterative_solver 后决定是否进入防沙箱死亡螺旋流程。

        所有经过 iterative_solver 的模板都接入 AST 安全壳 + 沙箱错误统计：
        - 所有模板: ast_audit → sandbox_execution → figure（安全壳保护）
        - CCF-A 模板: 额外走 coder_agent（组件化注入）+ reviewer_reflection（越狱熔断）

        设计意图：AST 安全壳和错误统计是通用保护，应该覆盖所有代码执行场景；
        组件化注入和越狱熔断是 CCF-A 专用的高级机制。
        """
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}

        # 初始化执行模式（所有模板都需要）
        if not state.get("execution_mode"):
            state["execution_mode"] = "restricted"
        if not state.get("circuit_breaker_threshold"):
            state["circuit_breaker_threshold"] = 3

        # CCF-A 模板：完整流程（coder_agent → ast_audit → sandbox → reviewer）
        if template in ccf_a:
            return "coder_agent"

        # 非 CCF-A 模板：简化流程（ast_audit → sandbox → figure）
        # 跳过 coder_agent（组件化注入）和 reviewer_reflection（越狱熔断）
        return "ast_audit"

    def _route_after_solver(self, state: TaskState) -> str:
        """统一路由：iterative_solver 完成后决定下一步。

        合并原 _route_solver（重试/升级/中止）和 _route_to_sandbox_or_writer（安全壳流程）。

        决策逻辑：
        1. 检查求解结果：成功 → 进入安全壳流程；失败 → 重试/升级/中止
        2. 安全壳流程：根据模板类型选择 CCF-A 或非 CCF-A 路径
        """
        attempts = state.get("solver_attempts", [])
        escalation = state.get("escalation_count", 0)

        # 检查是否有求解结果
        if not attempts:
            return "retry"

        last = attempts[-1]
        if last.get("execution_success"):
            # 求解成功 → 进入安全壳流程
            return self._route_to_sandbox_or_writer(state)

        # 求解失败 → 检查是否达到重试上限
        if len(attempts) >= self.cfg.max_solver_iterations:
            if escalation >= self.cfg.max_solver_escalations:
                return "abort"
            return "escalate"

        return "retry"

    # ------------------------------------------------------------------
    # v8.2: 防沙箱死亡螺旋 — 三机制节点
    # ------------------------------------------------------------------

    async def _node_coder_agent(self, state: TaskState) -> TaskState:
        """模块 1: Coder Agent 的"组件化注入"改造。

        核心逻辑：
        - 读取 execution_mode。如果是 "restricted"，Coder Agent 只生成 nn.Module
          和 Loss 组件代码，并调用 inject_components() 将其注入到系统预置的
          Base Template 中；
        - 如果是 "jailbreak"，允许生成完整代码。
        - 返回更新后的 experiment_code。

        设计意图：
        在死亡螺旋早期阶段，限制 Coder 的自由度，强制使用预验证的组件模板，
        降低代码出错概率。当指标连续未提升时，升级为 jailbreak 允许自由探索。
        """
        task_id = state["task_id"]
        execution_mode = state.get("execution_mode", "restricted")
        results = self._resolve_results(state)
        modeler_output = results.get("modeler_agent", {})

        self._update_progress(task_id, state["problem_text"], 52, f"代码生成中（{execution_mode}模式）")

        agent = self.agents.get("solver_agent")
        if not agent:
            return {**state, "current_step": "coder_agent_missing"}

        # 构造组件化注入的上下文
        component_context = ""
        if execution_mode == "restricted":
            # 受限模式：注入预置的 Base Template 组件
            component_context = (
                "\n\n## 组件化注入模式（restricted）\n"
                "你只能生成以下组件代码，系统会自动注入到 Base Template 中：\n"
                "1. nn.Module 子类（网络架构组件）\n"
                "2. Loss 函数组件\n"
                "3. 训练循环组件\n\n"
                "禁止生成：完整的训练脚本、数据加载代码、环境配置代码。\n"
                "请只输出组件代码，用 # COMPONENT: <type> 标记类型。"
            )

        # 调用 solver_agent 生成代码
        try:
            output = await agent.execute(
                task_input={
                    "action": "solve",
                    "problem_text": state["problem_text"] + component_context,
                    "execution_mode": execution_mode,
                },
                context={
                    **self._agent_context(state),
                    "results": results,
                    "execution_mode": execution_mode,
                },
            )
        except Exception as exc:
            logger.error(f"[LangGraph:{task_id}] coder_agent failed: {exc}")
            return {**state, "current_step": "coder_agent_failed"}

        # 组件化注入：如果是 restricted 模式，将组件代码注入到 Base Template
        if execution_mode == "restricted":
            code_files = output.get("code_files", [])
            if code_files:
                injected_code = self._inject_components_to_template(
                    code_files[0].get("code", ""),
                    state.get("paper_template", "math_modeling"),
                )
                output["code_files"] = [{
                    **code_files[0],
                    "code": injected_code,
                    "description": f"组件化注入后（{len(code_files)} 个组件）",
                }]

        ref_update = self._set_result(state, "coder_agent", output)
        self._post_chat(task_id, "coder_agent", f"代码生成完成（{execution_mode}模式）")

        return {
            **state,
            "results": {**state.get("results", {}), **ref_update},
            "current_step": "coder_agent_done",
        }

    @staticmethod
    def _inject_components_to_template(component_code: str, template: str) -> str:
        """将组件代码注入到系统预置的 Base Template 中。

        受限模式下，Coder 只生成 nn.Module / Loss 组件，
        此方法将其组装到完整的训练脚本模板中。
        """
        # 根据模板类型选择 Base Template
        base_templates = {
            "math_modeling": _BASE_TEMPLATE_MATH_MODELING,
            "neurips_2024": _BASE_TEMPLATE_CCF_A,
            "ieee_conference": _BASE_TEMPLATE_CCF_A,
            "acm_sigconf": _BASE_TEMPLATE_CCF_A,
            "springer_lncs": _BASE_TEMPLATE_CCF_A,
        }
        base = base_templates.get(template, _BASE_TEMPLATE_MATH_MODELING)

        # 提取组件标记
        components = {}
        for line in component_code.split("\n"):
            if line.strip().startswith("# COMPONENT:"):
                comp_type = line.split(":", 1)[1].strip()
                components[comp_type] = True

        # 注入组件到 Base Template
        injected = base.replace("# {{COMPONENTS}}", component_code)
        return injected

    async def _node_ast_audit(self, state: TaskState) -> TaskState:
        """模块 2: AST 审计 Agent 的"双重职责"升级（所有模板通用）。

        核心逻辑：
        A. (原有功能) 检查代码是否包含伪造的硬编码结果（防造假）
        B. (新增功能) 调用 SafetyShellTransformer 对 experiment_code 进行 AST 遍历，
           强制在最外层包裹 try-except，并在 torch 调用后注入 cuda.empty_cache()（防 OOM 崩溃）
        C. 如果审计通过且打补丁成功，返回 {"ast_audit_passed": True, "experiment_code": patched_code}

        适配所有模板：
        - CCF-A: 代码来自 coder_agent（code_files 直接在顶层）
        - 非 CCF-A: 代码来自 solver_agent（code_files 在 sub_problem_solutions 内）
        """
        task_id = state["task_id"]
        results = self._resolve_results(state)
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}

        # 根据模板类型选择代码来源
        if template in ccf_a:
            # CCF-A: 代码来自 coder_agent
            source_output = results.get("coder_agent", {})
            source_key = "coder_agent"
        else:
            # 非 CCF-A: 代码来自 solver_agent
            source_output = results.get("solver_agent", {})
            source_key = "solver_agent"

        # 获取待审计的代码（兼容两种数据结构）
        code_files = []
        if template in ccf_a:
            # CCF-A: code_files 在顶层
            code_files = source_output.get("code_files", []) if isinstance(source_output, dict) else []
        else:
            # 非 CCF-A: code_files 在 sub_problem_solutions 内
            solutions = source_output.get("sub_problem_solutions", []) if isinstance(source_output, dict) else []
            for sol in solutions:
                sol_code_files = sol.get("code_files", [])
                if sol_code_files:
                    code_files = sol_code_files
                    break

        if not code_files:
            logger.info(f"[LangGraph:{task_id}] ast_audit: 无代码文件，跳过审计")
            return {**state, "ast_audit_passed": False, "current_step": "ast_audit_skipped"}

        raw_code = code_files[0].get("code", "") if code_files else ""
        if not raw_code:
            return {**state, "ast_audit_passed": False, "current_step": "ast_audit_skipped"}

        self._update_progress(task_id, state["problem_text"], 54, "AST 审计中（防造假 + 防崩溃）")

        try:
            from ..core.code_audit import audit_and_patch
            audit_result, patched_code = audit_and_patch(raw_code, task_type="training")
        except ImportError:
            # fallback: 只做防造假审计，不做安全壳注入
            from ..core.code_audit import audit_code
            audit_result = audit_code(raw_code, task_type="training")
            patched_code = raw_code
            logger.warning(f"[LangGraph:{task_id}] safety_shell 不可用，仅执行防造假审计")
        except Exception as e:
            logger.error(f"[LangGraph:{task_id}] AST 审计异常: {e}")
            return {**state, "ast_audit_passed": False, "current_step": "ast_audit_failed"}

        # 更新代码文件为打补丁后的版本
        patched_files = [{
            **code_files[0],
            "code": patched_code,
            "description": f"AST 安全壳打补丁后（score={audit_result.score}）",
        }]

        # 将审计结果合并到对应的 Agent 输出
        if template in ccf_a:
            # CCF-A: 更新 coder_agent 输出
            updated_output = {
                **source_output,
                "code_files": patched_files,
                "ast_audit": {
                    "passed": audit_result.passed,
                    "score": audit_result.score,
                    "issues": [{"line": i.line, "severity": i.severity, "category": i.category,
                                "message": i.message, "suggestion": i.suggestion}
                               for i in audit_result.issues],
                    "summary": audit_result.summary,
                    "safety_shell_injected": patched_code != raw_code,
                },
            }
            ref_update = self._set_result(state, "coder_agent", updated_output)
        else:
            # 非 CCF-A: 更新 solver_agent 输出中的 code_files
            updated_solutions = list(source_output.get("sub_problem_solutions", []))
            for i, sol in enumerate(updated_solutions):
                if sol.get("code_files"):
                    updated_solutions[i] = {**sol, "code_files": patched_files}
                    break
            updated_output = {**source_output, "sub_problem_solutions": updated_solutions}
            updated_output["ast_audit"] = {
                "passed": audit_result.passed,
                "score": audit_result.score,
                "issues": [{"line": i.line, "severity": i.severity, "category": i.category,
                            "message": i.message, "suggestion": i.suggestion}
                           for i in audit_result.issues],
                "summary": audit_result.summary,
                "safety_shell_injected": patched_code != raw_code,
            }
            ref_update = self._set_result(state, "solver_agent", updated_output)

        # 通知审计结果
        if audit_result.passed:
            self._post_chat(
                task_id, "ast_audit_agent",
                f"AST 审计通过（score={audit_result.score}），安全壳已注入"
            )
        else:
            self._post_chat(
                task_id, "ast_audit_agent",
                f"AST 审计发现问题（score={audit_result.score}）：{audit_result.summary}"
            )

        return {
            **state,
            "results": {**state.get("results", {}), **ref_update},
            "ast_audit_passed": audit_result.passed,
            "current_step": "ast_audit_done",
        }

    async def _node_sandbox_execution(self, state: TaskState) -> TaskState:
        """模块 3a: 沙箱执行节点 — 模拟沙箱运行并统计错误（所有模板通用）。

        核心逻辑：
        - 模拟沙箱运行。如果报错，error_count + 1
        - 如果成功，提取指标并重置 error_count = 0
        - 记录指标到 metrics_trend 用于后续趋势判断

        适配所有模板：
        - CCF-A: 代码来自 ast_audit 后的 coder_agent
        - 非 CCF-A: 代码来自 ast_audit 后的 solver_agent
        """
        task_id = state["task_id"]
        error_count = state.get("error_count", 0)
        metrics_trend = list(state.get("metrics_trend", []))
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}

        # 根据模板类型选择代码来源
        results = self._resolve_results(state)
        if template in ccf_a:
            source_output = results.get("coder_agent", {})
        else:
            source_output = results.get("solver_agent", {})

        # 获取待执行的代码（兼容两种数据结构）
        code_files = []
        if template in ccf_a:
            code_files = source_output.get("code_files", []) if isinstance(source_output, dict) else []
        else:
            solutions = source_output.get("sub_problem_solutions", []) if isinstance(source_output, dict) else []
            for sol in solutions:
                sol_code_files = sol.get("code_files", [])
                if sol_code_files:
                    code_files = sol_code_files
                    break

        if not code_files:
            logger.info(f"[LangGraph:{task_id}] sandbox: 无代码文件，跳过执行")
            return {**state, "current_step": "sandbox_skipped"}

        self._update_progress(task_id, state["problem_text"], 56, "沙箱执行中")

        # 模拟沙箱执行（实际项目中调用 sandbox.py）
        try:
            from ..core.sandbox import execute_code
            code = code_files[0].get("code", "")
            sandbox_result = execute_code(code, timeout_sec=300)

            if sandbox_result.success:
                # 执行成功：重置错误计数，提取指标
                error_count = 0
                # 提取数值指标（从 stdout 中解析）
                extracted_metric = self._extract_metric_from_output(sandbox_result.stdout)
                if extracted_metric is not None:
                    metrics_trend.append(extracted_metric)
                    # 保留最近 5 次指标
                    metrics_trend = metrics_trend[-5:]

                # v8.3: 更新 Bandit — 执行成功
                self._bandit.update_from_result(
                    action_id=state.get("bandit_action_id", 0),
                    context_list=state.get("bandit_context", [0.0] * 7),
                    success=True,
                    metric_improved=extracted_metric is not None and (
                        len(metrics_trend) < 2 or metrics_trend[-1] > metrics_trend[-2]
                    ),
                    current_metric=extracted_metric,
                )

                self._post_chat(task_id, "sandbox", "沙箱执行成功")
                current_step = "sandbox_success"
            else:
                # 执行失败：错误计数 +1
                error_count += 1

                # v8.3: 更新 Bandit — 执行失败
                self._bandit.update_from_result(
                    action_id=state.get("bandit_action_id", 0),
                    context_list=state.get("bandit_context", [0.0] * 7),
                    success=False,
                    metric_improved=False,
                )

                self._post_chat(
                    task_id, "sandbox",
                    f"沙箱执行失败（连续第 {error_count} 次）：{sandbox_result.stderr[:200]}"
                )
                current_step = "sandbox_failed"

        except ImportError:
            # sandbox 模块不可用时的降级处理
            logger.warning(f"[LangGraph:{task_id}] sandbox 模块不可用，模拟执行成功")
            error_count = 0
            current_step = "sandbox_success"
        except Exception as e:
            error_count += 1
            self._post_chat(task_id, "sandbox", f"沙箱执行异常（连续第 {error_count} 次）：{str(e)[:200]}")
            current_step = "sandbox_failed"

        return {
            **state,
            "error_count": error_count,
            "metrics_trend": metrics_trend,
            "current_step": current_step,
        }

    async def _node_reviewer_reflection(self, state: TaskState) -> TaskState:
        """模块 3b: Reviewer/Reflection — Contextual Bandit 自适应决策。

        v8.3: 使用 LinUCB Contextual Bandit 替代固定规则熔断逻辑。
        Bandit 根据上下文（错误次数、模式、尝试次数、指标趋势）自适应选择：
        - continue: 继续当前模式重试
        - degrade: 降级为 restricted 模式
        - upgrade: 升级为 jailbreak 模式
        - abort: 放弃当前问题

        保留一个安全网：连续错误 >= 5 时强制降级（防止 Bandit 探索阶段的灾难性决策）。
        """
        task_id = state["task_id"]
        error_count = state.get("error_count", 0)
        execution_mode = state.get("execution_mode", "restricted")
        metrics_trend = list(state.get("metrics_trend", []))
        threshold = state.get("circuit_breaker_threshold", 3)
        attempt = state.get("experiment_iterations", 1)

        self._update_progress(task_id, state["problem_text"], 58, "Reviewer 反思中")

        decision = "continue"
        reason = ""
        bandit_result = None

        # ===== 安全网：连续错误过多时强制降级（防止 Bandit 探索期灾难）=====
        if error_count >= 5:
            decision = "degrade"
            reason = (
                f"安全网触发：连续 {error_count} 次错误（>=5），"
                f"强制降级为 restricted 模式"
            )
            execution_mode = "restricted"
            error_count = 0
            self._post_chat(task_id, "reviewer", f"🛡️ {reason}")

            # 记录安全网触发（reward 为负，让 Bandit 学习避免这种情况）
            prev_context = state.get("bandit_context", [0.0] * 7)
            prev_action = state.get("bandit_action_id", 0)
            if prev_context and len(prev_context) == 7:
                self._bandit.update_from_result(
                    action_id=prev_action,
                    context_list=prev_context,
                    success=False,
                    metric_improved=False,
                )

        # ===== Contextual Bandit 决策 =====
        else:
            bandit_result = self._bandit.decide(
                error_count=error_count,
                execution_mode=execution_mode,
                attempt=attempt,
                metrics_trend=metrics_trend,
            )

            decision = bandit_result["action"]
            reason = bandit_result["reason"]

            # 应用决策
            if decision == "degrade":
                execution_mode = "restricted"
                error_count = 0
            elif decision == "upgrade":
                execution_mode = "jailbreak"
                threshold = 1
            elif decision == "abort":
                # abort: 保持当前状态，让上层路由决定
                pass
            # "continue": 不修改任何状态

            self._post_chat(task_id, "reviewer", f"🤖 {reason}")

        return {
            **state,
            "error_count": error_count,
            "execution_mode": execution_mode,
            "metrics_trend": metrics_trend,
            "circuit_breaker_threshold": threshold,
            "bandit_action_id": bandit_result.get("action_id", 0) if bandit_result else 0,
            "bandit_context": bandit_result.get("context", [0.0] * 7) if bandit_result else [0.0] * 7,
            "current_step": f"reviewer_reflection_{decision}",
        }

    def _extract_metric_from_output(self, stdout: str) -> Optional[float]:
        """从沙箱执行输出中提取数值指标（用于趋势判断）。"""
        import re
        # 尝试匹配常见的指标输出格式
        patterns = [
            re.compile(r"(?:accuracy|acc|f1|loss|metric)\s*[:=]\s*(\d+\.?\d*)", re.IGNORECASE),
            re.compile(r"\{[^}]*\"(?:accuracy|loss|f1)\"\s*:\s*(\d+\.?\d*)"),
        ]
        for pattern in patterns:
            match = pattern.search(stdout)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def _route_after_sandbox(self, state: TaskState) -> str:
        """v8.2: 沙箱执行后路由 — CCF-A 进入越狱熔断，非 CCF-A 直接进入图表。"""
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}

        if template in ccf_a:
            return "reviewer"

        # 非 CCF-A 模板：安全壳 + 错误统计已完成，直接进入图表生成
        return "figure"

    def _route_after_reviewer(self, state: TaskState) -> str:
        """模块 3c: 条件边路由函数 — 根据 Reviewer 决策决定下一步。

        Returns:
            "coder_agent_node": 打回给 Coder 重写
            "figure": 进入图表生成阶段（所有模板都需要图表）
            END: 终止流程
        """
        current_step = state.get("current_step", "")

        # 降级/升级 → 打回给 Coder 重写
        if "degrade" in current_step or "upgrade" in current_step:
            return "coder_agent"

        # 熔断触发（多次降级后仍失败）→ 检查是否超过最大重试
        error_count = state.get("error_count", 0)
        execution_mode = state.get("execution_mode", "restricted")
        if error_count >= 3 and execution_mode == "restricted":
            # 已经在 restricted 模式下还连续失败 → 进入图表生成（带降级标记）
            self._post_chat(
                state["task_id"], "reviewer",
                "⚠️ 已达最大重试次数，进入图表生成阶段（结果可能不完整）"
            )
            return "figure"

        # 正常继续 → 进入图表生成（所有模板都需要图表）
        return "figure"

    # ------------------------------------------------------------------
    # v7.1: 并行分析路由
    # ------------------------------------------------------------------

    def _route_after_analyzer_parallel(self, state: TaskState) -> str:
        """analyzer 后决定是否进入并行分析（data+research+innovation 同时执行）。"""
        problem_type = (self._resolve_results(state).get("analyzer_agent", {}) or {}).get("problem_type", "")
        has_data = bool(state.get("files"))
        skip_data = self._should_skip_data(problem_type, has_data)
        skip_research = self._should_skip_research(problem_type, state.get("workflow_type", "standard"))

        # 都跳过 → 直接到建模
        if skip_data and skip_research:
            return "skip_to_modeling"

        # 至少有一个需要执行 → 进入并行分析
        return "parallel"

    def _route_after_parallel_analysis(self, state: TaskState) -> str:
        """并行分析完成后，选择建模 Agent。"""
        workflow = state.get("workflow_type", "standard")
        if workflow in ("deep_research", "research_paper"):
            return "discuss"
        template = state.get("paper_template", "math_modeling")
        modeling_agent = self._select_modeling_agent(template, workflow)
        if not modeling_agent:
            return "writer"
        if modeling_agent == "modeler_agent":
            return "modeler"
        if modeling_agent == "algorithm_engineer_agent":
            return "algorithm_engineer"
        if modeling_agent == "financial_analyst_agent":
            return "financial_analyst"
        return "writer"

    async def _node_parallel_analysis(self, state: TaskState) -> TaskState:
        """v7.1: 并行执行 data_agent + research_agent + innovation_agent。

        参考：LangGraph Send API 的 fan-out/fan-in 模式。
        在同一个节点内用 asyncio.gather 并发执行三个 Agent，
        然后合并结果到 state。
        """
        import asyncio

        state = await self._check_user_input(state)
        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_phase_change(task_id, "parallel_analysis", "并行分析阶段：data + research + innovation 同时执行")

        problem_type = (self._resolve_results(state).get("analyzer_agent", {}) or {}).get("problem_type", "")
        has_data = bool(state.get("files"))
        skip_data = self._should_skip_data(problem_type, has_data)
        skip_research = self._should_skip_research(problem_type, state.get("workflow_type", "standard"))

        # 构建并行任务列表
        tasks = {}
        task_coros = {}

        if not skip_data:
            tasks["data"] = self._node_data(state)
        if not skip_research:
            tasks["research"] = self._node_research(state)
            tasks["innovation"] = self._node_innovation(state)

        if not tasks:
            # 全部跳过
            return state

        logger.info(f"[LangGraph:{task_id}] parallel_analysis: running {list(tasks.keys())} concurrently")
        self._update_progress(task_id, state["problem_text"], 30, "并行分析中（data+research+innovation）")

        # 并发执行
        results = {}
        coro_list = list(tasks.values())
        keys = list(tasks.keys())
        done_results = await asyncio.gather(*coro_list, return_exceptions=True)

        for key, result in zip(keys, done_results):
            if isinstance(result, Exception):
                logger.warning(f"[LangGraph:{task_id}] parallel_analysis.{key} failed: {result}")
                bus.emit_error(task_id, f"{key}_agent", str(result))
            else:
                results[key] = result

        # 合并结果到 state
        merged_results = {**state.get("results", {})}
        merged_step = "parallel_analysis_done"

        for key, result_state in results.items():
            if isinstance(result_state, dict):
                # 每个子节点返回的是完整的 state dict，提取 results 部分
                sub_results = result_state.get("results", {})
                merged_results.update(sub_results)
                # 更新 sub_problems（如果 data 或 research 产生了新的）
                if "sub_problems" in result_state and result_state["sub_problems"]:
                    state["sub_problems"] = result_state["sub_problems"]

        bus.emit_agent_complete(task_id, "parallel_analysis", "parallel_analysis",
                               f"完成 {len(results)} 个并行任务")

        return {**state, "results": merged_results, "current_step": merged_step}

    def _get_config(self):
        """获取全局配置。"""
        from ..config import get_settings
        return get_settings()

    # ------------------------------------------------------------------
    # 需求校验节点（pre 阶段）— 修复"需求分解后不验完整性"缺陷
    # ------------------------------------------------------------------
    # 校验 requirement_decomposition 产出的 requirement_plan：结构完整性、
    # 子任务 schema、依赖图 DAG 合法性、Agent 名称合法性、关键问题→子任务
    # 覆盖度、token 预算，并辅以一次轻量 LLM 语义覆盖度校验。校验失败可回退
    # 到 requirement_decomposition 重新分解（带重试上限熔断，避免死循环）。

    # 允许的 Agent 名称集合（self.agents.keys() 的并集 + 已知标准 Agent）
    _KNOWN_AGENT_NAMES = {
        "research_agent", "modeler_agent", "algorithm_engineer_agent",
        "financial_analyst_agent", "solver_agent", "writer_agent",
        "data_agent", "experimentation_agent", "figure_agent",
        "analyzer_agent", "peer_review_agent", "coder_agent",
    }
    # 重新分解次数上限（仿 retry_count 熔断）：attempts<2 回退分解，>=2 强制放行
    _MAX_REDECOMPOSE_ATTEMPTS = 2
    # 关键问题→子任务覆盖度的 Jaccard token 重叠阈值
    _COVERAGE_JACCARD_THRESHOLD = 0.2
    # 需求计划 token 预算上限（防止分解器产出臃肿计划拖垮后续 Agent 上下文）
    _PLAN_TOKEN_BUDGET = 8000

    @staticmethod
    def _check_dependency_dag(
        subtasks: List[Dict[str, Any]], valid_ids: set
    ) -> tuple:
        """校验子任务依赖图为 DAG：(a) 悬空引用、(b) 环检测。

        Args:
            subtasks: 子任务列表。
            valid_ids: 已通过 schema 校验的合法子任务 id 字符串集合。

        Returns:
            (issues, has_cycle) — issues 为校验发现的消息列表，has_cycle 表示是否存在环。
        """
        issues: List[str] = []
        graph: Dict[str, List[str]] = {}
        for st in subtasks:
            if not isinstance(st, dict):
                continue
            sid = st.get("id")
            if sid is None or str(sid).strip() == "":
                continue
            deps = st.get("dependencies", []) or []
            if not isinstance(deps, list):
                deps = []
            graph[str(sid)] = [str(d) for d in deps]
            # (a) 悬空引用：依赖的 id 必须存在于 valid_ids
            for d in deps:
                if str(d) not in valid_ids:
                    issues.append(
                        f"子任务 {sid} 依赖了未定义的子任务 id: {d}（悬空引用）"
                    )

        # (b) 三色标记 DFS 检测环
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in graph}
        has_cycle = False

        def _dfs(node: str) -> None:
            nonlocal has_cycle
            color[node] = GRAY
            for nxt in graph.get(node, []):
                if nxt not in color:
                    # 指向不在图中的节点（已记为悬空引用），跳过
                    continue
                if color[nxt] == GRAY:
                    has_cycle = True
                    issues.append(f"依赖图存在环，涉及子任务: {node} -> {nxt}")
                elif color[nxt] == WHITE:
                    _dfs(nxt)
            color[node] = BLACK

        for nid in list(graph.keys()):
            if color[nid] == WHITE:
                _dfs(nid)
        return issues, has_cycle

    @staticmethod
    def _check_question_coverage(
        key_questions: List[str],
        subtasks: List[Dict[str, Any]],
        threshold: float,
    ) -> List[Dict[str, Any]]:
        """关键问题→子任务覆盖度校验（Jaccard token 重叠）。

        对每个 key_question，若无任何 subtask.description 与之 token 重叠系数 ≥ threshold，
        记一条 coverage_gap（warning 级），这是"完整性"缺陷的核心拦截点。
        """
        gaps: List[Dict[str, Any]] = []

        def _tokens(text: str) -> set:
            # 中英文混合 token 化：英文按 ≥2 字符词、中文按单字
            return set(re.findall(r"[a-zA-Z_]{2,}|[一-鿿]", str(text).lower()))

        sub_desc_tokens: List[set] = []
        for st in subtasks:
            if isinstance(st, dict):
                desc = st.get("description", "")
                if desc:
                    sub_desc_tokens.append(_tokens(desc))

        for q in key_questions:
            q_tokens = _tokens(q)
            if not q_tokens:
                continue
            best = 0.0
            for st_toks in sub_desc_tokens:
                if not st_toks:
                    continue
                inter = len(q_tokens & st_toks)
                union = len(q_tokens | st_toks)
                jacc = inter / union if union else 0.0
                if jacc > best:
                    best = jacc
            if best < threshold:
                gaps.append({
                    "severity": "warning",
                    "category": "coverage_gap",
                    "message": f"关键问题无子任务覆盖（最高重叠 {best:.2f} < {threshold}）: {q[:80]}",
                })
        return gaps

    async def _node_requirement_validation(self, state: TaskState) -> TaskState:
        """需求校验节点（pre 阶段）：校验 requirement_plan 的完整性，拦截残缺/不可调度计划。

        短问题（requirement_plan 为 None，未触发分解）直接放行不阻塞主流程；
        长问题则做结构/schema/DAG/Agent 合法性/覆盖度/token 预算 + 一次轻量 LLM
        语义覆盖度校验，失败可回退重新分解（带重试上限熔断）。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] requirement_validation: 启动需求完整性校验")
        self._update_progress(task_id, state.get("problem_text", ""), 8, "需求完整性校验中")

        plan = state.get("requirement_plan")
        attempts = int(state.get("requirement_validation_attempts", 0) or 0)

        # 1. 短路放行：未触发分解（短问题 <3000 字，见 _node_requirement_decomposition line 1792/1813）
        if not plan:
            logger.info(f"[LangGraph:{task_id}] requirement_validation: 无 requirement_plan，跳过校验")
            return {
                **state,
                "current_step": "requirement_validation_skipped",
                "requirement_validation_passed": True,
                "requirement_validation_attempts": attempts,
            }

        try:
            from ..core.context_compressor import estimate_tokens

            template = state.get("paper_template", "")
            workflow_type = state.get("workflow_type", "")
            issues: List[Dict[str, Any]] = []

            # 2. 结构完整性（确定性，仿 _validate_no_fabrication 风格）
            required_fields = [
                ("research_goal", str),
                ("key_questions", list),
                ("subtasks", list),
                ("methodology_hints", list),
                ("expected_output", str),
                ("data_requirements", list),
                ("template_suggestion", str),
            ]
            if not isinstance(plan, dict):
                issues.append({
                    "severity": "error", "category": "structure",
                    "message": "requirement_plan 不是 dict，结构非法",
                })
            else:
                for fname, ftype in required_fields:
                    val = plan.get(fname)
                    if val is None:
                        issues.append({
                            "severity": "error", "category": "structure",
                            "message": f"requirement_plan 缺失字段: {fname}",
                        })
                    elif not isinstance(val, ftype):
                        issues.append({
                            "severity": "error", "category": "structure",
                            "message": f"字段 {fname} 类型应为 {ftype.__name__}，实为 {type(val).__name__}",
                        })
                    elif isinstance(val, str) and not val.strip():
                        issues.append({
                            "severity": "error", "category": "structure",
                            "message": f"字段 {fname} 为空字符串",
                        })
                    elif isinstance(val, list) and len(val) == 0:
                        issues.append({
                            "severity": "error", "category": "structure",
                            "message": f"字段 {fname} 为空列表（至少 1 项）",
                        })

            subtasks = plan.get("subtasks", []) if isinstance(plan, dict) else []
            subtasks = subtasks if isinstance(subtasks, list) else []

            # 3. 子任务 schema：每个必须有 id、description(非空)、suggested_agent(非空)
            valid_subtask_ids: set = set()
            for idx, st in enumerate(subtasks):
                if not isinstance(st, dict):
                    issues.append({
                        "severity": "error", "category": "subtask_schema",
                        "message": f"subtasks[{idx}] 不是 dict",
                    })
                    continue
                sid = st.get("id")
                desc = st.get("description")
                agent = st.get("suggested_agent")
                if sid is None or str(sid).strip() == "":
                    issues.append({
                        "severity": "error", "category": "subtask_schema",
                        "message": f"subtasks[{idx}] 缺失 id",
                    })
                else:
                    valid_subtask_ids.add(str(sid))
                if not desc or (isinstance(desc, str) and not desc.strip()):
                    issues.append({
                        "severity": "error", "category": "subtask_schema",
                        "message": f"subtasks[{idx}] 缺失 description",
                    })
                if not agent or (isinstance(agent, str) and not agent.strip()):
                    issues.append({
                        "severity": "error", "category": "subtask_schema",
                        "message": f"subtasks[{idx}] 缺失 suggested_agent",
                    })

            # 4. 依赖图 DAG 校验（悬空引用 + 环检测）
            dag_issues, has_cycle = self._check_dependency_dag(subtasks, valid_subtask_ids)
            for msg in dag_issues:
                issues.append({
                    "severity": "error", "category": "dependency_dag",
                    "message": msg,
                })

            # 5. Agent 名称合法性：对照 self.agents.keys() 并集已知集合
            allowed_agents = set(self.agents.keys()) | self._KNOWN_AGENT_NAMES
            for st in subtasks:
                if not isinstance(st, dict):
                    continue
                ag = st.get("suggested_agent")
                if ag and isinstance(ag, str) and ag.strip() and ag not in allowed_agents:
                    issues.append({
                        "severity": "warning", "category": "agent_name",
                        "message": f"子任务 {st.get('id')} 的 suggested_agent 不在已知集合: {ag}",
                    })

            # 6. 关键问题→子任务覆盖度（确定性，Jaccard token 重叠）
            key_questions = plan.get("key_questions", []) if isinstance(plan, dict) else []
            key_questions = key_questions if isinstance(key_questions, list) else []
            coverage_gaps = self._check_question_coverage(
                [str(q) for q in key_questions],
                subtasks,
                self._COVERAGE_JACCARD_THRESHOLD,
            )
            issues.extend(coverage_gaps)

            # 7. Token 预算（复用 context_compressor.estimate_tokens）
            plan_tokens = estimate_tokens(plan)
            if plan_tokens > self._PLAN_TOKEN_BUDGET:
                issues.append({
                    "severity": "warning", "category": "token_budget",
                    "message": f"requirement_plan 体积过大: {plan_tokens} tokens > {self._PLAN_TOKEN_BUDGET}",
                })

            # 8. 问题覆盖度 LLM 校验（轻量单次调用，补足语义级缺口；解析失败降级跳过）
            try:
                problem_text = (state.get("problem_text") or "")[:6000]
                llm_gaps = await self._llm_question_coverage(
                    task_id, problem_text, plan, template, workflow_type
                )
                if llm_gaps:
                    issues.extend(llm_gaps)
            except Exception as llm_exc:
                logger.warning(
                    f"[LangGraph:{task_id}] requirement_validation LLM 覆盖度校验失败，降级跳过: {llm_exc}"
                )

            # 9. 汇总打分（仿 code_audit.audit_code 评分式）
            error_count = sum(1 for i in issues if i.get("severity") == "error")
            warning_count = sum(1 for i in issues if i.get("severity") == "warning")
            passed = error_count == 0
            score = max(0, 100 - error_count * 20 - warning_count * 5)
            new_attempts = attempts + 1

            validation = {
                "passed": passed,
                "score": score,
                "issues": issues,
                "gaps": [g.get("message", "") for g in coverage_gaps],
                "error_count": error_count,
                "warning_count": warning_count,
                "validated_at": datetime.now().isoformat(),
                "attempts": new_attempts,
                "plan_tokens": plan_tokens,
                "has_cycle": has_cycle,
                # 补全指令：注入下一次分解的 context（由路由层回退时消费）
                "remediation_hints": [
                    i.get("message", "") for i in issues if i.get("severity") == "error"
                ],
            }

            # 10. 写回：把 _validation 子字典并入 plan（仿 _fabrication_flags 注入输出 dict 范式）
            base_plan = plan if isinstance(plan, dict) else {"_raw_plan": plan}
            annotated_plan = {**base_plan, "_validation": validation}

            # 持久化校验报告（仿 _node_fact_check line 3151 的 _set_result 范式）
            self._set_result(state, "requirement_validator", validation)

            # 11. 路由语义：passed→done；失败且未达上限→failed 回退；达上限→降级放行
            if passed:
                current_step = "requirement_validation_done"
                rv_passed = True
                notice = (f"✅ 需求完整性校验通过（score={score}，warnings={warning_count}）")
            elif new_attempts >= self._MAX_REDECOMPOSE_ATTEMPTS:
                # 熔断：强制放行并打降级标记，避免阻塞主流程
                current_step = "requirement_validation_degraded"
                rv_passed = True
                notice = (f"⚠️ 需求校验第 {new_attempts} 次仍失败（score={score}，"
                          f"errors={error_count}），已达重试上限，降级放行。"
                          f"缺口: {'; '.join(validation['gaps'][:3]) or '无'}")
            else:
                current_step = "requirement_validation_failed"
                rv_passed = False
                notice = (f"⚠️ 需求完整性校验失败（score={score}，errors={error_count}），"
                          f"将回退重新分解（第 {new_attempts} 次）。"
                          f"问题: {'; '.join(validation['remediation_hints'][:3]) or '无'}")

            self._post_chat(task_id, "requirement_validator", notice)

            # 校验问题写回 state 的 _quality_issues 列表（无则新增）
            quality_issues = list(state.get("_quality_issues") or [])
            for iss in issues:
                quality_issues.append({
                    **iss, "stage": "pre", "node": "requirement_validation",
                })

            logger.info(
                f"[LangGraph:{task_id}] requirement_validation: passed={passed} "
                f"score={score} errors={error_count} warnings={warning_count} "
                f"attempts={new_attempts} step={current_step}"
            )

            return {
                **state,
                "requirement_plan": annotated_plan,
                "current_step": current_step,
                "results": {**state.get("results", {}), "requirement_validator": validation},
                "requirement_validation_passed": rv_passed,
                "requirement_validation_attempts": new_attempts,
                "_quality_issues": quality_issues,
            }
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] requirement_validation 异常: {exc}")
            return state

    async def _llm_question_coverage(
        self,
        task_id: str,
        problem_text: str,
        plan: Dict[str, Any],
        template: str,
        workflow_type: str,
    ) -> List[Dict[str, Any]]:
        """轻量单次 LLM 语义覆盖度校验（仿 _multi_agent_vote/_classify_review_defects 模式）。

        把 problem_text（截断前 6000 字）+ plan 喂给 LLM，要求返回 JSON
        {uncovered:[...], reason:...}，列出 problem_text 中明确要求但 subtasks
        未覆盖的交付物/约束。解析失败则降级返回空列表（不阻塞主流程）。
        """
        agent = self.agents.get("analyzer_agent")
        if not agent or not problem_text:
            return []
        subtasks = plan.get("subtasks", []) if isinstance(plan, dict) else []
        subtask_brief = json.dumps(
            [{"id": st.get("id"), "desc": st.get("description"),
              "agent": st.get("suggested_agent")}
             for st in subtasks if isinstance(st, dict)],
            ensure_ascii=False,
        )[:3000]
        prompt = (
            "你是需求完整性审计员。下面是问题原文与需求分解计划（子任务列表）。"
            "请找出问题原文中【明确要求】但子任务列表【未覆盖】的交付物或约束。\n"
            "只返回 JSON，格式：{\"uncovered\":[\"...\",\"...\"],\"reason\":\"...\"}，"
            "若无缺口返回 {\"uncovered\":[],\"reason\":\"\"}。\n\n"
            f"模板: {template}，工作流: {workflow_type}\n"
            f"问题原文（截断）：\n{problem_text}\n\n"
            f"子任务列表：\n{subtask_brief}"
        )
        resp = await agent.call_llm(
            [
                {"role": "system", "content": "You are a requirement coverage auditor. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        content = (resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                   if isinstance(resp, dict) else "")
        # 容错解析 JSON（LLM 可能包裹 ```json ... ``` 或附带说明）
        m = re.search(r"\{.*\}", content, re.DOTALL)
        payload = json.loads(m.group(0)) if m else {}
        uncovered = payload.get("uncovered", []) if isinstance(payload, dict) else []
        if not isinstance(uncovered, list):
            uncovered = []
        gaps: List[Dict[str, Any]] = []
        for item in uncovered[:8]:
            gaps.append({
                "severity": "warning",
                "category": "coverage_gap_llm",
                "message": f"LLM 语义覆盖缺口: {str(item)[:200]}",
            })
        return gaps

    async def _node_data_quality_check(self, state: TaskState) -> TaskState:
        """数据质量门禁（pre 阶段）：插在 parallel_analysis 与建模 Agent 之间。

        全确定性、Code-as-Truth：复用 DataSchemaExtractor 重新读取文件计算
        null_count / unique_count / numeric_summary，不信任 data_agent 自报的缺失率，
        并与之对账（防 LLM 估算/编造）。门禁未通过时阻断建模流程。
        """
        from pathlib import Path

        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] data_quality_check: 开始数据质量门禁校验")

        try:
            files = list(state.get("files", []) or [])
            # 由 _route_after_parallel_analysis 保证仅 files 非空时进入；此处作防御
            if not files:
                logger.info(f"[LangGraph:{task_id}] data_quality_check: 无数据文件，跳过门禁")
                return {**state, "current_step": "data_quality_check"}

            self._update_progress(task_id, state["problem_text"], 32, "数据质量门禁校验中")

            from ..services.data_schema import get_schema_extractor
            extractor = get_schema_extractor()

            issues: List[Dict[str, Any]] = []
            per_file_reports: List[Dict[str, Any]] = []
            metric_candidates = []  # [(指标键, 值)] 用于 check_metric_ranges
            total_cells = 0
            total_null = 0
            fatal = False

            # 不应出现负值的列名关键词
            non_negative_keywords = (
                "count", "price", "age", "数量", "价格", "年龄", "金额", "总额",
            )
            # 显式指标列名关键词（与 symbolic_auditor.range_rules 对齐）
            metric_keywords = (
                "accuracy", "precision", "recall", "f1", "auc", "r2",
                "r_squared", "sharpe", "max_drawdown", "return_rate",
            )

            # ===== 步骤 2 文件级门禁（数据缺失检测） + 步骤 3 脏数据检测 =====
            for fp in files:
                path = Path(fp)
                file_name = path.name

                # --- 文件缺失 ---
                if not path.exists():
                    issues.append({
                        "severity": "error", "category": "file_missing", "fatal": True,
                        "file": str(path),
                        "message": f"数据文件不存在: {file_name}",
                    })
                    fatal = True
                    per_file_reports.append({
                        "file": str(path), "file_name": file_name,
                        "shape": [0, 0], "missing_rate": 1.0,
                        "columns": [], "issues": ["file_missing"],
                    })
                    continue

                try:
                    size = path.stat().st_size
                except OSError as st_exc:
                    issues.append({
                        "severity": "error", "category": "unreadable", "fatal": True,
                        "file": str(path),
                        "message": f"无法读取文件状态: {st_exc}",
                    })
                    fatal = True
                    continue

                # --- 空文件 ---
                if size == 0:
                    issues.append({
                        "severity": "error", "category": "empty_file", "fatal": True,
                        "file": str(path),
                        "message": f"数据文件为空（0 字节）: {file_name}",
                    })
                    fatal = True
                    per_file_reports.append({
                        "file": str(path), "file_name": file_name,
                        "shape": [0, 0], "missing_rate": 1.0,
                        "columns": [], "issues": ["empty_file"],
                    })
                    continue

                # --- 不支持的类型 ---
                if path.suffix.lower() not in extractor.SUPPORTED_EXTS:
                    issues.append({
                        "severity": "warning", "category": "unsupported_type", "fatal": False,
                        "file": str(path),
                        "message": f"不支持的数据文件类型: {path.suffix}",
                    })
                    per_file_reports.append({
                        "file": str(path), "file_name": file_name,
                        "shape": [0, 0], "missing_rate": 0.0,
                        "columns": [], "issues": ["unsupported_type"],
                    })
                    continue

                # --- 不可读 ---
                schema = extractor.extract(path)
                if not schema:
                    issues.append({
                        "severity": "error", "category": "unreadable", "fatal": True,
                        "file": str(path),
                        "message": f"数据文件无法解析为表格: {file_name}",
                    })
                    fatal = True
                    per_file_reports.append({
                        "file": str(path), "file_name": file_name,
                        "shape": [0, 0], "missing_rate": 1.0,
                        "columns": [], "issues": ["unreadable"],
                    })
                    continue

                rows, cols = schema.get("shape", [0, 0])
                columns = schema.get("columns", []) or []
                file_null = sum(int(c.get("null_count", 0) or 0) for c in columns)
                cells = max(rows * cols, 1)
                missing_rate = file_null / cells
                total_cells += cells
                total_null += file_null

                file_issues: List[str] = []

                # 无数据行
                if rows == 0:
                    issues.append({
                        "severity": "error", "category": "empty_data", "fatal": True,
                        "file": file_name,
                        "message": f"数据文件无数据行（0 行）: {file_name}",
                    })
                    fatal = True
                    file_issues.append("empty_data")

                for c in columns:
                    cname = str(c.get("name", ""))
                    null_count = int(c.get("null_count", 0) or 0)
                    unique_count = int(c.get("unique_count", 0) or 0)

                    # 全空列
                    if rows > 0 and null_count >= rows:
                        issues.append({
                            "severity": "error", "category": "empty_column", "fatal": True,
                            "file": file_name, "column": cname,
                            "message": f"列 '{cname}' 全部为空（{null_count}/{rows}）",
                        })
                        fatal = True
                        file_issues.append("empty_column")

                    # 高缺失：>0.6 致命，>0.3 警告
                    col_missing = null_count / max(rows, 1)
                    if rows > 0 and col_missing > 0.6:
                        issues.append({
                            "severity": "error", "category": "high_missing", "fatal": True,
                            "file": file_name, "column": cname,
                            "message": f"列 '{cname}' 缺失率过高: {col_missing:.1%}",
                        })
                        fatal = True
                        file_issues.append("high_missing")
                    elif rows > 0 and col_missing > 0.3:
                        issues.append({
                            "severity": "warning", "category": "moderate_missing", "fatal": False,
                            "file": file_name, "column": cname,
                            "message": f"列 '{cname}' 缺失率偏高: {col_missing:.1%}",
                        })
                        file_issues.append("moderate_missing")

                    # 常量列（无信息量）
                    if rows > 1 and unique_count <= 1:
                        issues.append({
                            "severity": "warning", "category": "constant_column", "fatal": False,
                            "file": file_name, "column": cname,
                            "message": f"列 '{cname}' 为常量列（唯一值数={unique_count}），无信息量",
                        })
                        file_issues.append("constant_column")

                    # 非法负值 + 指标列范围候选（复用 schema 已算出的 numeric_summary）
                    ns = c.get("numeric_summary")
                    if isinstance(ns, dict):
                        cmin = ns.get("min")
                        cmax = ns.get("max")
                        cname_lower = cname.lower()
                        if isinstance(cmin, (int, float)) and cmin < 0 and any(
                            kw in cname_lower for kw in non_negative_keywords
                        ):
                            issues.append({
                                "severity": "warning", "category": "negative_value", "fatal": False,
                                "file": file_name, "column": cname,
                                "message": f"列 '{cname}' 出现非法负值（min={cmin}）",
                            })
                            file_issues.append("negative_value")
                        # 收集指标列的 min/max 候选，交给 check_metric_ranges 做范围校验
                        if any(kw in cname_lower for kw in metric_keywords):
                            if isinstance(cmin, (int, float)):
                                metric_candidates.append((f"{cname}__min", float(cmin)))
                            if isinstance(cmax, (int, float)):
                                metric_candidates.append((f"{cname}__max", float(cmax)))

                per_file_reports.append({
                    "file": str(path), "file_name": file_name,
                    "shape": [rows, cols],
                    "missing_rate": round(missing_rate, 4),
                    "columns": [
                        {"name": c.get("name"),
                         "null_count": c.get("null_count"),
                         "unique_count": c.get("unique_count")}
                        for c in columns
                    ],
                    "issues": file_issues,
                })

            overall_missing = total_null / max(total_cells, 1)

            # ===== （可选增强）显式指标列范围校验 =====
            if metric_candidates:
                try:
                    from ..services.symbolic_auditor import check_metric_ranges
                    # check_metric_ranges 忽略元组后两位，仅按内置 range_rules 校验 value
                    metrics_dict = {k: (v, 0.0, 0.0) for k, v in metric_candidates}
                    for finding in check_metric_ranges(metrics_dict):
                        issues.append({
                            "severity": "warning", "category": "metric_range", "fatal": False,
                            "message": finding.message,
                        })
                except Exception as me:
                    logger.debug(
                        f"[LangGraph:{task_id}] data_quality_check: 指标范围校验跳过: {me}"
                    )

            # ===== 步骤 4：data_agent 自报对账（防 LLM 估算/编造）=====
            divergences: List[Dict[str, Any]] = []
            try:
                results = self._resolve_results(state)
                data_out = results.get("data_agent", {})
                reported_by_name: Dict[str, float] = {}
                if isinstance(data_out, dict):
                    for a in data_out.get("analyses", []) or []:
                        if not isinstance(a, dict):
                            continue
                        fname = a.get("file_name")
                        if not fname and a.get("file_path"):
                            try:
                                fname = Path(a["file_path"]).name
                            except Exception:
                                fname = ""
                        dq = a.get("data_quality")
                        if not isinstance(dq, dict):
                            nested = a.get("analysis")
                            if isinstance(nested, dict):
                                dq = nested.get("data_quality")
                        if isinstance(dq, dict):
                            mr = dq.get("missing_rate")
                            if isinstance(mr, (int, float)):
                                # 兼容百分比（>1）/ 小数（0-1）
                                reported = float(mr) / 100.0 if float(mr) > 1.0 else float(mr)
                                reported_by_name[str(fname)] = reported

                for pfr in per_file_reports:
                    fname = str(pfr.get("file_name"))
                    recomputed = pfr.get("missing_rate", 0.0)
                    if not isinstance(recomputed, (int, float)):
                        continue
                    reported = reported_by_name.get(fname)
                    if reported is None:
                        continue
                    recomputed_f = float(recomputed)
                    # 重算值≈0 时退化为绝对差，避免除零
                    if recomputed_f > 1e-4:
                        rel_diff = abs(reported - recomputed_f) / recomputed_f
                    else:
                        rel_diff = abs(reported - recomputed_f)
                    if rel_diff > 0.1:
                        divergences.append({
                            "file": fname,
                            "data_agent_missing_rate": round(reported, 4),
                            "recomputed_missing_rate": round(recomputed_f, 4),
                            "relative_diff": round(rel_diff, 4),
                        })
                        issues.append({
                            "severity": "warning", "category": "data_agent_divergence",
                            "fatal": False, "file": fname,
                            "message": (
                                f"data_agent 自报缺失率 {reported:.2%} 与重算值 "
                                f"{recomputed_f:.2%} 偏差过大（相对差 {rel_diff:.1%}）"
                            ),
                        })
            except Exception as div_exc:
                logger.debug(
                    f"[LangGraph:{task_id}] data_quality_check: data_agent 对账失败: {div_exc}"
                )

            # ===== 步骤 5：判定 =====
            passed = (not fatal) and overall_missing < 0.6
            report = {
                "task_id": task_id,
                "file_count": len(files),
                "per_file": per_file_reports,
                "overall_missing_rate": round(overall_missing, 4),
                "issue_count": len(issues),
                "issues": issues,
                "data_agent_divergence": divergences,
                "passed": passed,
                "checked_at": datetime.now().isoformat(),
            }

            # ===== 步骤 6：写回 + 通知 =====
            ref = self._set_result(state, "data_quality_check", report)
            wm = self._get_working_memory(task_id)
            if wm:
                try:
                    wm.set_result("data_quality_check", report)
                except Exception:
                    pass

            if passed:
                self._post_chat(
                    task_id, "data_quality_check",
                    f"✅ 数据质量门禁通过：{len(files)} 个文件，整体缺失率 "
                    f"{overall_missing:.1%}，{len(issues)} 个提示",
                )
            else:
                err_count = sum(1 for i in issues if i.get("severity") == "error")
                self._post_chat(
                    task_id, "data_quality_check",
                    f"⚠️ 数据质量门禁未通过：{len(issues)} 个问题（{err_count} 个错误），"
                    f"建议补充或清洗数据",
                )

            # ===== 步骤 7：返回（校验问题写回 _quality_issues 列表，无则新增）=====
            existing_issues = list(state.get("_quality_issues", []) or [])
            existing_issues.extend(issues)

            new_state: TaskState = {
                **state,
                "results": {**state.get("results", {}), **ref},
                "current_step": "data_quality_check",
                "_quality_issues": existing_issues,
            }
            if not passed:
                new_state["cannot_solve_report"] = {
                    "reason": "数据质量门禁未通过",
                    "issues": [i.get("message", str(i)) for i in issues[:5]],
                }

            logger.info(
                f"[LangGraph:{task_id}] data_quality_check: passed={passed}, "
                f"files={len(files)}, overall_missing={overall_missing:.1%}, "
                f"issues={len(issues)}, divergences={len(divergences)}"
            )
            return new_state

        except Exception as e:
            logger.warning(
                f"[LangGraph:{task_id}] data_quality_check 失败，跳过门禁: {e}",
                exc_info=True,
            )
            return state

    async def _node_literature_dedup(self, state: TaskState) -> TaskState:
        """文献去重节点（pre 阶段）：在 writer 消费 literature 前做最终去重。

        图位置：插入在 figure 与 writer 之间（figure -> literature_dedup -> writer），
        这样在 writer 消费 literature 前做最终去重；修订路径（results 已有 writer_agent
        且含 citations）时还能清洗 writer 已有的 citations。

        范式镜像 _node_ast_audit/_node_fact_check：用 _resolve_results/_set_result 做
        state I/O，_post_chat 通知。复用 reference_verifier 的 _normalize_title() /
        _title_similarity() 做键归一化，复用 _verify_arxiv 内 re.sub(r"v\\d+$","",...)
        的 arXiv 版本号剥离惯用法。

        去重键（按优先级）：arxiv_id（剥版本号+小写）/ doi（去前缀+小写）/
        title（_normalize_title）/ url（去 query+去尾斜杠+小写）。命中任一键即判重复。
        无强 id（无 arxiv_id 且无 doi）时，对已保留标题调用 _title_similarity，
        >=0.85 视为同一篇。重复项的非空字段回填进被保留项的空缺（merge），保留
        richer record，避免丢元数据。
        """
        task_id = state["task_id"]
        try:
            from ..services.reference_verifier import _normalize_title, _title_similarity

            workflow_type = state.get("workflow_type", "standard")
            template = state.get("paper_template", "math_modeling")

            # ===== 1) 守卫：quick/code_focused 或 research_agent 结果为空 → 跳过 =====
            if workflow_type in ("quick", "code_focused"):
                logger.info(f"[LangGraph:{task_id}] literature_dedup skipped (workflow={workflow_type})")
                return {**state, "current_step": "literature_dedup_skipped"}

            results = self._resolve_results(state)
            research_output = results.get("research_agent")
            if not isinstance(research_output, dict):
                research_output = {}
            papers = research_output.get("papers", []) or []
            methods = research_output.get("methods", []) or []

            if not papers and not methods:
                logger.info(f"[LangGraph:{task_id}] literature_dedup skipped (research_agent empty)")
                return {**state, "current_step": "literature_dedup_skipped"}

            self._update_progress(task_id, state["problem_text"], 67, "文献去重中")

            # ===== 规范化键（复用 reference_verifier 的归一化逻辑） =====
            def _norm_arxiv(raw):
                if not raw:
                    return ""
                x = str(raw).strip().lower()
                x = re.sub(r"^arxiv\s*:\s*", "", x)
                return re.sub(r"v\d+$", "", x)  # 复用 _verify_arxiv 版本剥离惯用法

            def _norm_doi(raw):
                if not raw:
                    return ""
                d = str(raw).strip().lower()
                d = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d)
                d = re.sub(r"^doi:\s*", "", d)
                return d

            def _norm_url(raw):
                if not raw:
                    return ""
                u = str(raw).strip().lower()
                u = re.sub(r"\?.*$", "", u)  # 去 query string
                return u.rstrip("/")

            def _register_keys(seen_dict, idx, ka, kd, ku, kt):
                """把四元组键注册到 seen，指向 kept 中的索引（仅注册非空值）。"""
                for key_str in (f"arxiv:{ka}", f"doi:{kd}", f"url:{ku}", f"title:{kt}"):
                    if key_str.split(":", 1)[1] and key_str not in seen_dict:
                        seen_dict[key_str] = idx

            def _dedup_citations(cits):
                """对 citation 列表去重，返回 (去重后列表, 移除数)。"""
                removed = 0
                if not isinstance(cits, list) or not cits:
                    return cits, 0
                seen_c: Dict[str, int] = {}
                out: List[Any] = []
                for c in cits:
                    if not isinstance(c, dict):
                        out.append(c)
                        continue
                    ka = _norm_arxiv(c.get("arxiv_id"))
                    kd = _norm_doi(c.get("doi"))
                    kt = _normalize_title(c.get("title", "") or "")
                    ku = _norm_url(c.get("url"))
                    hit = None
                    for _, key_str in (
                        (f"arxiv:{ka}", "arxiv_id"),
                        (f"doi:{kd}", "doi"),
                        (f"url:{ku}", "url"),
                        (f"title:{kt}", "title"),
                    ):
                        if key_str.split(":", 1)[1] and key_str in seen_c:
                            hit = seen_c[key_str]
                            break
                    # 无强 id（无 arxiv_id 且无 doi）→ 标题模糊匹配
                    if hit is None and not (ka or kd) and kt and out:
                        ctitle = c.get("title", "") or ""
                        for i, oc in enumerate(out):
                            if not isinstance(oc, dict):
                                continue
                            ot = _normalize_title(oc.get("title", "") or "")
                            if ot and _title_similarity(ctitle, oc.get("title", "") or "") >= 0.85:
                                hit = i
                                break
                    if hit is not None:
                        keeper = out[hit]
                        for f in ("doi", "venue", "author", "year", "arxiv_id",
                                  "url", "title", "publisher"):
                            v = c.get(f)
                            if v and not keeper.get(f):
                                keeper[f] = v
                        removed += 1
                    else:
                        out.append(dict(c))
                        _register_keys(seen_c, len(out) - 1, ka, kd, ku, kt)
                return out, removed

            # ===== 2-4) papers 去重主循环 =====
            seen: Dict[str, int] = {}
            kept: List[Dict[str, Any]] = []
            kept_titles: List[str] = []
            duplicates: List[Dict[str, Any]] = []

            for paper in papers:
                if not isinstance(paper, dict):
                    continue
                k_arxiv = _norm_arxiv(paper.get("arxiv_id"))
                k_doi = _norm_doi(paper.get("doi"))
                k_title = _normalize_title(paper.get("title", "") or "")
                k_url = _norm_url(paper.get("url"))

                hit_idx = None
                hit_reason = ""
                for label, key_str in (
                    ("arxiv_id", f"arxiv:{k_arxiv}"),
                    ("doi", f"doi:{k_doi}"),
                    ("url", f"url:{k_url}"),
                    ("title", f"title:{k_title}"),
                ):
                    if key_str.split(":", 1)[1] and key_str in seen:
                        hit_idx = seen[key_str]
                        hit_reason = label
                        break

                # 无强 id（无 arxiv_id 且无 doi）→ 标题模糊匹配（捕获大小写/标点/尾句号差异）
                if hit_idx is None and not (k_arxiv or k_doi) and k_title and kept_titles:
                    best_sim = 0.0
                    best_idx = -1
                    ptitle = paper.get("title", "") or ""
                    for i, kt in enumerate(kept_titles):
                        if not kt:
                            continue
                        sim = _title_similarity(ptitle, kt)
                        if sim > best_sim:
                            best_sim = sim
                            best_idx = i
                    if best_sim >= 0.85 and best_idx >= 0:
                        hit_idx = best_idx
                        hit_reason = f"title_similarity({best_sim:.2f})"

                if hit_idx is not None:
                    # 重复：把非空字段回填进被保留项的空缺（merge），保留 richer record
                    keeper = kept[hit_idx]
                    for f in ("doi", "venue", "authors", "abstract", "year",
                              "arxiv_id", "url", "title", "publisher", "author"):
                        val = paper.get(f)
                        if val and not keeper.get(f):
                            keeper[f] = val
                    # 传递性：注册 keeper 新获得的键，避免后续同 id 漏判
                    _register_keys(
                        seen, hit_idx,
                        _norm_arxiv(keeper.get("arxiv_id")),
                        _norm_doi(keeper.get("doi")),
                        _norm_url(keeper.get("url")),
                        _normalize_title(keeper.get("title", "") or ""),
                    )
                    kept_titles[hit_idx] = _normalize_title(keeper.get("title", "") or "")
                    duplicates.append({
                        "title": paper.get("title", ""),
                        "reason": hit_reason,
                        "merged_into": keeper.get("title", ""),
                    })
                else:
                    kept.append(dict(paper))
                    idx = len(kept) - 1
                    _register_keys(seen, idx, k_arxiv, k_doi, k_url, k_title)
                    kept_titles.append(k_title)

            # ===== 5) methods 去重：按规范化 name 去重，合并 description =====
            seen_methods: Dict[str, int] = {}
            deduped_methods: List[Dict[str, Any]] = []
            method_removed = 0
            for m in methods:
                if not isinstance(m, dict):
                    continue
                name = m.get("name") or m.get("method_name") or ""
                k_name = _normalize_title(name) if name else ""
                if k_name and k_name in seen_methods:
                    keeper = deduped_methods[seen_methods[k_name]]
                    desc = m.get("description") or m.get("summary") or ""
                    if desc:
                        existing = keeper.get("description", "") or ""
                        if desc not in existing:
                            keeper["description"] = (existing + " " + desc).strip() if existing else desc
                    method_removed += 1
                else:
                    deduped_methods.append(dict(m))
                    if k_name:
                        seen_methods[k_name] = len(deduped_methods) - 1

            # ===== 6) 修订路径：清洗 writer_agent 已有 citations =====
            writer_citations_removed = 0
            ref_writer: Dict[str, Any] = {}
            writer_output = results.get("writer_agent")
            has_writer_cits = isinstance(writer_output, dict) and (
                bool(writer_output.get("citations"))
                or (isinstance(writer_output.get("paper_memory"), dict)
                    and bool(writer_output["paper_memory"].get("citations")))
            )
            if has_writer_cits:
                writer_output = dict(writer_output)
                deduped_cits, r1 = _dedup_citations(writer_output.get("citations"))
                writer_citations_removed += r1
                if deduped_cits is not None:
                    writer_output["citations"] = deduped_cits
                pm = writer_output.get("paper_memory")
                if isinstance(pm, dict):
                    pm = dict(pm)
                    deduped_pm_cits, r2 = _dedup_citations(pm.get("citations"))
                    writer_citations_removed += r2
                    if deduped_pm_cits is not None:
                        pm["citations"] = deduped_pm_cits
                    writer_output["paper_memory"] = pm
                ref_writer = self._set_result(state, "writer_agent", writer_output)

            # ===== 7) 生成报告（结构参考 code_audit.AuditResult / fact_checker report） =====
            report: Dict[str, Any] = {
                "enabled": True,
                "paper_template": template,
                "original_paper_count": len(papers),
                "deduped_paper_count": len(kept),
                "removed_count": len(papers) - len(kept),
                "duplicates": duplicates,
                "method_removed": method_removed,
                "writer_citations_removed": writer_citations_removed,
                "ran_at": datetime.now().isoformat(),
            }

            # ===== 8) 回写 research_agent（去重后 papers/methods + 报告） =====
            updated = {
                **research_output,
                "papers": kept,
                "methods": deduped_methods,
                "_literature_dedup": report,
            }
            ref_research = self._set_result(state, "research_agent", updated)
            self._set_result(state, "literature_dedup", report)  # 独立存储，供 _resolve_results 读取

            # ===== 校验问题写回 state 的 _quality_issues 列表（无则新增） =====
            quality_issues: List[str] = list(state.get("_quality_issues", []) or [])
            if report["removed_count"] > 0:
                quality_issues.append(
                    f"literature_dedup: 检测到 {report['removed_count']} 篇重复文献"
                    f"（共 {report['original_paper_count']} 篇），已合并/移除"
                )
            if method_removed > 0:
                quality_issues.append(f"literature_dedup: 合并 {method_removed} 个重复方法")
            if writer_citations_removed > 0:
                quality_issues.append(
                    f"literature_dedup: 修订路径清理 {writer_citations_removed} 条重复 writer citations"
                )

            # ===== 9) _post_chat 统计通知 + 返回 =====
            self._post_chat(
                task_id, "literature_dedup",
                f"📚 文献去重完成：{report['original_paper_count']} → {report['deduped_paper_count']} 篇"
                f"（移除 {report['removed_count']} 篇重复，合并 {method_removed} 个方法"
                + (f"，清理 {writer_citations_removed} 条重复引用" if writer_citations_removed else "")
                + "）",
            )
            logger.info(
                f"[LangGraph:{task_id}] literature_dedup: "
                f"{report['original_paper_count']}→{report['deduped_paper_count']} papers, "
                f"removed={report['removed_count']}, method_removed={method_removed}, "
                f"writer_citations_removed={writer_citations_removed}"
            )

            return {
                **state,
                "results": {
                    **state.get("results", {}),
                    **ref_research,
                    **ref_writer,
                    "literature_dedup": report,
                },
                "_quality_issues": quality_issues,
                "current_step": "literature_dedup_done",
            }
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] literature_dedup failed: {exc}", exc_info=True)
            return state


    async def _node_novelty_check(self, state: TaskState) -> TaskState:
        """创新点新颖性核查（pre 阶段）：检查 writer 声称的创新点是否已被研究文献覆盖。

        复用 IdeaArchive 的近重复相似度评分器（0.4 标题 + 0.4 方法 + 0.2 新颖性 Jaccard），
        指向 research_agent 收集的论文语料，闭合"创新点是否已被覆盖"的核查缺口。
        镜像 _node_fact_check 的提取-比对-报告结构（数字→创新点，solves.json→论文语料）。

        PLACEMENT: 插入 writer → peer_review 之间（writer→novelty_check→peer_review），
        让 peer_review / review_defect_router 能读到 results["novelty_checker"]。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] novelty_check: 启动创新点覆盖核查")
        self._update_progress(task_id, state.get("problem_text", ""), 92, "创新点覆盖核查中")

        results = self._resolve_results(state)
        research = results.get("research_agent", {})
        papers = research.get("papers", []) if isinstance(research, dict) else []
        workflow_type = state.get("workflow_type", "standard")

        # ===== 0. 跳过门：文献语料 <2 或 quick/code_focused 工作流 =====
        if len(papers) < 2 or workflow_type in ("quick", "code_focused"):
            logger.info(f"[LangGraph:{task_id}] novelty_check: 文献语料<2 / quick工作流，跳过核查")
            skip_report = {
                "task_id": task_id,
                "enabled": True,
                "passed": True,
                "skipped": True,
                "reason": "literature corpus <2 / quick workflow",
            }
            self._set_result(state, "novelty_checker", skip_report)
            return {
                **state,
                "results": {**state.get("results", {}), "novelty_checker": skip_report},
                "current_step": "novelty_check_skipped",
                "novelty_check_passed": True,
            }

        try:
            from ..core.idea_archive import IdeaArchive
            from ..core.context_compressor import estimate_tokens

            archive = IdeaArchive()  # 仅复用纯相似度方法，不写入 archive
            COVER_THRESHOLD = 0.7
            MID_BAND = (0.4, 0.7)
            CORPUS_TOKEN_BUDGET = 6000
            MAX_NOVELTY_CHARS = 600

            # ===== 1. 提取 writer 声称的创新点（FactChecker.extract-from-LaTeX 风格）=====
            writer = results.get("writer_agent", {})
            latex = writer.get("latex_code", "") if isinstance(writer, dict) else ""
            abstract = writer.get("abstract", "") if isinstance(writer, dict) else ""

            claims: List[Dict[str, Any]] = []

            # 1a. 结构化创新点：来自 innovation_analysis.innovation_ideas（归一化到 IdeaArchive 的 {title, methodology, novelty} 模式）
            innovation_analysis = state.get("innovation_analysis") or {}
            if isinstance(innovation_analysis, dict):
                for idea in innovation_analysis.get("innovation_ideas", []) or []:
                    if not isinstance(idea, dict):
                        continue
                    claims.append({
                        "title": idea.get("title", ""),
                        "methodology": idea.get("methodology", ""),
                        "novelty": idea.get("novelty", idea.get("expected_contribution", "")),
                        "source": "innovation_analysis",
                    })

            # 1b. 从 LaTeX 创新/贡献章节抽取（含 \\item / （1）枚举）
            section_re = re.compile(r"\\section\*?\{([^}]*)\}")
            section_hits = list(section_re.finditer(latex))
            for idx, sm in enumerate(section_hits):
                sec_title = sm.group(1)
                if not re.search(r"(创新|贡献|novelty|contribution|模型评价|创新点)", sec_title, re.IGNORECASE):
                    continue
                body_start = sm.end()
                body_end = section_hits[idx + 1].start() if idx + 1 < len(section_hits) else len(latex)
                body = latex[body_start:body_end]
                items = re.split(r"\\item\b|\n\s*[（(]\s*[0-9]+\s*[)）]", body)
                for it in items:
                    it = it.strip()
                    if len(it) < 12:
                        continue
                    claims.append({
                        "title": re.sub(r"\s+", " ", it)[:80],
                        "methodology": it,
                        "novelty": it,
                        "source": "writer_latex",
                    })

            # 1c. 摘要兜底：无任何结构化创新点时，把摘要作为单一 claim
            if not claims and abstract:
                claims.append({
                    "title": re.sub(r"\s+", " ", abstract)[:80],
                    "methodology": abstract,
                    "novelty": abstract,
                    "source": "writer_abstract",
                })

            if not claims:
                logger.warning(f"[LangGraph:{task_id}] novelty_check: 未提取到创新点声明，跳过覆盖核查")

            # ===== 2. 构建已知文献语料（token 预算受限，防止 50 篇综述撑爆上下文）=====
            corpus: List[Dict[str, Any]] = []
            budget_used = 0
            for p in papers:
                if not isinstance(p, dict):
                    continue
                entry = {
                    "title": p.get("title", ""),
                    "methodology": p.get("methods") or p.get("method") or p.get("key_technique") or "",
                    "novelty": (p.get("abstract", "") or "")[:MAX_NOVELTY_CHARS],
                    "arxiv_id": p.get("arxiv_id", ""),
                    "source": "research_agent",
                }
                cost = estimate_tokens(entry)
                if corpus and budget_used + cost > CORPUS_TOKEN_BUDGET:
                    break
                corpus.append(entry)
                budget_used += cost

            # ===== 3. 覆盖核查：每个 claim 对语料求最大相似度（IdeaArchive._compute_similarity）=====
            claim_assessments: List[Dict[str, Any]] = []
            for claim in claims:
                best_title, best_sim = "", 0.0
                for paper in corpus:
                    sim = archive._compute_similarity(
                        claim.get("title", ""), claim.get("methodology", ""), claim.get("novelty", ""),
                        paper.get("title", ""), paper.get("methodology", ""), paper.get("novelty", ""),
                    )
                    if sim > best_sim:
                        best_title, best_sim = paper.get("title", ""), sim
                claim_assessments.append({
                    "claim": claim,
                    "best_paper_title": best_title,
                    "best_sim": best_sim,
                })

            covered_claims: List[Dict[str, Any]] = [
                {
                    "claim": a["claim"].get("title", ""),
                    "covered_by_paper_title": a["best_paper_title"],
                    "similarity": a["best_sim"],
                    "reason": "similarity>=0.7",
                }
                for a in claim_assessments
                if a["best_sim"] >= COVER_THRESHOLD
            ]

            # ===== 4. 双向检查（镜像 FactChecker.compare 反向）：claim 与文献重叠但该文献未被 \\cite =====
            try:
                from .writer_agent import WriterAgent
                cite_keys = WriterAgent._scan_cite_keys(latex)
            except Exception:
                cite_keys = re.findall(r"\\cite[a-z]*\{([^}]+)\}", latex)

            def _is_paper_cited(paper: Dict[str, Any]) -> bool:
                ax = paper.get("arxiv_id", "")
                if ax and ax in latex:
                    return True
                title_tokens = {t for t in re.findall(r"\w+", paper.get("title", "").lower()) if len(t) > 2}
                if not title_tokens:
                    return False
                for k in cite_keys:
                    k_tokens = set(re.findall(r"\w+", k.lower()))
                    if not k_tokens:
                        continue
                    inter = len(title_tokens & k_tokens)
                    if inter >= 2 and inter / len(title_tokens) >= 0.4:
                        return True
                return False

            paper_by_title = {pp.get("title", ""): pp for pp in corpus}
            uncited_overlap: List[Dict[str, Any]] = []
            for cov in covered_claims:
                paper_obj = paper_by_title.get(cov.get("covered_by_paper_title", ""))
                if paper_obj and not _is_paper_cited(paper_obj):
                    uncited_overlap.append({
                        "claim": cov.get("claim", ""),
                        "paper_title": cov.get("covered_by_paper_title", ""),
                        "similarity": cov.get("similarity", 0.0),
                        "severity": "error",
                        "reason": "claim asserts novelty but overlaps an uncited paper",
                    })

            # ===== 5. LLM tie-break：0.4–0.7 中间带 Jaccard 不可靠时（_node_discuss_approach call_llm 模式）=====
            mid_claims = [a for a in claim_assessments if MID_BAND[0] <= a["best_sim"] < MID_BAND[1]]
            llm_agent = None
            for cand in ("peer_review_agent", "analyzer_agent", "research_agent", "writer_agent"):
                cand_agent = self.agents.get(cand)
                if cand_agent and hasattr(cand_agent, "call_llm"):
                    llm_agent = cand_agent
                    break
            for a in mid_claims[:5]:
                if llm_agent is None:
                    break
                prompt = (
                    "你是创新性评审专家。判断以下创新点是否已被该论文覆盖（方法/思路相同即算覆盖）。\n"
                    f"创新点: {a['claim'].get('title', '')}\n"
                    f"创新点方法: {a['claim'].get('methodology', '')[:200]}\n"
                    f"论文标题: {a['best_paper_title']}\n"
                    "只输出 JSON: {\"covered\": true/false, \"reason\": \"...\"}"
                )
                if estimate_tokens(prompt) > 2000:
                    prompt = prompt[:4000]
                try:
                    resp = await llm_agent.call_llm(
                        [
                            {"role": "system", "content": "你是创新性评审专家，只输出合法 JSON。"},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                    )
                    content = ""
                    if isinstance(resp, dict):
                        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                    jm = re.search(r"\{.*\}", content, re.DOTALL)
                    if jm:
                        verdict = json.loads(jm.group(0))
                        if verdict.get("covered"):
                            covered_claims.append({
                                "claim": a["claim"].get("title", ""),
                                "covered_by_paper_title": a["best_paper_title"],
                                "similarity": a["best_sim"],
                                "reason": f"LLM: {verdict.get('reason', '')}",
                            })
                except Exception as llm_exc:
                    logger.debug(f"[LangGraph:{task_id}] novelty_check LLM tie-break 失败: {llm_exc}")

            # ===== 6. 打分 + 报告（镜像 FactChecker.check 报告结构）=====
            scores: List[float] = []
            for a in claim_assessments:
                dups = [{"similarity": a["best_sim"]}] if a["best_sim"] >= COVER_THRESHOLD else []
                scores.append(archive._compute_novelty_score(a["claim"], dups))
            novelty_score = (sum(scores) / len(scores)) if scores else 0.5

            has_error_uncited = any(o.get("severity") == "error" for o in uncited_overlap)
            passed = (len(covered_claims) == 0) and (not has_error_uncited)

            issues: List[Dict[str, Any]] = []
            for cov in covered_claims:
                issues.append({
                    "severity": "error",
                    "category": "novelty",
                    "node": "novelty_check",
                    "message": f"创新点「{cov.get('claim', '')}」疑似被文献《{cov.get('covered_by_paper_title', '')}》覆盖（相似度 {cov.get('similarity', 0.0):.2f}）",
                })
            for o in uncited_overlap:
                issues.append({
                    "severity": "error",
                    "category": "novelty",
                    "node": "novelty_check",
                    "message": f"创新点「{o.get('claim', '')}」与未引用文献《{o.get('paper_title', '')}》高度重叠（相似度 {o.get('similarity', 0.0):.2f}）",
                })

            report = {
                "task_id": task_id,
                "enabled": True,
                "passed": passed,
                "claim_count": len(claims),
                "paper_count": len(corpus),
                "covered_claims": covered_claims,
                "uncited_overlap": uncited_overlap,
                "novelty_score": round(novelty_score, 3),
                "issues": issues,
                "review_required": not passed,
            }

            # ===== 7. 写回 state =====
            self._set_result(state, "novelty_checker", report)

            claims_trace = list(state.get("claims_trace", []) or [])
            claims_trace.append({
                "timestamp": datetime.now().isoformat(),
                "node": "novelty_check",
                "novelty_score": round(novelty_score, 3),
                "covered_count": len(covered_claims),
                "uncited_count": len(uncited_overlap),
                "review_required": not passed,
            })

            quality_issues = list(state.get("_quality_issues", []) or [])
            if not passed:
                quality_issues.extend(issues)

            if not passed:
                self._post_chat(
                    task_id, "novelty_checker",
                    f"⚠️ 创新点新颖性核查未通过：{len(covered_claims)} 处疑似已被覆盖，"
                    f"{len(uncited_overlap)} 处未引用重叠，novelty_score={novelty_score:.2f}。"
                    "建议补充差异化论证或在论文中补引相关文献。",
                )
            else:
                self._post_chat(
                    task_id, "novelty_checker",
                    f"✅ 创新点新颖性核查通过：{len(claims)} 个创新点未见覆盖（novelty_score={novelty_score:.2f}）",
                )

            logger.info(
                f"[LangGraph:{task_id}] novelty_check: passed={passed} claims={len(claims)} "
                f"papers={len(corpus)} covered={len(covered_claims)} uncited={len(uncited_overlap)} "
                f"score={novelty_score:.2f}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), "novelty_checker": report},
                "claims_trace": claims_trace,
                "current_step": "novelty_check_done",
                "novelty_check_passed": passed,
                "_quality_issues": quality_issues,
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] novelty_check 失败: {e}")
            return {**state, "novelty_check_passed": False, "current_step": "novelty_check_failed"}

    async def _node_method_feasibility(self, state: TaskState) -> TaskState:
        """pre 阶段方法可行性预评估（建模后、求解前的可行性闸门）。

        逐子问题对 modeler_agent.sub_problem_models 做【确定性检查】+【LLM 裁决】，
        在 model 上注入 _feasibility（verdict/score/risks/alternative_method/
        library_matched/rationale）与 _method_swap 建议，避免把明显不可行的方法
        送入沙箱死亡螺旋浪费迭代。报告写入 results['method_feasibility'] 与
        method_feasibility_report，并同步黑板与 claims_trace / _quality_issues。
        """
        task_id = state["task_id"]
        state = await self._check_user_input(state)

        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent_name = self._select_modeling_agent(template, workflow_type)

        results = self._resolve_results(state)
        modeler_output = results.get("modeler_agent", {}) or {}
        sub_problem_models = (
            modeler_output.get("sub_problem_models", [])
            if isinstance(modeler_output, dict) else []
        )

        # 调研/综述模板或无建模输出 → 直接跳过
        if not modeling_agent_name or not sub_problem_models:
            logger.info(
                f"[LangGraph:{task_id}] method_feasibility: 无建模输出"
                f"（template={template}, agent={modeling_agent_name}），跳过"
            )
            return {
                **state,
                "method_feasibility_report": None,
                "current_step": "method_feasibility_skipped",
            }

        self._update_progress(task_id, state["problem_text"], 47, "方法可行性预评估中")
        logger.info(
            f"[LangGraph:{task_id}] method_feasibility start: "
            f"{len(sub_problem_models)} 个子问题模型"
        )

        try:
            # ===== 上下文准备 =====
            analyzer_output = results.get("analyzer_agent", {}) or {}
            data_output = results.get("data_agent", {}) or {}
            problem_type = (
                analyzer_output.get("problem_type", "")
                if isinstance(analyzer_output, dict) else ""
            )
            difficulty = (
                analyzer_output.get("difficulty", "")
                if isinstance(analyzer_output, dict) else ""
            )
            data_files = state.get("files", [])
            data_insights = (
                data_output.get("insights", [])
                if isinstance(data_output, dict) else []
            )
            solver_attempts = state.get("solver_attempts", [])
            error_count = state.get("error_count", 0)
            metrics_trend = list(state.get("metrics_trend", []))

            # v8.2 死亡螺旋上下文：连续未提升则更保守
            spiral_conservative = (
                len(metrics_trend) >= 2 and metrics_trend[-1] <= metrics_trend[-2]
            )

            # 方法库（不可用时降级跳过 B/E 检查，不阻断）
            method_lib = None
            try:
                from ..core.method_library import get_method_library
                method_lib = get_method_library()
            except Exception as lib_exc:
                logger.warning(
                    f"[LangGraph:{task_id}] method_library 不可用，"
                    f"跳过方法库检查: {lib_exc}"
                )

            # analyzer 子问题 problem_type 映射（按 id 索引）
            sp_types: Dict[Any, str] = {}
            sp_list = (
                analyzer_output.get("sub_problems", [])
                if isinstance(analyzer_output, dict) else []
            )
            for sp in sp_list:
                if isinstance(sp, dict):
                    sp_types[sp.get("id")] = sp.get("problem_type", "")

            def _ptype_to_lib_category(ptype: str) -> str:
                p = (ptype or "").lower()
                if "优化" in ptype or "规划" in ptype or "optim" in p:
                    return "optimization"
                if "预测" in ptype or "forecast" in p or "prediction" in p:
                    return "prediction"
                if "分类" in ptype or "classif" in p:
                    return "classification"
                if "聚类" in ptype or "cluster" in p:
                    return "clustering"
                if "评价" in ptype or "评估" in ptype or "evaluat" in p:
                    return "evaluation"
                if "仿真" in ptype or "simulat" in p:
                    return "simulation"
                return ""

            # LLM 裁决用 agent：analyzer_agent 优先，回退 modeler_agent
            llm_agent = (
                self.agents.get("analyzer_agent")
                or self.agents.get(modeling_agent_name)
            )

            per_problem: List[Dict[str, Any]] = []
            patched_models: List[Dict[str, Any]] = []
            overall_feasible = True
            quality_issues = list(state.get("_quality_issues", []))
            claims_trace = list(state.get("claims_trace", []))

            data_keywords = [
                "预测", "forecast", "回归", "分类", "时间序列",
                "time series", "learning", "机器学习", "训练", "predict",
            ]
            heuristic_keywords = [
                "启发式", "heuristic", "近似", "relax", "松弛", "遗传",
                "ga", "genetic", "模拟退火", "annealing", "元启发",
                "粒子群", "蚁群", "禁忌搜索",
            ]

            for idx, model in enumerate(sub_problem_models):
                if not isinstance(model, dict):
                    patched_models.append(model)
                    continue

                sp_id = model.get("sub_problem_id", idx + 1)
                sp_name = model.get("sub_problem_name", f"子问题{sp_id}")
                sp_type = (
                    sp_types.get(sp_id)
                    or model.get("model_type", "")
                    or problem_type
                )
                model_type = model.get("model_type", "")
                model_name = model.get("model_name", "")
                algo = model.get("algorithm", {})
                if isinstance(algo, dict):
                    algo_name = algo.get("name", "") or algo.get("description", "")
                else:
                    algo_name = str(algo)
                algo_name = (algo_name or model_name).strip()
                objective = str(model.get("objective_function", "") or "").strip()
                constraints = model.get("constraints", []) or []
                decision_vars = model.get("decision_variables", []) or []
                var_names = {
                    str(v.get("name", "")).strip()
                    for v in decision_vars
                    if isinstance(v, dict) and v.get("name")
                }

                risks: List[Dict[str, Any]] = []
                det_score = 100
                library_matched = False
                lib_alternatives: List[str] = []

                # --- A. 数据可得性 ---
                algo_lower = (algo_name + " " + sp_type + " " + model_name).lower()
                needs_data = any(kw in algo_lower for kw in data_keywords)
                if needs_data and not data_files and not data_insights:
                    risks.append({
                        "severity": "error", "category": "data",
                        "message": "预测/学习类方法需要数据，但 files 为空且 data_agent 无 insights",
                    })
                    det_score -= 30

                # --- B. 方法-问题一致性（method_library） ---
                if method_lib is not None:
                    try:
                        rec_cat = _ptype_to_lib_category(sp_type or problem_type)
                        if rec_cat:
                            recommended = method_lib.recommend_methods(
                                problem_type=rec_cat
                            )
                            lib_alternatives = [
                                m.name_cn or m.name for m in recommended
                            ]
                        if algo_name:
                            searched = method_lib.search_methods(query=algo_name)
                            matched = bool(searched)
                            if not matched:
                                for m in method_lib.methods.values():
                                    if algo_name.lower() in (m.name + m.name_cn).lower():
                                        matched = True
                                        break
                            library_matched = matched
                            if not matched:
                                risks.append({
                                    "severity": "warning",
                                    "category": "method_existence",
                                    "message": f"提议方法 '{algo_name}' 不在结构化方法库中",
                                })
                                det_score -= 10
                    except Exception as b_exc:
                        logger.warning(
                            f"[LangGraph:{task_id}] method_feasibility B 检查异常: {b_exc}"
                        )

                # --- C. 目标-约束自洽性 ---
                if not objective or len(objective) < 5:
                    risks.append({
                        "severity": "error", "category": "objective",
                        "message": "目标函数缺失或过短",
                    })
                    det_score -= 20
                else:
                    for c in constraints:
                        cexpr = (
                            c.get("expression", c.get("name", ""))
                            if isinstance(c, dict) else str(c)
                        )
                        for sym in re.findall(r'\$([A-Za-z_]\w*)\$', str(cexpr)):
                            if var_names and sym not in var_names:
                                risks.append({
                                    "severity": "warning",
                                    "category": "constraint_var",
                                    "message": f"约束引用未定义符号 ${sym}$",
                                })
                                det_score -= 5

                # --- D. 复杂度-难度-历史失败匹配 ---
                is_optimization = (
                    "优化" in sp_type or "规划" in sp_type
                    or "optim" in model_type.lower()
                )
                has_heuristic = any(
                    kw in algo_name.lower() for kw in heuristic_keywords
                )
                if difficulty == "困难" and is_optimization and not has_heuristic:
                    risks.append({
                        "severity": "warning", "category": "complexity",
                        "message": "困难优化问题未采用启发式/近似/松弛方法，求解可能不可行",
                    })
                    det_score -= 10
                if solver_attempts and error_count >= 2:
                    risks.append({
                        "severity": "warning", "category": "prior_failure",
                        "message": f"历史求解失败（error_count={error_count}），建议方法降级",
                    })
                    det_score -= 15

                # --- E. 依赖可用性 ---
                if method_lib is not None and library_matched:
                    try:
                        dep_method = None
                        for m in method_lib.methods.values():
                            if algo_name and algo_name.lower() in (m.name + m.name_cn).lower():
                                dep_method = m
                                break
                        if dep_method and dep_method.dependencies:
                            import importlib.util
                            for dep in dep_method.dependencies:
                                try:
                                    if importlib.util.find_spec(dep) is None:
                                        risks.append({
                                            "severity": "warning",
                                            "category": "dependency",
                                            "message": f"依赖包 {dep} 未安装",
                                        })
                                        det_score -= 5
                                except Exception:
                                    pass
                    except Exception as e_exc:
                        logger.warning(
                            f"[LangGraph:{task_id}] method_feasibility E 检查异常: {e_exc}"
                        )

                det_score = max(0, det_score)

                # ===== LLM 综合裁决（仿 _multi_agent_vote） =====
                verdict = "conditional"
                score_delta = 0
                llm_risks: List[str] = []
                alternative_method = ""
                rationale = ""
                degraded = False

                try:
                    if llm_agent is not None:
                        prompt = (
                            "你是数学建模方法可行性评审专家。对以下【子问题建模方案】做可行性预评估。\n"
                            "严格要求：宁可保守判定为 conditional/infeasible，禁止仅因方法名看起来高级就判 feasible；"
                            "只有当方法、数据、目标-约束均自洽且有落地路径时才判 feasible。\n\n"
                            f"子问题：{sp_name}\n"
                            f"问题类型：{sp_type}\n"
                            f"提议模型：{model_name}（{model_type}）\n"
                            f"算法：{algo_name}\n"
                            f"目标函数：{objective[:200]}\n"
                            f"决策变量：{', '.join(list(var_names)[:10])}\n"
                            f"数据可得性：{'有数据文件/insights' if (data_files or data_insights) else '无数据'}\n"
                            f"难度：{difficulty}\n"
                            f"方法库推荐备选：{', '.join(lib_alternatives) if lib_alternatives else '无'}\n"
                            f"确定性检查已发现风险：{json.dumps(risks, ensure_ascii=False)}\n"
                            f"历史求解失败：{'是(error_count=' + str(error_count) + ')' if (solver_attempts and error_count >= 2) else '否'}\n\n"
                            "只返回 JSON（不要其他文字）：\n"
                            '{"verdict":"feasible|conditional|infeasible",'
                            '"score_delta":-20到+10的整数,'
                            '"risks":["风险1","风险2"],'
                            '"alternative_method":"备选方法名或空",'
                            '"rationale":"一句话理由"}'
                        )
                        resp = await llm_agent.call_llm(
                            messages=[
                                {"role": "system", "content": "You are a strict mathematical-modeling feasibility reviewer. Return ONLY JSON."},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.1,
                        )
                        content = (
                            resp.get("choices", [{}])[0]
                            .get("message", {}).get("content", "")
                        )
                        extractor = getattr(llm_agent, "extract_json", None)
                        parsed = (
                            extractor(content) if callable(extractor) else None
                        )
                        if not parsed:
                            try:
                                parsed = json.loads(content)
                            except Exception:
                                parsed = None
                        if isinstance(parsed, dict):
                            v = str(parsed.get("verdict", "conditional")).lower()
                            verdict = v if v in ("feasible", "conditional", "infeasible") else "conditional"
                            try:
                                score_delta = int(parsed.get("score_delta", 0))
                            except Exception:
                                score_delta = 0
                            raw_risks = parsed.get("risks", [])
                            llm_risks = [str(r) for r in raw_risks if r] if isinstance(raw_risks, list) else []
                            alternative_method = str(parsed.get("alternative_method", "") or "")
                            rationale = str(parsed.get("rationale", "") or "")
                        else:
                            degraded = True
                    else:
                        degraded = True
                except Exception as llm_exc:
                    logger.warning(
                        f"[LangGraph:{task_id}] method_feasibility LLM 裁决失败"
                        f" (sp{sp_id})，降级为确定性裁决: {llm_exc}"
                    )
                    degraded = True

                # 降级裁决：仅确定性（死亡螺旋上下文更保守）
                if degraded:
                    if spiral_conservative:
                        verdict = (
                            "infeasible" if det_score < 70
                            else "conditional" if det_score < 85
                            else "feasible"
                        )
                    else:
                        verdict = (
                            "infeasible" if det_score < 60
                            else "conditional" if det_score < 80
                            else "feasible"
                        )

                # 合并 risks
                all_risks = list(risks)
                for r in llm_risks:
                    all_risks.append({
                        "severity": "warning", "category": "llm", "message": r,
                    })

                feasibility_score = max(0, det_score + score_delta)
                final_alt = (
                    alternative_method
                    or (lib_alternatives[0] if lib_alternatives else "")
                )
                if verdict == "infeasible":
                    overall_feasible = False

                # 写回 model 标注
                patched = {**model}
                patched["_feasibility"] = {
                    "verdict": verdict,
                    "score": feasibility_score,
                    "deterministic_score": det_score,
                    "risks": all_risks,
                    "alternative_method": final_alt,
                    "library_matched": library_matched,
                    "rationale": rationale or ("降级裁决（LLM 不可用）" if degraded else ""),
                    "_degraded": degraded,
                }
                if verdict == "infeasible" and final_alt:
                    patched["_method_swap"] = {
                        "from": algo_name or model_name, "to": final_alt,
                    }
                patched_models.append(patched)

                per_problem.append({
                    "sub_problem_id": sp_id,
                    "sub_problem_name": sp_name,
                    "model_name": model_name,
                    "algorithm": algo_name,
                    "verdict": verdict,
                    "score": feasibility_score,
                    "risks": all_risks,
                    "alternative_method": final_alt,
                    "library_matched": library_matched,
                    "degraded": degraded,
                })

                # claims_trace 追加每子问题裁决
                claims_trace.append({
                    "timestamp": datetime.now().isoformat(),
                    "node": "method_feasibility",
                    "sub_problem_id": sp_id,
                    "verdict": verdict,
                    "score": feasibility_score,
                    "library_matched": library_matched,
                    "alternative_method": final_alt,
                    "rationale": rationale,
                })

                # _quality_issues 写回（无则新增）
                if verdict in ("infeasible", "conditional"):
                    risk_msgs = [
                        r.get("message", str(r)) if isinstance(r, dict) else str(r)
                        for r in all_risks[:3]
                    ]
                    quality_issues.append({
                        "node": "method_feasibility",
                        "severity": "error" if verdict == "infeasible" else "warning",
                        "sub_problem_id": sp_id,
                        "category": "method_feasibility",
                        "message": (
                            f"[{sp_name}] 方法可行性={verdict}（score={feasibility_score}）："
                            + "; ".join(risk_msgs)
                        ),
                    })

            # ===== 汇总报告 =====
            n_feasible = sum(1 for p in per_problem if p["verdict"] == "feasible")
            n_conditional = sum(1 for p in per_problem if p["verdict"] == "conditional")
            n_infeasible = sum(1 for p in per_problem if p["verdict"] == "infeasible")

            report = {
                "task_id": task_id,
                "overall_feasible": overall_feasible,
                "per_problem": per_problem,
                "assessed_at": datetime.now().isoformat(),
                "summary": {
                    "n_feasible": n_feasible,
                    "n_conditional": n_conditional,
                    "n_infeasible": n_infeasible,
                    "spiral_conservative": spiral_conservative,
                },
            }

            # 写回 results：method_feasibility 报告 + patched modeler_agent
            ref_mf = self._set_result(state, "method_feasibility", report)
            patched_modeler_output = {
                **modeler_output, "sub_problem_models": patched_models,
            }
            ref_modeler = self._set_result(state, "modeler_agent", patched_modeler_output)

            # 黑板同步
            wm = self._get_working_memory(task_id)
            if wm:
                try:
                    wm.set_result("method_feasibility", report)
                    wm.set_result("modeler_agent", patched_modeler_output)
                except Exception as wm_exc:
                    logger.debug(
                        f"[LangGraph:{task_id}] method_feasibility 黑板同步失败: {wm_exc}"
                    )

            # 汇报用户
            self._post_chat(
                task_id, "coordinator",
                f"方法可行性预评估完成：可行 {n_feasible}，有条件 {n_conditional}，"
                f"不可行 {n_infeasible}"
                + ("（存在不可行方法，建议降级或更换）" if n_infeasible else ""),
            )

            logger.info(
                f"[LangGraph:{task_id}] method_feasibility done: "
                f"feasible={n_feasible} conditional={n_conditional} "
                f"infeasible={n_infeasible} overall={overall_feasible}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), **ref_mf, **ref_modeler},
                "method_feasibility_report": report,
                "claims_trace": claims_trace,
                "_quality_issues": quality_issues,
                "current_step": "method_feasibility_done",
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] method_feasibility 节点异常: {e}")
            return state

    async def _node_context_compression(self, state: TaskState) -> TaskState:
        """上下文压缩节点（图里显式触发的唯一入口，插在 figure → writer 之间）。

        范式与 _node_fact_check 复用 get_fact_checker().check()、_node_ast_audit 复用
        audit_and_patch() 一致：本节点只做图编排层薄封装——
        解析 __ref__（_resolve_results）→ 调 ContextCompressor.maybe_compress（原地压缩）
        → 把压缩后副本回写 result_store（_set_result）→ 防御性校验 protected 字段存活
        → 记录统计。不新写任何压缩算法。

        LLM caller 缺失时压缩器自动降级 L2 截断；累计 token 低于阈值时 level_used='none'、
        agents_compressed=[]，节点不写回不通知（幂等：压缩后结果回落到阈值以下，重复触发为空操作）。
        """
        task_id = state["task_id"]
        logger.info(
            f"[LangGraph:{task_id}] context_compression_node: start "
            f"(template={state.get('paper_template')}, workflow={state.get('workflow_type')})"
        )

        try:
            self._update_progress(task_id, state.get("problem_text", ""), 67, "上下文压缩中")

            # 1) 解析结果：把 __ref__ 还原成真实 agent 输出 dict
            #    注意 store.get 每次返回反序列化副本，故必须回写才让 writer/fact_check 看到
            results = self._resolve_results(state)

            # 2) 取压缩器单例 + token 估计器
            from ..core.context_compressor import get_compressor, estimate_tokens
            compressor = get_compressor()

            # 3) 选 LLM caller（用于 L1 摘要；缺失则压缩器自动降级 L2 截断，仍真实做事）
            #    优先 peer_review_agent / writer_agent，其次任一有 callable call_llm 的 agent
            llm_caller = None
            priority = ["peer_review_agent", "writer_agent"]
            ordered_names = priority + [n for n in self.agents if n not in priority]
            for name in ordered_names:
                agent_obj = self.agents.get(name)
                call = getattr(agent_obj, "call_llm", None) if agent_obj is not None else None
                if callable(call):
                    llm_caller = call
                    break

            # 4) 预快照：protected 字段 token（写回后存活校验，防压缩误删交付物）+ 总 token（不变量校验）
            protected_fields = ("latex_code", "numerical_results", "key_findings")
            pre_protected: Dict[str, Dict[str, int]] = {}  # agent_name -> {field: tokens}
            pre_tokens: Dict[str, int] = {}                # agent_name -> total tokens
            for name, out in results.items():
                if isinstance(out, dict):
                    pre_tokens[name] = estimate_tokens(out)
                    snap: Dict[str, int] = {}
                    for pf in protected_fields:
                        if pf in out:
                            snap[pf] = estimate_tokens(out[pf])
                    if snap:
                        pre_protected[name] = snap

            # 5) 执行压缩（原地修改 results 副本；返回 CompressionStats）
            #    丢弃 DROPPABLE_FIELDS(_contract/_raw_output/_fabrication_check 等)、截断超长
            #    字符串/大 list、对超大非 protected 字段做 LLM 摘要或 L2 硬截断；
            #    PROTECTED_FIELDS(latex_code/numerical_results/key_findings/...) 永不裁剪。
            #    _fabrication_flags/_fabrication_score 不在 DROPPABLE_FIELDS，故下游
            #    fact_check 的防编造检测不受影响。
            stats = compressor.maybe_compress(task_id, results, llm_caller=llm_caller)

            # 6) 写回结果存储（resolve 出来的是副本，必须回写 store）
            ref_update: Dict[str, Any] = {}
            written_back: List[str] = []
            seen: set = set()
            for entry in stats.agents_compressed:
                base = entry.split("(")[0]  # "writer_agent(L1)" -> "writer_agent"
                if base in seen:
                    continue
                seen.add(base)
                if base in results and isinstance(results[base], dict):
                    ref_update.update(self._set_result(state, base, results[base]))
                    written_back.append(base)

            # 7) 防御性校验：protected 字段存活（防压缩误删交付物）
            quality_issues: List[Dict[str, Any]] = []
            revoked: List[str] = []
            for agent_name in written_back:
                post_out = results.get(agent_name)
                if not isinstance(post_out, dict):
                    continue
                pre_fields = pre_protected.get(agent_name, {})
                bad = False
                for pf, pre_tok in pre_fields.items():
                    if pf not in post_out:
                        quality_issues.append({
                            "node": "context_compression_node",
                            "category": "protected_field_lost",
                            "agent": agent_name,
                            "field": pf,
                            "message": f"压缩误删 protected 字段 {pf}，已撤销该 agent 写回",
                        })
                        logger.error(
                            f"[LangGraph:{task_id}] context_compression: protected field "
                            f"{pf} lost for {agent_name}, revoking writeback"
                        )
                        bad = True
                        break
                    post_tok = estimate_tokens(post_out[pf])
                    if post_tok != pre_tok:
                        quality_issues.append({
                            "node": "context_compression_node",
                            "category": "protected_field_changed",
                            "agent": agent_name,
                            "field": pf,
                            "message": (
                                f"protected 字段 {pf} token 变化 {pre_tok}→{post_tok}，"
                                f"已撤销该 agent 写回"
                            ),
                        })
                        logger.error(
                            f"[LangGraph:{task_id}] context_compression: protected field "
                            f"{pf} token changed for {agent_name} "
                            f"({pre_tok}->{post_tok}), revoking writeback"
                        )
                        bad = True
                        break
                if bad:
                    revoked.append(agent_name)
            # 撤销被判定误删的 agent 写回（不污染交付物）
            for agent_name in revoked:
                ref_update.pop(agent_name, None)

            # 不变量校验
            if stats.saved_tokens < 0:
                quality_issues.append({
                    "node": "context_compression_node",
                    "category": "invariant_violation",
                    "message": f"saved_tokens={stats.saved_tokens} < 0",
                })
                logger.warning(
                    f"[LangGraph:{task_id}] context_compression: saved_tokens<0 ({stats.saved_tokens})"
                )
            if stats.compressed_tokens > stats.original_tokens:
                quality_issues.append({
                    "node": "context_compression_node",
                    "category": "invariant_violation",
                    "message": (
                        f"compressed_tokens={stats.compressed_tokens} > "
                        f"original_tokens={stats.original_tokens}"
                    ),
                })
                logger.warning(
                    f"[LangGraph:{task_id}] context_compression: compressed>original "
                    f"({stats.compressed_tokens}>{stats.original_tokens})"
                )

            # 8) 通知（仅当真正压缩了）
            if stats.saved_tokens > 0:
                self._post_chat(
                    task_id, "context_compressor",
                    f"🗜️ 上下文压缩：{stats.original_tokens}→{stats.compressed_tokens} tokens"
                    f"（level={stats.level_used}, {len(stats.agents_compressed)} agents）",
                )
                current_step = "context_compression_node"
            else:
                # 低于阈值 / 无可压缩内容：幂等跳过，不通知
                logger.info(
                    f"[LangGraph:{task_id}] context_compression: no compression needed "
                    f"(level={stats.level_used}, saved={stats.saved_tokens})"
                )
                current_step = "context_compression_skipped"

            # 9) 序列化统计
            stats_dict = {
                "original_tokens": stats.original_tokens,
                "compressed_tokens": stats.compressed_tokens,
                "saved_tokens": stats.saved_tokens,
                "level_used": stats.level_used,
                "agents_compressed": list(stats.agents_compressed),
                "ratio": stats.ratio(),
                "compressed_at": datetime.now().isoformat(),
            }

            # 校验问题写回 state 的 _quality_issues 列表（无则新增）
            quality_issues_full: List[Dict[str, Any]] = list(state.get("_quality_issues") or [])
            quality_issues_full.extend(quality_issues)

            logger.info(
                f"[LangGraph:{task_id}] context_compression: done "
                f"({stats.original_tokens}->{stats.compressed_tokens}, level={stats.level_used}, "
                f"agents={len(stats.agents_compressed)}, written_back={len(ref_update)}, "
                f"revoked={len(revoked)}, issues={len(quality_issues)})"
            )

            # 10) 返回
            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "context_compression_stats": stats_dict,
                "_quality_issues": quality_issues_full,
                "current_step": current_step,
            }
        except Exception as exc:
            logger.warning(
                f"[LangGraph:{task_id}] context_compression failed: {exc}", exc_info=True
            )
            return state

    @staticmethod
    def _audit_code_style(code_files: List[Dict[str, Any]]):
        """代码风格一致性审计（仅标准库 ast/tokenize/re，可复现不注水）。

        跨文件检查命名/导入顺序/docstring/引号/缩进/行尾，产出与 ast_audit 同构的
        AuditResult（issues 为 AuditIssue 列表），并对每个文件做不会改变语义的安全
        归一化（strip 行尾空白 + 单尾换行 + CRLF→LF）。命名/导入重排仅报告不自动改写。

        Returns:
            (AuditResult, patched_files): 审计结果 + 归一化后的 code_files（同序）。
        """
        import ast
        import io
        import re as _re
        import tokenize
        from ..core.code_audit import AuditResult, AuditIssue

        def _classify(name: str):
            # PascalCase：首字母大写且含小写字母（排除全大写常量）
            if _re.match(r'^[A-Z][A-Za-z0-9]*$', name) and any(c.islower() for c in name):
                return 'PascalCase'
            if _re.match(r'^[a-z][a-z0-9_]*$', name):
                return 'snake_case'
            if _re.match(r'^[a-z][A-Za-z0-9]*$', name) and any(c.isupper() for c in name):
                return 'camelCase'
            return None  # 全大写常量等不纳入多数派统计

        def _norm(code: str) -> str:
            code = code.replace('\r\n', '\n').replace('\r', '\n')
            code = '\n'.join(ln.rstrip() for ln in code.split('\n'))
            return code.rstrip('\n') + '\n'

        issues = []
        all_names = []       # (filename, name, cls, line) 用于全局多数派
        file_names = []      # idx -> [(name, cls, line)]
        file_quotes = []     # idx -> (single, double)
        trees = []           # idx -> tree or None

        # ===== 第一遍：AST 解析 + 收集命名分类 + 引号计数 =====
        for idx, cf in enumerate(code_files):
            code = cf.get("code", "") if isinstance(cf, dict) else ""
            filename = (cf.get("filename") if isinstance(cf, dict) else None) or f"file_{idx}"
            if not isinstance(code, str) or not code.strip():
                file_names.append([]); file_quotes.append((0, 0)); trees.append(None); continue
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                issues.append(AuditIssue(
                    line=getattr(e, 'lineno', 0) or 0, severity="error", category="style_syntax",
                    message=f"[{filename}] 语法错误，无法做风格审计: {e.msg}",
                    suggestion="修复语法错误后重试",
                ))
                file_names.append([]); file_quotes.append((0, 0)); trees.append(None); continue

            trees.append(tree)
            names_here = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    cls = _classify(node.name)
                    if cls:
                        all_names.append((filename, node.name, cls, node.lineno))
                        names_here.append((node.name, cls, node.lineno))
                elif isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            cls = _classify(tgt.id)
                            if cls:
                                all_names.append((filename, tgt.id, cls, tgt.lineno))
                                names_here.append((tgt.id, cls, tgt.lineno))
            file_names.append(names_here)

            single = double = 0
            try:
                for tok in tokenize.generate_tokens(io.StringIO(code).readline):
                    if tok.type == tokenize.STRING:
                        core = tok.string[_re.match(r'^[rbfuRBFU]*', tok.string).end():]
                        if core.startswith("'"):
                            single += 1
                        elif core.startswith('"'):
                            double += 1
            except (tokenize.TokenError, IndentationError, SyntaxError):
                pass
            file_quotes.append((single, double))

        # ===== 全局多数派：命名风格 + 引号风格 =====
        style_counter = {'snake_case': 0, 'camelCase': 0, 'PascalCase': 0}
        for _, _, cls, _ in all_names:
            style_counter[cls] = style_counter.get(cls, 0) + 1
        majority_style = max(style_counter, key=style_counter.get) if sum(style_counter.values()) > 0 else None
        total_single = sum(q[0] for q in file_quotes)
        total_double = sum(q[1] for q in file_quotes)
        majority_quote = ("single" if total_single >= total_double else "double") if (total_single + total_double) > 0 else None

        # ===== 第二遍：逐文件生成 issues =====
        for idx, cf in enumerate(code_files):
            tree = trees[idx]
            if tree is None:
                continue
            code = cf.get("code", "") if isinstance(cf, dict) else ""
            filename = (cf.get("filename") if isinstance(cf, dict) else None) or f"file_{idx}"

            # 1. 命名一致性（偏离全局多数派 → error）
            if majority_style:
                dev = [(n, c, ln) for (n, c, ln) in file_names[idx] if c != majority_style]
                if dev:
                    sample = ", ".join(n for n, _, _ in dev[:3])
                    issues.append(AuditIssue(
                        line=dev[0][2], severity="error", category="style_naming",
                        message=f"[{filename}] 命名偏离全局多数派({majority_style})：{sample}{' 等' if len(dev) > 3 else ''}",
                        suggestion=f"统一为 {majority_style} 命名风格（仅报告，不自动改写）",
                    ))

            # 2. 导入顺序（E402 + 组内字母序 → warning）
            imports = []
            first_code = None
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports.append(node)
                    continue
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    continue  # 模块 docstring
                if isinstance(node, ast.If):
                    continue  # if __name__ == "__main__" 块
                if first_code is None:
                    first_code = node.lineno
            if first_code is not None:
                late = [i for i in imports if i.lineno > first_code]
                if late:
                    issues.append(AuditIssue(
                        line=late[0].lineno, severity="warning", category="style_import_order",
                        message=f"[{filename}] 导入出现在代码之后（PEP8 E402 类）",
                        suggestion="将所有 import 移到文件顶部（模块 docstring 之后）",
                    ))
            preamble = [i for i in imports if first_code is None or i.lineno < first_code]
            seq = []
            for i in preamble:
                if isinstance(i, ast.Import):
                    for a in i.names:
                        seq.append(a.name.lower())
                else:
                    mod = i.module or ''
                    for a in i.names:
                        seq.append((mod + '.' + a.name if mod else a.name).lower())
            if seq and seq != sorted(seq):
                issues.append(AuditIssue(
                    line=preamble[0].lineno, severity="warning", category="style_import_order",
                    message=f"[{filename}] 导入未按字母序排列",
                    suggestion="按字母序排列 import 语句（仅报告，不自动改写）",
                ))

            # 3. 文档字符串（公开符号缺失 → warning）
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith('_'):
                    if not ast.get_docstring(node):
                        kind = '类' if isinstance(node, ast.ClassDef) else '函数'
                        issues.append(AuditIssue(
                            line=node.lineno, severity="warning", category="style_docstring",
                            message=f"[{filename}] 公开{kind} '{node.name}' 缺少 docstring",
                            suggestion="为公开符号添加文档字符串",
                        ))

            # 4. 引号风格一致性（偏离全局多数派 → warning）
            if majority_quote:
                s, d = file_quotes[idx]
                if s + d > 0:
                    dom = "single" if s >= d else "double"
                    if dom != majority_quote:
                        issues.append(AuditIssue(
                            line=1, severity="warning", category="style_quotes",
                            message=f"[{filename}] 引号风格偏离全局多数派({majority_quote})：单 {s} / 双 {d}",
                            suggestion=f"统一为 {'单' if majority_quote == 'single' else '双'}引号（仅报告，不自动改写）",
                        ))

            # 5. 缩进一致性（tab/space 混用或单位不一 → error）
            has_tab = has_space = False
            widths = set()
            for line in code.splitlines():
                leading = line[:len(line) - len(line.lstrip(' \t'))]
                if '\t' in leading:
                    has_tab = True
                sp = leading.count(' ')
                if sp:
                    has_space = True
                    widths.add(sp)
            indent_bad = False
            if has_tab and has_space:
                indent_bad = True
            elif has_space and not has_tab:
                pos = sorted(w for w in widths if w > 0)
                if pos:
                    base = pos[0]
                    if any(w % base != 0 for w in pos):
                        indent_bad = True
            if indent_bad:
                issues.append(AuditIssue(
                    line=1, severity="error", category="style_indent",
                    message=f"[{filename}] 缩进不一致（tab/space 混用或缩进单位不统一）",
                    suggestion="统一使用 4 空格缩进，禁止 tab/space 混用",
                ))

            # 6. 行尾空白/缺尾换行/CRLF（→ warning）
            flags = []
            if '\r\n' in code or '\r' in code:
                flags.append("CRLF 行尾")
            for line in code.splitlines(keepends=False):
                if line != line.rstrip():
                    flags.append("行尾空白")
                    break
            if code and not code.endswith('\n'):
                flags.append("缺尾换行")
            if flags:
                issues.append(AuditIssue(
                    line=1, severity="warning", category="style_lineend",
                    message=f"[{filename}] 行尾问题：{'、'.join(flags)}",
                    suggestion="strip 行尾空白 + 单尾换行 + CRLF→LF（已自动归一化）",
                ))

        # ===== 计分（与 audit_code 一致：error×15 + warning×5） =====
        err = sum(1 for i in issues if i.severity == "error")
        warn = sum(1 for i in issues if i.severity == "warning")
        score = max(0, 100 - err * 15 - warn * 5)
        passed = err == 0
        parts = []
        if err:
            parts.append(f"{err}个严重问题")
        if warn:
            parts.append(f"{warn}个警告")
        summary = "通过" if not parts else f"发现{', '.join(parts)}"
        result = AuditResult(passed=passed, issues=issues, score=score, summary=summary)

        # ===== 安全归一化 patch（仅语义无关变换；命名/导入重排不自动改写） =====
        patched_files = []
        for cf in code_files:
            if isinstance(cf, dict):
                code = cf.get("code", "")
                if isinstance(code, str) and code:
                    patched_files.append({**cf, "code": _norm(code), "description": f"风格归一化后(score={score})"})
                else:
                    patched_files.append(cf)
            else:
                patched_files.append(cf)
        return result, patched_files

    async def _node_code_style_check(self, state: TaskState) -> TaskState:
        """代码风格一致性检查节点（mid 阶段，缺陷：代码风格不一致）。

        镜像 _node_ast_audit 的结构与 _set_result 回写约定：按 paper_template 分支解析
        coder_agent / solver_agent 的【全部】code_files（风格一致性是跨文件问题），用标准库
        ast/tokenize/re 做可复现审计（不引入外部 linter），安全归一化后回写，设置
        code_style_passed 标志，并将校验问题写回 state._quality_issues。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] code_style_check: 开始代码风格一致性检查")

        try:
            results = self._resolve_results(state)
            template = state.get("paper_template", "math_modeling")
            ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}

            # 按模板分支解析代码来源（收集全部 code_files，非仅第 0 个）
            if template in ccf_a:
                source_output = results.get("coder_agent", {})
                source_key = "coder_agent"
                code_files = list(source_output.get("code_files", [])) if isinstance(source_output, dict) else []
            else:
                source_output = results.get("solver_agent", {})
                source_key = "solver_agent"
                code_files = []
                solutions = source_output.get("sub_problem_solutions", []) if isinstance(source_output, dict) else []
                for sol in solutions:
                    sol_code_files = sol.get("code_files", []) if isinstance(sol, dict) else []
                    code_files.extend(sol_code_files)

            if not code_files:
                logger.info(f"[LangGraph:{task_id}] code_style_check: 无代码文件，跳过")
                return {**state, "code_style_passed": False, "current_step": "code_style_check_skipped"}

            self._update_progress(task_id, state["problem_text"], 55, "代码风格一致性检查中")

            # 真实校验 + 安全归一化
            audit_result, patched_files = self._audit_code_style(code_files)
            normalized = any(
                isinstance(pcf, dict) and isinstance(ocf, dict) and pcf.get("code") != ocf.get("code")
                for pcf, ocf in zip(patched_files, code_files)
            )
            issue_dicts = [
                {"line": i.line, "severity": i.severity, "category": i.category,
                 "message": i.message, "suggestion": i.suggestion}
                for i in audit_result.issues
            ]

            # 回写：镜像 _node_ast_audit 的 results 回写范式
            if template in ccf_a:
                updated_output = {
                    **source_output,
                    "code_files": patched_files,
                    "code_style_audit": {
                        "passed": audit_result.passed,
                        "score": audit_result.score,
                        "issues": issue_dicts,
                        "summary": audit_result.summary,
                        "normalized": normalized,
                    },
                }
                ref_update = self._set_result(state, source_key, updated_output)
            else:
                # 非 CCF-A：按原顺序把 patched_files 写回各 sub_problem_solutions 的 code_files
                updated_solutions = []
                ptr = 0
                for sol in source_output.get("sub_problem_solutions", []) if isinstance(source_output, dict) else []:
                    sol_cf = sol.get("code_files", []) if isinstance(sol, dict) else []
                    if not sol_cf:
                        updated_solutions.append(sol)
                        continue
                    n = len(sol_cf)
                    new_cf = patched_files[ptr:ptr + n]
                    if len(new_cf) != n:  # 数量不一致则保留原文件（防御）
                        new_cf = sol_cf
                    ptr += n
                    updated_solutions.append({**sol, "code_files": new_cf})
                updated_output = {
                    **source_output,
                    "sub_problem_solutions": updated_solutions,
                    "code_style_audit": {
                        "passed": audit_result.passed,
                        "score": audit_result.score,
                        "issues": issue_dicts,
                        "summary": audit_result.summary,
                        "normalized": normalized,
                    },
                }
                ref_update = self._set_result(state, source_key, updated_output)

            # 校验问题写回 state._quality_issues（无则新增）
            quality_issues = list(state.get("_quality_issues", []))
            for iss in audit_result.issues:
                quality_issues.append({
                    "stage": "code_style_check",
                    "severity": iss.severity,
                    "category": iss.category,
                    "line": iss.line,
                    "message": iss.message,
                    "suggestion": iss.suggestion,
                    "task_id": task_id,
                })

            # 通知
            if audit_result.passed:
                self._post_chat(task_id, "code_style_agent", f"代码风格检查通过（score={audit_result.score}）")
            else:
                self._post_chat(task_id, "code_style_agent", f"代码风格检查未通过（score={audit_result.score}）：{audit_result.summary}")

            logger.info(
                f"[LangGraph:{task_id}] code_style_check: passed={audit_result.passed} "
                f"score={audit_result.score} issues={len(audit_result.issues)} normalized={normalized}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "code_style_passed": audit_result.passed,
                "_quality_issues": quality_issues,
                "current_step": "code_style_check_done",
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] code_style_check 失败: {e}", exc_info=True)
            return state

    async def _node_reproducibility_check(self, state: TaskState) -> TaskState:
        """方法可复现性审查（补全"审查核心缺失"，对所有模板通用）。

        前置 _node_fact_check 已物化 final/main.tex + final/solves.json 并产出
        fact_checker 报告，本节点直接消费，补上 CCF-A 之外原本缺失的审查核心。
        5 项检查全部基于现有确定性工具/正则，非空壳：
        1. 代码审计复检（core/code_audit.audit_code）拦截硬编码指标——数值无法由运行代码复现
        2. 随机种子可复现性（正则判定 seed 设置）
        3. 论文声称方法↔代码实现匹配（writer paper_memory.model_names vs 代码）
        4. 声明↔日志追溯表（services/claims_traceability，填充 state.claims_trace）
        5. 一键复现 Bundle（core/reproducibility_bundle，此前仅 CCF-A 调用，本节点对所有模板生效）
        """
        task_id = state["task_id"]
        project_name = state.get("project_name")
        template = state.get("paper_template", "math_modeling")
        try:
            output_dir = get_project_output_dir(project_name)
        except Exception:
            output_dir = None

        self._update_progress(task_id, state["problem_text"], 88, "方法可复现性审查中")
        logger.info(f"[LangGraph:{task_id}] reproducibility_check: 开始方法可复现性审查 (template={template})")

        try:
            results = self._resolve_results(state)
            writer_output = results.get("writer_agent") or {}
            solver_output = results.get("solver_agent") or {}
            experiment_output = results.get("experimentation_agent") or {}
            fact_report = results.get("fact_checker") or {}

            paper_memory = writer_output.get("paper_memory", {}) if isinstance(writer_output, dict) else {}
            key_claims = paper_memory.get("key_claims", []) if isinstance(paper_memory, dict) else []
            model_names = paper_memory.get("model_names", []) if isinstance(paper_memory, dict) else []
            sub_solutions = solver_output.get("sub_problem_solutions", []) if isinstance(solver_output, dict) else []

            report: Dict[str, Any] = {"enabled": True, "passed": True, "issues": [], "checks": []}
            issues: List[str] = report["issues"]
            severe_count = 0  # 严重问题计数（不一致/不可复现/硬编码/无证据/无代码）

            # ===== 取最终代码（与 ast_audit 节点同款取法）=====
            ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}
            final_code = ""
            if template in ccf_a:
                coder_output = results.get("coder_agent") or {}
                code_files = coder_output.get("code_files", []) if isinstance(coder_output, dict) else []
                if code_files:
                    final_code = code_files[0].get("code", "") or ""
            if not final_code:
                for sol in sub_solutions:
                    sol_code_files = sol.get("code_files", []) if isinstance(sol, dict) else []
                    if sol_code_files:
                        final_code = "\n\n".join(
                            cf.get("code", "") for cf in sol_code_files if isinstance(cf, dict)
                        )
                        break
            if not final_code and isinstance(experiment_output, dict):
                exp_code_files = experiment_output.get("code_files", []) or []
                if exp_code_files:
                    final_code = exp_code_files[0].get("code", "") or ""

            # ===== 审查核心-1: 代码审计复检（拦截硬编码指标）=====
            audit_check: Dict[str, Any] = {"name": "code_audit", "passed": True, "score": 100, "summary": ""}
            if not final_code:
                issues.append("无可复现代码")
                report["passed"] = False
                severe_count += 1
                audit_check.update(passed=False, score=0, summary="无可复现代码")
            else:
                try:
                    from ..core.code_audit import audit_code
                    audit_result = audit_code(final_code, task_type="general")
                    hardcoded = [
                        i for i in audit_result.issues
                        if getattr(i, "category", "") == "hardcoded_metric"
                    ]
                    audit_check.update(
                        passed=audit_result.passed and not hardcoded,
                        score=audit_result.score,
                        summary=audit_result.summary,
                        hardcoded_count=len(hardcoded),
                    )
                    if hardcoded:
                        report["passed"] = False
                        for hi in hardcoded:
                            issues.append(f"运行代码无法复现该数值: {getattr(hi, 'message', str(hi))}")
                            severe_count += 1
                except Exception as e:
                    logger.warning(f"[LangGraph:{task_id}] reproducibility_check code_audit failed: {e}")
                    audit_check.update(passed=False, score=0, summary=f"代码审计异常: {e}")
            report["checks"].append(audit_check)

            # ===== 审查核心-2: 随机种子可复现性 =====
            seed_set = bool(re.search(
                r"(?:np\.random\.seed|random\.seed|torch\.manual_seed|tf\.random\.set_seed)\s*\(",
                final_code,
            ))
            training_keywords = ("fit(", "train(", "epoch", "backward", "optimizer.step", "loss.backward")
            has_training = any(kw in final_code for kw in training_keywords)
            seed_check: Dict[str, Any] = {
                "name": "random_seed", "passed": True, "seed_set": seed_set, "has_training": has_training,
            }
            if has_training and not seed_set:
                issues.append("训练代码未设置随机种子，结果不可复现")
                report["passed"] = False
                seed_check["passed"] = False
                severe_count += 1
            report["checks"].append(seed_check)

            # ===== 审查核心-3: 方法↔代码一致性 =====
            described_methods = [m for m in model_names if isinstance(m, str) and len(m) >= 3]
            # 从 modeling agent (proposed_method.algorithm) 提取算法名做同样匹配
            modeling_output = results.get("algorithm_engineer_agent") or results.get("modeler_agent") or {}
            if isinstance(modeling_output, dict):
                proposed = modeling_output.get("proposed_method")
                if isinstance(proposed, dict):
                    alg = proposed.get("algorithm")
                    if isinstance(alg, dict):
                        an = alg.get("name", "")
                        if isinstance(an, str) and len(an) >= 3:
                            described_methods.append(an)
                    elif isinstance(alg, str) and len(alg) >= 3:
                        described_methods.append(alg)
                    pm_name = proposed.get("name", "")
                    if isinstance(pm_name, str) and len(pm_name) >= 3:
                        described_methods.append(pm_name)
                for m in modeling_output.get("sub_problem_models", []) or []:
                    if not isinstance(m, dict):
                        continue
                    a = m.get("algorithm")
                    if isinstance(a, dict):
                        an = a.get("name", "")
                        if isinstance(an, str) and len(an) >= 3:
                            described_methods.append(an)
                    mn = m.get("model_name", "")
                    if isinstance(mn, str) and len(mn) >= 3:
                        described_methods.append(mn)

            orphan: List[str] = []
            if described_methods and final_code:
                code_lower = final_code.lower()
                for m in described_methods:
                    ml = m.lower()
                    if ml not in code_lower and ml.replace(" ", "") not in code_lower:
                        orphan.append(m)
            method_check: Dict[str, Any] = {
                "name": "method_code_consistency",
                "passed": len(orphan) == 0,
                "described_methods": list(dict.fromkeys(described_methods))[:10],
                "orphan_methods": orphan[:5],
            }
            if orphan:
                # warning：记入 checks 提示人工，不直接 fail report
                issues.append("论文声称的方法在代码中无实现: " + ", ".join(orphan[:5]))
            report["checks"].append(method_check)

            # ===== 审查核心-4: 声明↔日志追溯表 =====
            trace_rows_dict: List[Dict[str, Any]] = list(state.get("claims_trace", []) or [])
            try:
                from ..services.claims_traceability import (
                    build_claims_traceability, save_claims_traceability,
                )
                fact_issues = fact_report.get("issues", []) or []
                provenance: List[Dict[str, Any]] = []
                for sol in sub_solutions:
                    if not isinstance(sol, dict):
                        continue
                    for cf in (sol.get("code_files") or []):
                        if isinstance(cf, dict):
                            provenance.append({"code_path": cf.get("path", "")})
                if isinstance(experiment_output, dict):
                    for cf in (experiment_output.get("code_files") or []):
                        if isinstance(cf, dict):
                            provenance.append({"code_path": cf.get("path", "")})
                trace = build_claims_traceability(
                    task_id,
                    key_claims=key_claims,
                    solve_results=sub_solutions,
                    experiment_output=experiment_output if isinstance(experiment_output, dict) else {},
                    provenance_records=provenance,
                    fact_check_issues=fact_issues,
                )
                trace_rows_dict = [r.to_dict() for r in trace.rows]
                trace_summary = dict(trace.summary) if isinstance(trace.summary, dict) else {}
                report["claims_traceability"] = trace_summary

                mismatch = trace_summary.get("mismatch", 0)
                missing_evidence = trace_summary.get("missing_evidence", 0)
                coverage = trace_summary.get("coverage", 0.0)
                if isinstance(mismatch, (int, float)) and mismatch > 0:
                    issues.append(f"{mismatch} 处声明↔日志数值不一致")
                    report["passed"] = False
                    severe_count += 1
                if (isinstance(coverage, (int, float)) and coverage < 0.5
                        and isinstance(missing_evidence, (int, float)) and missing_evidence > 0):
                    issues.append(f"声明追溯覆盖率{coverage:.0%}，{missing_evidence} 处无证据")
                    severe_count += 1

                if output_dir:
                    save_claims_traceability(trace, output_dir / "final")
            except Exception as e:
                logger.warning(f"[LangGraph:{task_id}] reproducibility_check claims_traceability failed: {e}")
                report["claims_traceability"] = {"error": str(e)}

            # ===== 审查核心-5: 一键复现 Bundle（对所有模板生效）=====
            try:
                from ..core.reproducibility_bundle import get_reproducibility_bundle
                experiment_result = experiment_output.get("experiment_result", {}) if isinstance(experiment_output, dict) else {}
                if not isinstance(experiment_result, dict):
                    experiment_result = {}
                bundle_payload = {
                    "dataset_info": experiment_result.get("dataset_info", {}) or {},
                    "aggregated": experiment_result.get("metrics") or experiment_result.get("aggregated"),
                    "raw_batch": experiment_result.get("raw_batch"),
                }
                bundle = get_reproducibility_bundle().create_bundle(
                    bundle_payload, task_id, project_name,
                )
                report["reproducibility_bundle"] = {
                    "bundle_id": bundle.get("bundle_id"),
                    "bundle_path": bundle.get("bundle_path"),
                    "env_lock": bool(bundle.get("env_lock")),
                    "data_hash": bool(bundle.get("data_hash")),
                    "reproduction_steps": len(bundle.get("reproduction_steps", []) or []),
                    "error": bundle.get("error"),
                }
                if bundle.get("error"):
                    issues.append(f"复现bundle生成失败:{bundle.get('error')}")
            except Exception as e:
                logger.warning(f"[LangGraph:{task_id}] reproducibility_check bundle failed: {e}")
                report["reproducibility_bundle"] = {"error": str(e)}
                issues.append(f"复现bundle生成失败:{e}")

            # ===== 收尾 =====
            report["checked_at"] = datetime.now().isoformat()
            other_count = max(0, len(issues) - severe_count)
            report["score"] = max(0, 100 - 20 * severe_count - 5 * other_count)

            # 持久化报告
            if output_dir and issues:
                try:
                    report_path = output_dir / "final" / "reproducibility_report.json"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                    logger.info(f"[LangGraph:{task_id}] reproducibility_check report saved to {report_path}")
                except Exception as disk_exc:
                    logger.warning(f"[LangGraph:{task_id}] reproducibility_check report save failed: {disk_exc}")

            # 通知用户
            emoji = "✅" if report["passed"] else "⚠️"
            self._post_chat(
                task_id, "reproducibility_check",
                f"{emoji} 方法可复现性审查：发现{len(issues)}个问题，复现bundle已生成"
                f"（score={report['score']}，passed={report['passed']}）"
                + ("\n" + "\n".join(f"  - {s}" for s in issues[:5]) if issues else ""),
            )

            # 外部 store 持久化
            ref_update = self._set_result(state, "reproducibility_check", report)

            # 校验问题写回 state 的 _quality_issues 列表（无则新增）
            quality_issues = list(state.get("_quality_issues", []) or [])
            for iss in issues:
                entry = f"[reproducibility_check] {iss}"
                if entry not in quality_issues:
                    quality_issues.append(entry)

            logger.info(
                f"[LangGraph:{task_id}] reproducibility_check done: passed={report['passed']} "
                f"score={report['score']} issues={len(issues)} severe={severe_count} "
                f"bundle={'ok' if report.get('reproducibility_bundle', {}).get('bundle_id') else 'n/a'}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "claims_trace": trace_rows_dict,
                "current_step": "reproducibility_check_done",
                "_quality_issues": quality_issues,
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] reproducibility_check 失败: {e}", exc_info=True)
            return {**state, "current_step": "reproducibility_check_failed"}

    async def _node_formula_validity_check(self, state: TaskState) -> TaskState:
        """post 阶段：LaTeX 公式有效性校验（report-only，不改写论文）。

        复用 services/formula_validator.FormulaValidator 对 writer 产出的 latex_code 做确定性
        数学段校验（环境配对 / 定界符平衡 / 退化公式 / 错位对齐符，可选编译验证），结果落盘
        final/formula_validity_report.json、回写 state._quality_issues，并写入外部结果 store。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] formula_validity_check: start")

        # guard（defensive getattr：兼容 LangGraphConfig 未显式声明字段的情况）
        if not getattr(self.cfg, "enable_formula_validity_check", True):
            logger.info(f"[LangGraph:{task_id}] formula_validity_check: disabled by config, skip")
            return {**state, "current_step": "formula_validity_skipped"}

        try:
            # 1. 取 writer 产出的 latex_code（dict 校验）
            results = self._resolve_results(state)
            writer_output = results.get("writer_agent") or {}
            if not isinstance(writer_output, dict):
                writer_output = {}
            latex_code = writer_output.get("latex_code", "") or ""
            if not latex_code.strip():
                logger.info(f"[LangGraph:{task_id}] formula_validity_check: no latex_code, skip")
                return {**state, "current_step": "formula_validity_skipped"}

            # 2. 进度
            self._update_progress(task_id, state["problem_text"], 85, "LaTeX 公式有效性校验中")

            # 3. 校验（复用 AuditReport/AuditFinding 容器与打分：error -15 / warning -5）
            from ..services.formula_validator import get_formula_validator
            compile_check = bool(getattr(self.cfg, "formula_compile_check", False))
            report = get_formula_validator().validate(latex_code, compile_check=compile_check)

            findings = [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "message": f.message,
                    "location": f.location,
                    "expected": f.expected,
                    "actual": f.actual,
                }
                for f in report.findings
            ]
            seg_count = int(getattr(report, "segment_count", 0))
            error_count = sum(1 for f in findings if f["severity"] == "error")
            warning_count = sum(1 for f in findings if f["severity"] == "warning")
            report_dict: Dict[str, Any] = {
                "enabled": True,
                "passed": bool(report.passed),
                "score": max(0.0, float(report.score)),
                "segment_count": seg_count,
                "error_count": error_count,
                "warning_count": warning_count,
                "findings": findings,
            }

            # 4. 落盘（与 fact_check 一致：异常仅 warn，不阻断）
            saved_path = "final/formula_validity_report.json"
            try:
                output_dir = get_project_output_dir(state.get("project_name"))
                report_path = output_dir / "final" / "formula_validity_report.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(report_dict, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                saved_path = str(report_path.relative_to(output_dir))
                logger.info(f"[LangGraph:{task_id}] formula_validity_check: report saved to {report_path}")
            except Exception as disk_exc:
                logger.warning(f"[LangGraph:{task_id}] formula_validity_check report save failed: {disk_exc}")

            # 5. 写回外部结果 store（ref 引用）
            ref_update = self._set_result(state, "formula_validity", report_dict)

            # 6. 通知（passed / failed 两态）
            if report.passed:
                self._post_chat(
                    task_id, "coordinator",
                    f"✅ LaTeX 公式有效性校验通过（score={report_dict['score']:.0f}，{seg_count} 个公式段）",
                )
            else:
                top3 = "; ".join(
                    f"[{f['location']}] {f['message']}" for f in findings[:3]
                )
                self._post_chat(
                    task_id, "coordinator",
                    f"⚠️ 公式校验发现 {error_count} 错误/{warning_count} 警告："
                    f"{top3} 报告已存 {saved_path}",
                )

            # 7. 写回 state._quality_issues（无则新增，保留已有项）
            quality_issues = list(state.get("_quality_issues") or [])
            for f in findings:
                quality_issues.append({
                    "source": "formula_validity_check",
                    "severity": f["severity"],
                    "category": f["category"],
                    "location": f["location"],
                    "message": f["message"],
                })

            logger.info(
                f"[LangGraph:{task_id}] formula_validity_check: passed={report.passed} "
                f"score={report_dict['score']:.0f} errors={error_count} warnings={warning_count} "
                f"segments={seg_count}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "formula_validity_passed": bool(report.passed),
                "_quality_issues": quality_issues,
                "current_step": "formula_validity_check",
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] formula_validity_check 失败: {e}")
            return state


    async def _node_table_consistency_check(self, state: TaskState) -> TaskState:
        """Post 阶段：表格内部一致性校验（报告型节点，镜像 _node_fact_check）。

        解析 writer 产物 final/main.tex 中的所有 tabular 环境，校验：
        (a) 列数一致性；(b) 数值列识别；(c) 合计/总计行求和（复用 symbolic_auditor.check_table_sums）
        与平均行内联均值校验；(d) 百分比列（复用 check_percentages）；(e) 重复行。
        只校验 + 落盘 + 通知，不重写 LaTeX。问题写回 state["_quality_issues"]。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] table_consistency_check 开始")
        try:
            # 1. 取参
            project_name = state.get("project_name")
            template = state.get("paper_template", "math_modeling")
            results = self._resolve_results(state)
            writer_output = results.get("writer_agent") or {}
            latex_code = (
                writer_output.get("latex_code", "")
                if isinstance(writer_output, dict)
                else ""
            )

            # 2. 早退：无 latex_code
            if not latex_code:
                report = {
                    "enabled": True,
                    "passed": True,
                    "skipped": "no latex_code",
                    "tables_checked": 0,
                    "issues": [],
                }
                self._set_result(state, "table_consistency_checker", report)
                logger.info(f"[LangGraph:{task_id}] table_consistency: 无 latex_code，跳过")
                return {
                    **state,
                    "results": {**state.get("results", {}), "table_consistency_checker": report},
                    "current_step": "table_consistency_check_skipped",
                }

            # 3. 进度
            self._update_progress(task_id, state["problem_text"], 82, "表格内部一致性校验中")

            # 复用设计指定的工具
            from dataclasses import asdict
            from ..services.symbolic_auditor import (
                AuditFinding,
                check_table_sums,
                check_percentages,
            )

            # 4. 解析所有 tabular 环境
            tables = self._extract_latex_tables(latex_code)
            logger.info(f"[LangGraph:{task_id}] table_consistency: 解析到 {len(tables)} 张表")

            # 5. 逐表校验
            findings: List[AuditFinding] = []
            for table in tables:
                location = table["location"]
                n_cols = table["n_cols"]
                rows = table["rows"]
                if not rows:
                    continue

                # (a) 列数一致性（必查）
                if n_cols > 0:
                    for r_idx, row in enumerate(rows):
                        if len(row) != n_cols:
                            findings.append(AuditFinding(
                                severity="error",
                                category="column_mismatch",
                                message=f"第 {r_idx + 1} 行单元格数 {len(row)} 与列规格 {n_cols} 不一致",
                                location=f"{location}:row{r_idx + 1}",
                            ))
                else:
                    # 列规格无法解析，跳过该表后续结构化校验
                    continue

                headers = rows[0]
                # 建立列数据（按列收集单元格文本，与 rows 对齐）
                col_cells: List[List[str]] = [[] for _ in range(n_cols)]
                for row in rows:
                    for j in range(min(len(row), n_cols)):
                        col_cells[j].append(row[j])

                # 唯一列名（表头文本，回退 col{j}）
                col_keys: Dict[int, str] = {}
                used_keys: set = set()
                for j in range(n_cols):
                    base = (
                        headers[j].strip()
                        if j < len(headers) and headers[j].strip()
                        else f"col{j + 1}"
                    )
                    key = base
                    k = 1
                    while key in used_keys:
                        key = f"{base}_{k}"
                        k += 1
                    used_keys.add(key)
                    col_keys[j] = key

                # (b) 数值列识别：body（去表头）多数单元格可解析为 float
                numeric_parsed: Dict[int, List[Optional[float]]] = {}
                for j in range(n_cols):
                    cells = col_cells[j]
                    parsed = [self._try_parse_float(c) for c in cells]
                    body = parsed[1:] if len(parsed) > 1 else parsed
                    if body and sum(1 for v in body if v is not None) >= max(1, len(body) // 2):
                        numeric_parsed[j] = parsed

                # 识别合计/平均行（首格匹配关键词）
                total_row_idx = None
                avg_row_idx = None
                for r_idx, row in enumerate(rows):
                    first = row[0].strip() if row else ""
                    if re.search(r"合计|总计|Total|Sum", first, re.IGNORECASE):
                        total_row_idx = r_idx
                    elif re.search(r"平均|Average|Mean", first, re.IGNORECASE):
                        avg_row_idx = r_idx

                # (c) 合计/总计行求和（仅在有总计行时调用，避免误判最后一行为合计）
                if total_row_idx is not None and total_row_idx != 0:
                    sum_data: Dict[str, List[float]] = {}
                    for j, parsed in numeric_parsed.items():
                        values: List[float] = []
                        for r_idx in range(len(rows)):
                            if r_idx == total_row_idx or r_idx == avg_row_idx:
                                continue
                            v = parsed[r_idx] if r_idx < len(parsed) else None
                            if v is not None:
                                values.append(v)
                        total_v = parsed[total_row_idx] if total_row_idx < len(parsed) else None
                        if total_v is not None:
                            values.append(total_v)
                        if len(values) >= 2:
                            sum_data[col_keys[j]] = values
                    if sum_data:
                        for f in check_table_sums(sum_data):
                            f.location = f"{location}:{f.location}"
                            findings.append(f)

                    # 平均行内联均值校验（symbolic_auditor 无均值规则，自行容差判定）
                    if avg_row_idx is not None and avg_row_idx != 0:
                        for j, parsed in numeric_parsed.items():
                            body_vals: List[float] = []
                            for r_idx in range(len(rows)):
                                if r_idx == 0 or r_idx == avg_row_idx or r_idx == total_row_idx:
                                    continue
                                v = parsed[r_idx] if r_idx < len(parsed) else None
                                if v is not None:
                                    body_vals.append(v)
                            avg_cell = parsed[avg_row_idx] if avg_row_idx < len(parsed) else None
                            if body_vals and avg_cell is not None:
                                expected_mean = sum(body_vals) / len(body_vals)
                                tol = max(0.01, abs(expected_mean) * 0.01)
                                if abs(expected_mean - avg_cell) > tol:
                                    findings.append(AuditFinding(
                                        severity="warning",
                                        category="sum_mismatch",
                                        message=(
                                            f"列 '{col_keys[j]}' 平均值不一致: "
                                            f"实际均值={expected_mean:.4f}, 表中平均={avg_cell:.4f}"
                                        ),
                                        location=location,
                                        expected=expected_mean,
                                        actual=avg_cell,
                                    ))

                # (d) 百分比列（表头含关键词 或 body 全列以 % 结尾）
                for j in range(n_cols):
                    cells = col_cells[j]
                    header_text = headers[j] if j < len(headers) else ""
                    is_pct = False
                    if header_text and re.search(r"占比|比例|百分比|率|分布", header_text):
                        is_pct = True
                    else:
                        body_vals_txt = [
                            c for r_idx, c in enumerate(cells) if r_idx != 0 and c.strip()
                        ]
                        if body_vals_txt and all(c.strip().endswith("%") for c in body_vals_txt):
                            is_pct = True
                    if is_pct:
                        pct_vals: List[float] = []
                        for r_idx in range(len(rows)):
                            if r_idx == 0 or r_idx == total_row_idx or r_idx == avg_row_idx:
                                continue
                            v = self._try_parse_float(cells[r_idx] if r_idx < len(cells) else None)
                            if v is not None:
                                pct_vals.append(v)
                        if pct_vals:
                            for f in check_percentages(pct_vals):
                                f.location = location
                                findings.append(f)

                # (e) 重复行
                seen_rows: set = set()
                for r_idx, row in enumerate(rows):
                    if r_idx == 0:
                        continue
                    key = tuple(c.strip() for c in row)
                    if key in seen_rows:
                        findings.append(AuditFinding(
                            severity="warning",
                            category="duplicate_row",
                            message=f"第 {r_idx + 1} 行与之前的行内容完全重复",
                            location=f"{location}:row{r_idx + 1}",
                        ))
                    else:
                        seen_rows.add(key)

            # 6. 汇总 report
            stats = {
                "column_mismatch": sum(1 for f in findings if f.category == "column_mismatch"),
                "sum_mismatch": sum(1 for f in findings if f.category == "sum_mismatch"),
                "percentage": sum(1 for f in findings if f.category == "percentage"),
                "duplicate_row": sum(1 for f in findings if f.category == "duplicate_row"),
            }
            error_count = sum(1 for f in findings if f.severity == "error")
            report = {
                "enabled": True,
                "task_id": task_id,
                "paper_template": template,
                "tables_checked": len(tables),
                "issues": [asdict(f) for f in findings],
                "passed": error_count == 0,
                "stats": stats,
            }

            # 7. 落盘 + 通知（镜像 fact_check）
            if project_name:
                try:
                    output_dir = get_project_output_dir(project_name)
                    report_path = output_dir / "final" / "table_consistency_report.json"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                    logger.info(f"[LangGraph:{task_id}] table_consistency report saved to {report_path}")
                except Exception as disk_exc:
                    logger.warning(f"[LangGraph:{task_id}] table_consistency report save failed: {disk_exc}")

            if report["passed"]:
                self._post_chat(
                    task_id, "coordinator",
                    f"✅ 表格内部一致性校验通过：{len(tables)} 张表",
                )
            else:
                preview = [
                    f"{f.category}@{f.location}: {f.message}"
                    for f in findings
                    if f.severity == "error"
                ][:5]
                self._post_chat(
                    task_id, "coordinator",
                    f"⚠️ 表格内部一致性校验发现问题（共 {len(findings)} 处，其中 error {error_count} 处）：\n"
                    + ("\n".join(f"  - {s}" for s in preview) if preview else "")
                    + "\n报告已保存至 final/table_consistency_report.json，请人工审核后修正。",
                )

            # 校验问题写回 state 的 _quality_issues 列表（无则新增）
            quality_issues = list(state.get("_quality_issues", []))
            for f in findings:
                quality_issues.append({
                    "checker": "table_consistency",
                    "severity": f.severity,
                    "category": f.category,
                    "message": f.message,
                    "location": f.location,
                })

            self._set_result(state, "table_consistency_checker", report)
            logger.info(
                f"[LangGraph:{task_id}] table_consistency_check done: "
                f"tables={len(tables)} findings={len(findings)} passed={report['passed']}"
            )
            return {
                **state,
                "results": {**state.get("results", {}), "table_consistency_checker": report},
                "_quality_issues": quality_issues,
                "current_step": "table_consistency_check",
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] table_consistency_check 异常: {e}", exc_info=True)
            return state

    # ------------------------------------------------------------------
    # 表格内部一致性校验 — 辅助纯函数（便于单测）
    # ------------------------------------------------------------------
    @staticmethod
    def _count_tabular_columns(spec: str) -> int:
        """从 tabular 列规格字符串计算列数。

        示例: "|c|c|l|r|" → 4 ; "|>{\\centering}p{2cm}|c|" → 2 ; "*{3}{c}" → 3
        """
        if not spec:
            return 0
        s = spec.strip()
        # 展开 *{n}{spec} 重复形式（spec 可含嵌套花括号）
        star_re = re.compile(r"\*\s*\{\s*(\d+)\s*\}\s*\{")
        while True:
            m = star_re.search(s)
            if not m:
                break
            content, after = LangGraphOrchestrator._extract_braced_at(s, m.end() - 1)
            s = s[: m.start()] + (content * int(m.group(1))) + s[after:]
        # 去掉 @{...} >{...} <{...}
        s = re.sub(r"@\s*\{[^{}]*\}", "", s)
        s = re.sub(r">\s*\{[^{}]*\}", "", s)
        s = re.sub(r"<\s*\{[^{}]*\}", "", s)
        # p{..} m{..} b{..} 各占 1 列（宽度参数不含花括号）
        s = re.sub(r"[pmbPMB]\s*\{[^{}]*\}", "C", s)
        # 去掉竖线分隔
        s = s.replace("|", "")
        # 剩余字母字符即为列类型（c/l/r/…）
        return sum(1 for ch in s if ch.isalpha())

    @staticmethod
    def _extract_braced_at(text: str, pos: int) -> tuple:
        """text[pos] == '{'，返回 (花括号内内容, 闭合花括号后位置)。

        支持 \\{ \\} 转义（不计入深度）；不平衡时返回 (剩余内容, len(text))。
        """
        n = len(text)
        if pos >= n or text[pos] != "{":
            return "", pos
        depth = 0
        i = pos
        while i < n:
            ch = text[i]
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[pos + 1: i], i + 1
            i += 1
        return text[pos + 1:], n

    @staticmethod
    def _parse_brace_groups(text: str, pos: int) -> tuple:
        """从 pos 开始解析连续的 {...} 平衡花括号组，返回 (内容列表, 结束位置)。"""
        groups: List[str] = []
        i = pos
        n = len(text)
        while i < n:
            while i < n and text[i] in " \t\r\n":
                i += 1
            if i < n and text[i] == "{":
                content, after = LangGraphOrchestrator._extract_braced_at(text, i)
                groups.append(content)
                i = after
            else:
                break
        return groups, i

    @staticmethod
    def _extract_latex_tables(latex_code: str) -> List[Dict[str, Any]]:
        """从 LaTeX 源码中提取所有 tabular/tabular*/tabularx 环境并解析。

        返回每张表：{"col_spec": str, "n_cols": int, "rows": List[List[str]],
                   "caption": str, "location": "table{i+1}"}
        """
        tables: List[Dict[str, Any]] = []
        env_re = re.compile(r"\\begin\{(tabular\*|tabularx|tabular)\}")
        pos = 0
        idx = 0
        while True:
            m = env_re.search(latex_code, pos)
            if not m:
                break
            env = m.group(1)
            args, after = LangGraphOrchestrator._parse_brace_groups(latex_code, m.end())
            # 列规格是最后一个花括号组（tabular*/tabularx 的第一组是宽度）
            col_spec_raw = args[-1] if args else ""
            end_re = re.compile(r"\\end\{" + re.escape(env) + r"\}")
            end_m = end_re.search(latex_code, after)
            if not end_m:
                pos = m.end()
                continue
            body = latex_code[after: end_m.start()]

            # 提取最近的 \\caption{...}（表格浮动体内）
            caption = ""
            win_start = max(0, m.start() - 1500)
            win_end = min(len(latex_code), end_m.end() + 500)
            cap_m = re.search(r"\\caption\s*\{", latex_code[win_start:win_end])
            if cap_m:
                brace_pos = win_start + cap_m.end() - 1
                cap_content, _ = LangGraphOrchestrator._extract_braced_at(latex_code, brace_pos)
                caption = cap_content.strip()

            tables.append({
                "col_spec": col_spec_raw,
                "n_cols": LangGraphOrchestrator._count_tabular_columns(col_spec_raw),
                "rows": LangGraphOrchestrator._parse_tabular_rows(body),
                "caption": caption,
                "location": f"table{idx + 1}",
            })
            idx += 1
            pos = end_m.end()
        return tables

    @staticmethod
    def _parse_tabular_rows(body: str) -> List[List[str]]:
        """按 \\\\ 拆行，去 hline/toprule/midrule/bottomrule/cline，按未转义 & 拆单元格。"""
        rows: List[List[str]] = []
        # 行分隔符 \\\\ （可能带 \\\\[length]）
        parts = re.split(r"\\\\(?:\s*\[[^\]]*\])?", body)
        for part in parts:
            row = re.sub(
                r"\\(?:hline|toprule|midrule|bottomrule|cline\s*\{[^}]*\})\s*", "", part
            ).strip()
            if not row:
                continue
            rows.append(LangGraphOrchestrator._split_cells(row))
        return rows

    @staticmethod
    def _split_cells(row: str) -> List[str]:
        """按未转义的 & 拆分单元格，剥离 \\multicolumn{}{}{}/\\multirow 包裹。"""
        cells: List[str] = []
        current: List[str] = []
        i = 0
        n = len(row)
        while i < n:
            ch = row[i]
            if ch == "\\" and i + 1 < n:
                # 转义序列（含 \&），原样保留两字符
                current.append(ch)
                current.append(row[i + 1])
                i += 2
                continue
            if ch == "&":
                cells.append(LangGraphOrchestrator._unwrap_multicolumn("".join(current).strip()))
                current = []
                i += 1
                continue
            current.append(ch)
            i += 1
        cells.append(LangGraphOrchestrator._unwrap_multicolumn("".join(current).strip()))
        return cells

    @staticmethod
    def _unwrap_multicolumn(cell: str) -> str:
        """剥离 \\multicolumn{n}{align}{content} / \\multirow{n}{w}{content} 包裹，返回 content。"""
        cell = cell.strip()
        for cmd in ("multicolumn", "multirow"):
            m = re.match(r"\\" + cmd + r"\s*\{", cell)
            if m:
                groups, _ = LangGraphOrchestrator._parse_brace_groups(cell, m.end() - 1)
                if len(groups) >= 3:
                    return groups[2].strip()
                if groups:
                    return groups[-1].strip()
                return cell
        return cell

    @staticmethod
    def _try_parse_float(text: Any) -> Optional[float]:
        """尝试把单元格文本解析为 float，容许 % 后缀、千分逗号、科学计数、$ $ 包裹。"""
        if text is None:
            return None
        s = str(text).strip()
        if not s:
            return None
        s = s.replace("$", "").replace("\\,", "").replace("\\%", "%")
        s = re.sub(r"\\text\{([^}]*)\}", r"\1", s).strip()
        if not s:
            return None
        s = s.rstrip("%").strip().replace(",", "").strip("()[]")
        try:
            return float(s)
        except ValueError:
            return None

    async def _node_figure_caption_check(self, state: TaskState) -> TaskState:
        r"""图表说明与正文一致性校验（post 阶段）。

        在 writer 产出 LaTeX（含 \caption）之后、最终 summary 之前，校验：
        1) 正文 \includegraphics 与 figure_agent 生成清单的结构对齐；
        2) caption 中数字与 solver 求解结果对账（复用 FactChecker）；
        3) caption 与所在段落正文的趋势/语义方向是否矛盾（CJK bigram Jaccard）；
        4) caption 中对比声明与指标范围是否合法（复用 symbolic_auditor）。
        对可安全修补的缺 caption / 占位 caption 自动合成回写 writer_agent.latex_code
        并同步磁盘 final/main.tex；语义级矛盾不自动改，仅记录并标记需人工审核。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] figure_caption_check: start")
        # 新增 state 字段 _quality_issues：无则新建，聚合各节点校验问题
        quality_issues: List[Dict[str, Any]] = list(state.get("_quality_issues", []) or [])

        try:
            # 0. 前置
            state = await self._check_user_input(state)
            problem_text = state.get("problem_text", "")
            self._update_progress(task_id, problem_text, 88, "图表说明一致性校验中")
            results = self._resolve_results(state)

            writer_output = results.get("writer_agent") or {}
            latex_code = writer_output.get("latex_code", "") if isinstance(writer_output, dict) else ""
            figure_output = results.get("figure_agent") or {}
            figures = figure_output.get("figures", []) if isinstance(figure_output, dict) else []

            if not latex_code or not figures:
                logger.info(f"[LangGraph:{task_id}] figure_caption_check: empty latex_code or figures, skipping")
                return {**state, "current_step": "figure_caption_check_skipped", "_quality_issues": quality_issues}

            from pathlib import Path

            def _stem(p: str) -> str:
                try:
                    return Path(p or "").stem
                except Exception:
                    return (p or "")

            # 1. 解析 LaTeX figure 环境
            figure_block_re = re.compile(r"\\begin\{figure\*?\}(?s:.*?)\\end\{figure\*?\}")
            includegraphics_re = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
            label_re = re.compile(r"\\label\{([^}]+)\}")
            # 支持 \caption[短标题]{长标题} 与 \caption{标题}（允许一层嵌套花括号）
            caption_re = re.compile(r"\\caption(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}")
            ref_re = re.compile(r"\\(?:c?ref)\{([^}]+)\}")
            section_re = re.compile(r"\\(?:sub)*section\{([^}]*)\}")

            captions: List[Dict[str, Any]] = []
            for bi, m in enumerate(figure_block_re.finditer(latex_code)):
                block = m.group(0)
                ig = includegraphics_re.search(block)
                lb = label_re.search(block)
                cap_m = caption_re.search(block)
                cap_text = cap_m.group(1).strip() if cap_m else ""
                captions.append({
                    "block_index": bi,
                    "block_start": m.start(),
                    "block_end": m.end(),
                    "block_text": block,
                    "includegraphics_path": ig.group(1).strip() if ig else "",
                    "figure_file_basename": _stem(ig.group(1)) if ig else "",
                    "label": lb.group(1).strip() if lb else "",
                    "caption_text": cap_text,
                })
            ref_keys = set()
            for rm in ref_re.finditer(latex_code):
                for k in rm.group(1).split(","):
                    ref_keys.add(k.strip())

            # figure_agent 可能合并了 plan 的 title/description（_node_figure 一行级小改后可用，缺失则降级）
            plan_figs: List[Any] = []
            if isinstance(figure_output, dict):
                pf = figure_output.get("plan_figures") or figure_output.get("figure_plan", {})
                if isinstance(pf, dict):
                    plan_figs = pf.get("figures", [])
                elif isinstance(pf, list):
                    plan_figs = pf
            fig_meta: Dict[str, Dict[str, Any]] = {}
            for pf in plan_figs:
                if not isinstance(pf, dict):
                    continue
                key = pf.get("id") or pf.get("figure_id") or _stem(pf.get("figure_path", ""))
                if key:
                    fig_meta[key] = pf

            issues: List[Dict[str, Any]] = []

            # 2. 结构一致性——caption 与 figure_agent 生成清单对齐
            latex_basenames = {c["figure_file_basename"] for c in captions if c["figure_file_basename"]}
            agent_map: Dict[str, Dict[str, Any]] = {}
            for fig in figures:
                if not isinstance(fig, dict):
                    continue
                b = _stem(fig.get("figure_path", "")) or fig.get("figure_id", "")
                if b:
                    agent_map[b] = fig

            # (a) 正文引用了某 includegraphics 但 figure_agent 未生成
            for c in captions:
                b = c["figure_file_basename"]
                if b and b not in agent_map:
                    issues.append({
                        "severity": "error", "category": "structure_missing",
                        "figure_id": c.get("label") or b,
                        "message": f"正文引用图表 {b}，但 figure_agent 未生成该文件",
                        "suggestion": "检查 \\includegraphics 路径或重新生成该图表",
                    })
            # (b) figure_agent 生成成功但正文未 includegraphics → 孤立图表
            for b, fig in agent_map.items():
                if fig.get("success") and b not in latex_basenames:
                    issues.append({
                        "severity": "warning", "category": "orphan_figure",
                        "figure_id": fig.get("figure_id", b),
                        "message": f"figure_agent 生成成功 {b}，但正文未 \\includegraphics 引用",
                        "suggestion": "在正文中插入该图表或确认无需展示",
                    })

            PLACEHOLDER_CAPTIONS = {"图表标题", "图标题", "figure", "caption", "xxx", "...", "标题", "图", ""}

            def _is_placeholder(t: str) -> bool:
                t = (t or "").strip()
                if not t or len(t) <= 2:
                    return True
                return t.lower() in {x.lower() for x in PLACEHOLDER_CAPTIONS}

            # (c) includegraphics 无对应 \caption 或 caption 为空/占位符
            for c in captions:
                if not c["caption_text"] or _is_placeholder(c["caption_text"]):
                    issues.append({
                        "severity": "warning", "category": "missing_caption",
                        "figure_id": c.get("label") or c["figure_file_basename"],
                        "message": "图表缺少有效说明（caption 为空或占位符）",
                        "suggestion": "为该图表补充描述性 caption",
                    })

            # 3. 数值一致性——复用 FactChecker：caption 数字 vs solver 求解结果
            fc = get_fact_checker()
            solver_output = results.get("solver_agent") or {}
            solves = solver_output.get("sub_problem_solutions", []) if isinstance(solver_output, dict) else []
            solve_numbers = fc.extract_numbers_from_solves(solves) if solves else {}

            if solve_numbers:
                for c in captions:
                    ct = c["caption_text"]
                    if not ct:
                        continue
                    cap_numbers: Dict[str, float] = {}
                    for nm in fc.NUMBER_RE.finditer(ct):
                        try:
                            val = float(nm.group(0))
                        except ValueError:
                            continue
                        ctx = ct[max(0, nm.start() - 20):nm.end() + 20].replace("\n", " ").strip()[:40]
                        cap_numbers[ctx] = val
                    if not cap_numbers:
                        continue
                    for iss in fc.compare(cap_numbers, solve_numbers, threshold=0.05):
                        msg = iss.message if hasattr(iss, "message") else str(iss)
                        issues.append({
                            "severity": "error", "category": "caption_numeric",
                            "figure_id": c.get("label") or c["figure_file_basename"],
                            "message": f"图表说明数字与求解结果不符：{msg}",
                            "suggestion": "核对 caption 中数字与 solver 输出一致",
                        })

            # 把已 resolve 的 fact_checker 报告中、上下文命中 caption 片段的项升级为 caption 级 error
            fact_report = results.get("fact_checker") or {}
            if isinstance(fact_report, dict):
                for iss in fact_report.get("issues", []):
                    if not isinstance(iss, dict):
                        continue
                    ctx = iss.get("latex_key", "")
                    if not ctx:
                        continue
                    for c in captions:
                        ct = c["caption_text"]
                        if ct and (ctx in ct or ct[:24] in ctx):
                            issues.append({
                                "severity": "error", "category": "caption_numeric",
                                "figure_id": c.get("label") or c["figure_file_basename"],
                                "message": f"图表说明数字对账失败：{iss.get('message', ctx)}",
                                "suggestion": "依据求解结果修正 caption 数字",
                            })
                            break

            # 4. 方向/语义一致性——caption 与所在段落正文比对
            POS_TREND = {"上升", "增加", "提高", "improve", "better", "优于", "增长", "提升", "改善", "增强"}
            NEG_TREND = {"下降", "减少", "降低", "decline", "worse", "劣于", "减弱", "恶化", "衰退", "下滑"}

            def _has_trend(text: str, words) -> bool:
                tl = text.lower()
                return any(w.lower() in tl for w in words)

            def _cjk_bigrams(text: str) -> set:
                cjk = re.findall(r"[一-鿿]", text)
                return {cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)}

            def _jaccard(a: set, b: set) -> float:
                if not a or not b:
                    return 0.0
                inter = len(a & b)
                return inter / len(a | b) if inter else 0.0

            section_positions = [(sm.start(), sm.group(1)) for sm in section_re.finditer(latex_code)]

            for c in captions:
                ct = c["caption_text"]
                if not ct:
                    continue
                # 取块前最近 \section/\subsection 起点到块尾的正文片段（讨论该图的上下文）
                frag_start = c["block_start"]
                for sp, _ in reversed(section_positions):
                    if sp < c["block_start"]:
                        frag_start = sp
                        break
                discuss_pre = latex_code[frag_start:c["block_start"]]
                discuss_post = latex_code[c["block_end"]:c["block_end"] + 500]
                discuss_text = discuss_pre + " " + discuss_post

                # 趋势词冲突检测：caption 与正文片段方向相反且两处都含数字
                cap_pos = _has_trend(ct, POS_TREND)
                cap_neg = _has_trend(ct, NEG_TREND)
                frag_pos = _has_trend(discuss_text, POS_TREND)
                frag_neg = _has_trend(discuss_text, NEG_TREND)
                if (fc.NUMBER_RE.search(ct) and fc.NUMBER_RE.search(discuss_text) and
                        ((cap_pos and frag_neg) or (cap_neg and frag_pos))):
                    issues.append({
                        "severity": "error", "category": "trend_conflict",
                        "figure_id": c.get("label") or c["figure_file_basename"],
                        "message": "图表说明与正文趋势描述矛盾",
                        "suggestion": "统一 caption 与正文的增/降趋势表述",
                    })

                # CJK bigram Jaccard：caption 与(图表 title+description+正文片段)相似度
                meta = fig_meta.get(c["figure_file_basename"]) or fig_meta.get(c.get("label", ""))
                ref_text = " ".join(filter(None, [
                    meta.get("title", "") if isinstance(meta, dict) else "",
                    meta.get("description", "") if isinstance(meta, dict) else "",
                    discuss_text,
                ]))
                if ref_text:
                    sim = _jaccard(_cjk_bigrams(ct), _cjk_bigrams(ref_text))
                    if sim < 0.05 and not _is_placeholder(ct):
                        issues.append({
                            "severity": "warning", "category": "weak_relevance",
                            "figure_id": c.get("label") or c["figure_file_basename"],
                            "message": f"caption 主题与图表/正文弱相关（相似度 {sim:.2f}）",
                            "suggestion": "使 caption 更贴合图表实际内容",
                        })

            # 5. 对比/范围声明——复用 symbolic_auditor
            try:
                from ..services.symbolic_auditor import check_comparison_claims, check_metric_ranges
                metric_name_re = re.compile(
                    r"(accuracy|准确率|精确率|precision|recall|f1|auc|rmse|mse|mae|r2|r_squared|sharpe|max_drawdown|return_rate)",
                    re.IGNORECASE)
                comp_re = re.compile(
                    r"([一-鿿\w]{1,30})\s*(?:优于|超过|outperform|better\s+than)\s*([一-鿿\w]{1,30})",
                    re.IGNORECASE)

                for c in captions:
                    ct = c["caption_text"]
                    if not ct:
                        continue
                    fig_id = c.get("label") or c["figure_file_basename"]
                    nums = []
                    for nm in fc.NUMBER_RE.finditer(ct):
                        try:
                            nums.append(float(nm.group(0)))
                        except ValueError:
                            continue
                    # 对比声明：组装 comparison_claims
                    cap_lower = ct.lower()
                    metric_name = "loss" if any(w in cap_lower for w in ["误差", "loss", "error", "mse", "rmse", "mae", "max_drawdown"]) else "accuracy"
                    claims = []
                    for cm in comp_re.finditer(ct):
                        claims.append({
                            "method_a": cm.group(1), "method_b": cm.group(2),
                            "metric": metric_name,
                            "value_a": nums[0] if nums else None,
                            "value_b": nums[1] if len(nums) > 1 else None,
                            "claim": "A优于B",
                        })
                    for f in check_comparison_claims(claims):
                        issues.append({
                            "severity": f.severity, "category": "comparison",
                            "figure_id": fig_id, "message": f.message,
                            "suggestion": "修正对比声明的数值方向",
                        })
                    # 指标范围：caption 内含指标名的数字组装 metrics dict
                    metrics: Dict[str, Any] = {}
                    for mm in metric_name_re.finditer(ct):
                        mname = mm.group(1)
                        nmatch = fc.NUMBER_RE.search(ct[mm.end():])
                        if nmatch:
                            try:
                                metrics[mname] = (float(nmatch.group(0)), 0.0, 1.0)
                            except ValueError:
                                pass
                    for f in check_metric_ranges(metrics):
                        issues.append({
                            "severity": f.severity, "category": "range",
                            "figure_id": fig_id, "message": f.message,
                            "suggestion": "确认指标值在合理范围内",
                        })
            except Exception as sa_exc:
                logger.warning(f"[LangGraph:{task_id}] symbolic_auditor 不可用，跳过对比/范围校验: {sa_exc}")

            # 6. 自动修补（仅修可安全修的：缺 caption / 占位 caption）
            auto_patched = 0
            patched = False
            new_parts: List[str] = []
            last_pos = 0
            for c in captions:
                new_parts.append(latex_code[last_pos:c["block_start"]])
                block = c["block_text"]
                fig = agent_map.get(c["figure_file_basename"])
                meta = fig_meta.get(c["figure_file_basename"]) or fig_meta.get(c.get("label", ""))
                if (not c["caption_text"] or _is_placeholder(c["caption_text"])) and (fig or meta):
                    title = (meta.get("title") if isinstance(meta, dict) else "") or \
                            (fig.get("figure_id") if isinstance(fig, dict) else "") or f"fig_{c['block_index'] + 1}"
                    desc = (meta.get("description") if isinstance(meta, dict) else "") or ""
                    if not desc:
                        for sp, sname in section_positions:
                            if sp < c["block_start"]:
                                desc = sname
                            else:
                                break
                    synth = f"图{c['block_index'] + 1}：{title}" + (f"（{desc}）" if desc else "")
                    if caption_re.search(block):
                        patched_block = caption_re.sub(lambda _mm: r"\caption{" + synth + "}", block, count=1)
                    else:
                        patched_block = re.sub(
                            r"\\end\{figure\*?\}",
                            lambda mm: r"\caption{" + synth + "}\n" + mm.group(0),
                            block, count=1)
                    if patched_block != block:
                        block = patched_block
                        auto_patched += 1
                        patched = True
                new_parts.append(block)
                last_pos = c["block_end"]
            new_parts.append(latex_code[last_pos:])
            new_latex = "".join(new_parts)

            writer_ref: Dict[str, Any] = {}
            if patched and new_latex != latex_code:
                try:
                    writer_output["latex_code"] = new_latex
                    writer_output["_caption_auto_patched"] = True
                    writer_ref = self._set_result(state, "writer_agent", writer_output)
                    # 同步磁盘 final/main.tex（取自 _node_compliance_check 范式）
                    output_dir = get_project_output_dir(state.get("project_name"))
                    final_tex = output_dir / "final" / "main.tex"
                    final_tex.parent.mkdir(parents=True, exist_ok=True)
                    final_tex.write_text(new_latex, encoding="utf-8")
                    papers_tex = output_dir / "papers" / f"paper_{task_id}.tex"
                    if papers_tex.exists():
                        papers_tex.write_text(new_latex, encoding="utf-8")
                    logger.info(f"[LangGraph:{task_id}] figure_caption_check: auto-patched {auto_patched} captions, wrote {final_tex}")
                except Exception as disk_exc:
                    logger.warning(f"[LangGraph:{task_id}] caption auto-patch disk write failed: {disk_exc}")

            # 7. 产出 report
            error_count = sum(1 for i in issues if i.get("severity") == "error")
            passed = error_count == 0
            report = {
                "task_id": task_id,
                "enabled": True,
                "passed": passed,
                "issue_count": len(issues),
                "error_count": error_count,
                "issues": issues,
                "checked_captions": len(captions),
                "checked_figures": len(figures),
                "auto_patched": auto_patched,
                "ref_keys": sorted(ref_keys),
            }
            self._set_result(state, "figure_caption_check", report)

            # 校验问题写回 state 的 _quality_issues 列表
            for i in issues:
                quality_issues.append({
                    "node": "figure_caption_check",
                    "severity": i.get("severity"),
                    "category": i.get("category"),
                    "figure_id": i.get("figure_id"),
                    "message": i.get("message"),
                })

            # claims_trace 追加一条 caption_check trace entry
            claims_trace = list(state.get("claims_trace", []) or [])
            claims_trace.append({
                "timestamp": datetime.now().isoformat(),
                "node": "figure_caption_check",
                "issue_count": len(issues),
                "auto_patched": auto_patched,
                "sample_issues": issues[:3],
            })

            # 持久化 report 到 final/figure_caption_check_report.json（仿 fact_check）
            try:
                output_dir = get_project_output_dir(state.get("project_name"))
                report_path = output_dir / "final" / "figure_caption_check_report.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
            except Exception as disk_exc:
                logger.warning(f"[LangGraph:{task_id}] figure_caption_check report save failed: {disk_exc}")

            current_step = "figure_caption_check_done" if passed else "figure_caption_check_review_required"
            self._post_chat(
                task_id, "coordinator",
                f"{'✅' if passed else '⚠️'} 图表说明校验：{len(issues)} 处问题/已自动修补 {auto_patched} 处"
                + ("" if passed else "，存在需人工审核的语义矛盾"),
            )
            logger.info(
                f"[LangGraph:{task_id}] figure_caption_check done: issues={len(issues)} "
                f"errors={error_count} auto_patched={auto_patched} passed={passed}")

            merged_results = {**state.get("results", {}), "figure_caption_check": report, **writer_ref}
            return {
                **state,
                "results": merged_results,
                "claims_trace": claims_trace,
                "_quality_issues": quality_issues,
                "current_step": "figure_caption_check_done",
            }
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] figure_caption_check 失败: {exc}", exc_info=True)
            return {**state, "current_step": "figure_caption_check_failed", "_quality_issues": quality_issues}

    async def _node_citation_density_check(self, state: TaskState) -> TaskState:
        """引用密度合理性校验（post 阶段，纯规则，不调 LLM）。

        插入位置：fact_check → citation_density_check → compliance_check。
        fact_check 已把 writer 的 latex_code 预写到 final/main.tex，本节点优先读
        内存中已 resolve 的 writer_agent 输出，避免磁盘时序依赖。复用
        WriterAgent._scan_cite_keys 提取 \\cite key，复用
        ConsistencyChecker._check_citation_usage 检测孤立 bib 条目。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] citation_density_check: start")
        try:
            from .writer_agent import WriterAgent
            from ..services.consistency_checker import get_consistency_checker

            # ===== 1. 前置读取与短路 =====
            results = self._resolve_results(state)
            writer_output = results.get("writer_agent", {}) or {}
            if not isinstance(writer_output, dict):
                writer_output = {}
            latex_code = writer_output.get("latex_code", "") or ""
            if not latex_code:
                logger.info(f"[LangGraph:{task_id}] citation_density_check: writer 无 latex_code，跳过")
                return {**state, "current_step": "citation_density_check_skipped"}

            citations_top = writer_output.get("citations", []) or \
                (writer_output.get("paper_memory", {}) or {}).get("citations", [])
            if not isinstance(citations_top, list):
                citations_top = []
            chapters = writer_output.get("chapters", []) or []
            if not isinstance(chapters, list):
                chapters = []
            research_papers = ((results.get("research_agent", {}) or {}).get("papers", [])) or []
            if not isinstance(research_papers, list):
                research_papers = []

            template = state.get("paper_template", "math_modeling") or "math_modeling"
            workflow_type = state.get("workflow_type", "standard") or "standard"
            project_name = state.get("project_name")

            self._update_progress(task_id, state.get("problem_text", ""), 82, "引用密度校验中")

            # ===== 2. 全文被引 key 全集（去重保序）+ bib key 全集 =====
            all_cited_keys = WriterAgent._scan_cite_keys(latex_code)
            total_cited = len(all_cited_keys)
            bib_keys = {
                c.get("key") for c in citations_top
                if isinstance(c, dict) and c.get("key")
            }
            total_bib = len(citations_top)

            # ===== 3. 逐章节提取引用（latex 优先，回退 chapter.citations） =====
            core_ids = {"modeling", "result_analysis", "reliability", "empirical", "results"}
            per_chapter_count: Dict[str, int] = {}
            core_cite_count = 0
            core_has_numeric = False
            max_count = 0
            max_chapter_id = ""

            def _chapter_keys(ch: Dict[str, Any]) -> set:
                # 组装后的 chapters 可能省略 latex，回退到 chapter.citations 的 key
                lx = ch.get("latex", "") or ""
                if lx:
                    return set(WriterAgent._scan_cite_keys(lx))
                return {
                    c.get("key") for c in ch.get("citations", [])
                    if isinstance(c, dict) and c.get("key")
                }

            for ch in chapters:
                if not isinstance(ch, dict):
                    continue
                ch_id = str(ch.get("id") or ch.get("title") or "")
                keys = _chapter_keys(ch)
                per_chapter_count[ch_id] = len(keys)
                if ch_id in core_ids:
                    core_cite_count += len(keys)
                    lx = ch.get("latex", "") or ""
                    if lx and re.search(r"\d", lx):
                        core_has_numeric = True
                if len(keys) > max_count:
                    max_count = len(keys)
                    max_chapter_id = ch_id

            max_chapter_share = (max_count / total_cited) if total_cited > 0 else 0.0

            # ===== 4. 正文字数粗估 → 引用密度/千字 =====
            body_text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", latex_code)
            body_chars = len(body_text)
            cite_per_1k = total_cited / max(body_chars / 1000, 1)

            # ===== 5. 孤立 bib（复用 consistency_checker）+ 悬空引用 =====
            orphan_issues = get_consistency_checker()._check_citation_usage(
                latex_code, citations_top
            )
            orphan_count = len(orphan_issues)
            orphan_rate = orphan_count / max(total_bib, 1)
            dangling = [k for k in all_cited_keys if k not in bib_keys]
            dangling_count = len(dangling)

            # ===== 6. 模板感知阈值（硬编码真实规则，可复现） =====
            ccf_a = {"neurips_2024", "ieee_conference", "acm_sigconf",
                     "springer_lncs", "research_paper"}
            if (template in {"research_survey", "research_review", "literature_review"}
                    or workflow_type in {"deep_research", "survey"}):
                min_refs, min_cite_per_1k = 25, 1.5
            elif template in ccf_a or workflow_type == "research_paper":
                min_refs, min_cite_per_1k = 15, 1.0
            elif template == "financial_analysis":
                min_refs, min_cite_per_1k = 8, 0.8
            elif template in {"math_modeling", "coursework"}:
                min_refs, min_cite_per_1k = 5, 0.5
            else:
                min_refs, min_cite_per_1k = 5, 0.5
            max_share_threshold = 0.6
            orphan_rate_threshold = 0.3

            # ===== 7. 生成 issues（带 severity/category/location/message） =====
            issues: List[Dict[str, Any]] = []

            def _add(severity: str, category: str, location: str, message: str) -> None:
                issues.append({
                    "severity": severity,
                    "category": category,
                    "location": location,
                    "message": message,
                })

            if total_bib < min_refs:
                _add("warning", "citation_volume", "bibliography",
                     f"参考文献数 {total_bib} 低于 {template} 期望下限 {min_refs}")
            if cite_per_1k < min_cite_per_1k:
                _add("warning", "citation_density", "body",
                     f"引用密度 {cite_per_1k:.2f}/千字 低于阈值 {min_cite_per_1k}")
            if max_chapter_share > max_share_threshold and max_chapter_id:
                _add("warning", "citation_concentration", max_chapter_id,
                     f"引用过度集中于 {max_chapter_id}（占比 {max_chapter_share:.0%}），疑似引用堆砌")
            if core_cite_count == 0 and core_has_numeric:
                _add("warning", "citation_missing", "core_sections",
                     "建模/结果核心章节零引用，关键声明缺少来源支撑")
            if orphan_rate > orphan_rate_threshold and total_bib > 0:
                _add("warning", "citation_orphan", "bibliography",
                     f"{orphan_count}/{total_bib} 条参考文献未被正文引用")
            if dangling_count > 0:
                preview = ", ".join(dangling[:5])
                _add("warning", "citation_dangling", "body",
                     f"正文引用 {dangling_count} 个 key 在 bib 中缺失：{preview}")
            if (research_papers and len(research_papers) >= min_refs
                    and total_bib < min_refs * 0.8):
                _add("info", "citation_underuse", "bibliography",
                     f"检索到 {len(research_papers)} 篇文献但仅引用 {total_bib}，可补充引用")

            warning_count = sum(1 for i in issues if i["severity"] == "warning")
            passed = warning_count == 0 and total_bib >= min_refs

            report = {
                "task_id": task_id,
                "template": template,
                "workflow_type": workflow_type,
                "stats": {
                    "total_cited": total_cited,
                    "total_bib": total_bib,
                    "cite_per_1k": round(cite_per_1k, 4),
                    "orphan_rate": round(orphan_rate, 4),
                    "dangling_count": dangling_count,
                    "per_chapter_count": per_chapter_count,
                    "max_chapter_share": round(max_chapter_share, 4),
                    "core_cite_count": core_cite_count,
                },
                "issues": issues,
                "issue_count": warning_count,
                "passed": passed,
            }

            # ===== 8. 持久化与通知（复用 fact_check 范式） =====
            try:
                output_dir = get_project_output_dir(project_name)
                report_path = output_dir / "final" / "citation_density_report.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                logger.info(f"[LangGraph:{task_id}] citation_density_check: report saved to {report_path}")
            except Exception as disk_exc:
                logger.warning(f"[LangGraph:{task_id}] citation_density_check 报告写盘失败: {disk_exc}")

            ref_update = self._set_result(state, "citation_density_check", report)
            if passed:
                self._post_chat(
                    task_id, "coordinator",
                    f"✅ 引用密度合理：引用 {total_cited}，密度 {cite_per_1k:.2f}/千字",
                )
            else:
                warn_msgs = [i["message"] for i in issues if i["severity"] == "warning"][:3]
                top3 = "\n".join(f"  - {m}" for m in warn_msgs)
                self._post_chat(
                    task_id, "coordinator",
                    f"⚠️ 引用密度问题：{warning_count} 项，报告已存 final/citation_density_report.json\n"
                    + top3,
                )

            logger.info(
                f"[LangGraph:{task_id}] citation_density_check done: "
                f"passed={passed} cited={total_cited} bib={total_bib} "
                f"density={cite_per_1k:.2f}/千字 issues={warning_count}"
            )

            # ===== 9. 校验问题写回 state._quality_issues（无则新增） =====
            quality_issues = list(state.get("_quality_issues", []) or [])
            for iss in issues:
                quality_issues.append({
                    "node": "citation_density_check",
                    "severity": iss["severity"],
                    "category": iss["category"],
                    "location": iss["location"],
                    "message": iss["message"],
                })

            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "_quality_issues": quality_issues,
                "current_step": "citation_density_check_done",
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] citation_density_check 失败: {e}")
            return state

    async def _node_reference_completeness(self, state: TaskState) -> TaskState:
        """参考文献完整性审计节点（post 阶段交付物质量门）。

        与 _node_fact_check 平级，紧接 fact_check 之后运行。审计正文 \\cite{} 与
        参考文献注册表的一致性，复用 services/reference_verifier 做存在性验真，
        并以 research_agent 真实检索池为 ground-truth 做防编造交叉校验。

        四类缺陷：
          - dangling: 正文引用了但 bib 缺条目（编译会 undefined）
          - orphans:  bib 有条目但正文未引用
          - incomplete: 条目残缺（缺 title+author / 占位 / 无 year 且无 doi/arxiv/url）
          - suspected_fabricated: 声称是文献却无法验证且不在真实检索池（疑似编造）

        任何异常都降级放行，不阻塞 summary。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] reference_completeness: 开始审计参考文献完整性")
        self._update_progress(task_id, state.get("problem_text", ""), 85, "参考文献完整性审计中")
        results = self._resolve_results(state)

        # 1) 解析输入
        writer_output = results.get("writer_agent") or {}
        if not isinstance(writer_output, dict):
            writer_output = {}
        latex_code = writer_output.get("latex_code", "") or ""
        if not latex_code:
            logger.info(f"[LangGraph:{task_id}] reference_completeness: 无 LaTeX 内容，跳过审计")
            return {**state, "current_step": "reference_completeness_skipped"}

        research_output = results.get("research_agent") or {}
        research_papers = research_output.get("papers", []) if isinstance(research_output, dict) else []

        try:
            # 2) 物化 main.tex（自包含，防 fact_check 被跳过时空转）
            output_dir = None
            try:
                output_dir = get_project_output_dir(state.get("project_name"))
                final_dir = output_dir / "final"
                final_dir.mkdir(parents=True, exist_ok=True)
                final_tex = final_dir / "main.tex"
                if not final_tex.exists():
                    final_tex.write_text(latex_code, encoding="utf-8")
                    logger.info(f"[LangGraph:{task_id}] reference_completeness: 物化 {final_tex}")
            except Exception as disk_exc:
                logger.warning(f"[LangGraph:{task_id}] reference_completeness: main.tex 物化失败: {disk_exc}")

            # 3) 提取正文实际引用的 key 集合（复用 WriterAgent._scan_cite_keys）
            agent = self.agents.get("writer_agent")
            if agent is not None and hasattr(agent, "_scan_cite_keys"):
                used_keys = agent._scan_cite_keys(latex_code)
            else:
                used_keys = []
                _seen_keys: set = set()
                for m in re.finditer(r"\\cite[a-z]*\{([^}]+)\}", latex_code):
                    for k in m.group(1).split(","):
                        k = k.strip()
                        if k and k not in _seen_keys:
                            _seen_keys.add(k)
                            used_keys.append(k)
            used_keys_set = set(used_keys)

            # 4) 构建参考文献注册表（合并三处来源，按 key 去重）
            def _entry_key(entry: Dict[str, Any], idx: int) -> str:
                k = (entry.get("key") or "").strip()
                if k:
                    return k
                title = (entry.get("title") or "").strip()
                year = str(entry.get("year") or "").strip()
                if title or year:
                    base = re.sub(r"[^\w]+", "_", f"{title}_{year}".strip("_")).strip("_").lower()
                    return base or f"ref_{idx}"
                return f"ref_{idx}"

            raw_entries: List[Dict[str, Any]] = []
            raw_entries.extend(writer_output.get("citations", []) or [])
            paper_memory = writer_output.get("paper_memory", {})
            if isinstance(paper_memory, dict):
                raw_entries.extend(paper_memory.get("citations", []) or [])
            chapters = writer_output.get("chapters", []) or []
            for ch in chapters:
                if isinstance(ch, dict):
                    raw_entries.extend([c for c in (ch.get("citations", []) or []) if isinstance(c, dict)])

            registry: Dict[str, Dict[str, Any]] = {}
            for idx, entry in enumerate(raw_entries):
                if not isinstance(entry, dict):
                    continue
                key = _entry_key(entry, idx)
                if key not in registry:
                    registry[key] = entry

            total = len(registry)
            logger.info(
                f"[LangGraph:{task_id}] reference_completeness: 正文引用 {len(used_keys)} 个 key, "
                f"注册表 {total} 条"
            )

            # 5) 计算四类缺陷
            # (a) dangling: 正文引用但注册表查不到
            dangling = [k for k in used_keys if k not in registry]
            # (b) orphans: 注册表有但正文未引用
            orphans = [k for k in registry if k not in used_keys_set]

            # (c) incomplete: 残缺条目
            incomplete: List[str] = []
            for key, entry in registry.items():
                has_title = bool((entry.get("title") or "").strip())
                has_author = bool((entry.get("author") or "").strip())
                has_year = bool(str(entry.get("year") or "").strip())
                has_doi = bool((entry.get("doi") or "").strip())
                has_arxiv = bool((entry.get("arxiv_id") or "").strip())
                has_url = bool((entry.get("url") or "").strip())
                if entry.get("_placeholder"):
                    incomplete.append(key)
                elif not has_title and not has_author:
                    incomplete.append(key)
                elif not has_year and not has_doi and not has_arxiv and not has_url:
                    incomplete.append(key)

            # (d) unverified / suspected_fabricated
            # 优先复用 writer 已写入的 _verified 缓存；仅对缺失标志的子集调用验真
            to_verify = [e for e in registry.values() if e.get("_verified") is None]
            if to_verify:
                try:
                    from ..services.reference_verifier import verify_all_references
                    verify_results = await verify_all_references(
                        to_verify, max_concurrent=5, check_title=True
                    )
                    for entry, vr in zip(to_verify, verify_results):
                        entry["_verified"] = bool(vr.verified)
                        if not vr.verified:
                            entry["_verify_error"] = vr.error
                except Exception as verify_exc:
                    logger.warning(
                        f"[LangGraph:{task_id}] reference_completeness: 参考文献验真失败（降级跳过）: {verify_exc}"
                    )

            # 防编造交叉校验：把 research_papers 归一化为 ground-truth 池
            pool_titles: set = set()
            pool_arxiv: set = set()
            pool_doi: set = set()
            for p in research_papers or []:
                if not isinstance(p, dict):
                    continue
                t = (p.get("title") or "").strip()
                if t:
                    nt = re.sub(r"[^\w\s]", "", t.lower())
                    nt = re.sub(r"\s+", " ", nt).strip()
                    if nt:
                        pool_titles.add(nt)
                aid = (p.get("arxiv_id") or "").strip()
                if aid:
                    pool_arxiv.add(re.sub(r"v\d+$", "", aid))
                d = (p.get("doi") or "").strip().lower()
                if d:
                    pool_doi.add(d)

            def _in_research_pool(entry: Dict[str, Any]) -> bool:
                t = (entry.get("title") or "").strip()
                if t:
                    nt = re.sub(r"[^\w\s]", "", t.lower())
                    nt = re.sub(r"\s+", " ", nt).strip()
                    if nt and nt in pool_titles:
                        return True
                aid = (entry.get("arxiv_id") or "").strip()
                if aid and re.sub(r"v\d+$", "", aid) in pool_arxiv:
                    return True
                d = (entry.get("doi") or "").strip().lower()
                if d and d in pool_doi:
                    return True
                return False

            suspected_fabricated: List[str] = []
            for key, entry in registry.items():
                if entry.get("_verified") is False:
                    in_pool = _in_research_pool(entry)
                    has_author = bool((entry.get("author") or "").strip())
                    has_year = bool(str(entry.get("year") or "").strip())
                    is_kb = entry.get("_source_type") == "knowledge_base"
                    if not in_pool and (has_author or has_year) and not is_kb:
                        suspected_fabricated.append(key)

            # 6) 评分
            verified_count = sum(1 for e in registry.values() if e.get("_verified") is True)
            verified_ratio = round(verified_count / total, 4) if total else 1.0

            score = 100
            score -= 20 * len(dangling)
            score -= 20 * len(suspected_fabricated)
            score -= 5 * len(incomplete)
            score -= 3 * len(orphans)
            score = max(0, score)
            passed = (len(dangling) == 0) and (len(suspected_fabricated) == 0) and (verified_ratio >= 0.6)

            # per_entry 状态汇总
            per_entry = []
            for key, entry in registry.items():
                if key in dangling:
                    status = "dangling"
                elif key in suspected_fabricated:
                    status = "suspected_fabricated"
                elif key in incomplete:
                    status = "incomplete"
                elif key in orphans:
                    status = "orphan"
                elif entry.get("_verified") is True:
                    status = "verified"
                else:
                    status = "unverified"
                per_entry.append({
                    "key": key,
                    "status": status,
                    "source": entry.get("_source_type") or entry.get("venue") or "",
                })

            report = {
                "task_id": task_id,
                "total": total,
                "used_count": len(used_keys),
                "dangling": dangling,
                "orphans": orphans,
                "incomplete": incomplete,
                "suspected_fabricated": suspected_fabricated,
                "per_entry": per_entry,
                "verified_ratio": verified_ratio,
                "score": score,
                "passed": passed,
            }

            # 回写 writer 结果（标记可疑条目，只标记不删，避免破坏 LaTeX）
            writer_output["_reference_audit"] = report
            for key in suspected_fabricated:
                if key in registry:
                    registry[key]["_suspected_fabricated"] = True
            for key in orphans:
                if key in registry:
                    registry[key]["_orphan"] = True
            self._set_result(state, "writer_agent", writer_output)
            self._set_result(state, "reference_completeness", report)

            # 落盘报告
            if output_dir is not None:
                try:
                    report_dir = output_dir / "final"
                    report_dir.mkdir(parents=True, exist_ok=True)
                    report_path = report_dir / "reference_completeness_report.json"
                    report_path.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                    logger.info(f"[LangGraph:{task_id}] reference_completeness: 报告已保存 {report_path}")
                except Exception as disk_exc:
                    logger.warning(f"[LangGraph:{task_id}] reference_completeness: 报告落盘失败: {disk_exc}")

            # 通知
            if passed:
                self._post_chat(
                    task_id, "reference_completeness",
                    f"✅ 参考文献完整性通过: {total} 篇, 已验证 {verified_count} 篇",
                )
            else:
                self._post_chat(
                    task_id, "reference_completeness",
                    f"⚠️ 参考文献完整性告警: 悬空 {len(dangling)} / 疑似编造 {len(suspected_fabricated)} / "
                    f"残缺 {len(incomplete)}, 报告见 final/reference_completeness_report.json",
                )

            # 追加 claims_trace
            trace = list(state.get("claims_trace", []) or [])
            trace.append({
                "timestamp": datetime.now().isoformat(),
                "node": "reference_completeness",
                "passed": passed,
                "score": score,
                "dangling": len(dangling),
                "suspected_fabricated": len(suspected_fabricated),
            })

            # 校验问题写回 state 的 _quality_issues 列表（无则新增）
            quality_issues = list(state.get("_quality_issues") or [])
            for key in dangling:
                quality_issues.append({
                    "node": "reference_completeness",
                    "task_id": task_id,
                    "severity": "error",
                    "category": "dangling_reference",
                    "key": key,
                    "message": f"悬空引用: 正文 \\cite{{{key}}} 在参考文献注册表中找不到对应条目",
                })
            for key in suspected_fabricated:
                quality_issues.append({
                    "node": "reference_completeness",
                    "task_id": task_id,
                    "severity": "error",
                    "category": "suspected_fabricated_reference",
                    "key": key,
                    "message": f"疑似编造文献: {key} 无法验证且不在真实检索池中",
                })
            for key in incomplete:
                quality_issues.append({
                    "node": "reference_completeness",
                    "task_id": task_id,
                    "severity": "warning",
                    "category": "incomplete_reference",
                    "key": key,
                    "message": f"残缺参考文献条目: {key} 缺少关键字段（title/author/year/doi/arxiv/url）",
                })
            for key in orphans:
                quality_issues.append({
                    "node": "reference_completeness",
                    "task_id": task_id,
                    "severity": "warning",
                    "category": "orphan_reference",
                    "key": key,
                    "message": f"孤立参考文献: {key} 已列入 bib 但正文未引用",
                })

            logger.info(
                f"[LangGraph:{task_id}] reference_completeness: passed={passed} score={score} "
                f"dangling={len(dangling)} suspected_fabricated={len(suspected_fabricated)} "
                f"incomplete={len(incomplete)} orphans={len(orphans)} verified={verified_count}/{total}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), "reference_completeness": report},
                "claims_trace": trace,
                "_quality_issues": quality_issues,
                "current_step": "reference_completeness",
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] reference_completeness 失败: {e}", exc_info=True)
            return state

    async def _node_terminology_consistency(self, state: TaskState) -> TaskState:
        """术语统一性校验节点（post 阶段，非破坏性只读）。

        图位置：fact_check → terminology_consistency → compliance_check。
        校验对象：writer_agent 终稿的 latex_code（在 peer_review 定稿、fact_check 数值对账之后，
        compliance_check 改写文本之前），为非破坏性只读校验。

        复用 backend/app/services/consistency_checker.py::get_consistency_checker().check()
        做术语对偶冲突 / 模型名漏提及 / 引用孤立 / 摘要↔结论数字一致性；
        并自实现符号一致性 + 缩略语一致性（补 ConsistencyChecker._check_symbol_consistency 空缺）。
        校验结果非破坏性写回 results.terminology_consistency，并追加到 state._quality_issues。
        异常时降级放行，绝不阻塞主流程。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] terminology_consistency: 开始术语统一性校验")

        workflow_type = state.get("workflow_type", "standard")
        results = self._resolve_results(state)
        writer_output = results.get("writer_agent") or {}
        if not isinstance(writer_output, dict):
            writer_output = {}
        latex_code = writer_output.get("latex_code", "") or writer_output.get("latex", "")

        # 1. 守卫：无 latex 或 quick/code_focused 模式跳过
        if not latex_code or workflow_type in ("quick", "code_focused"):
            logger.info(
                f"[LangGraph:{task_id}] terminology_consistency: 跳过"
                f"（latex_empty={not latex_code}, workflow={workflow_type}）"
            )
            return {**state, "current_step": "terminology_consistency_skipped"}

        self._update_progress(task_id, state.get("problem_text", ""), 86, "术语统一性校验中")

        project_name = state.get("project_name")
        try:
            output_dir = get_project_output_dir(project_name)
        except Exception:
            output_dir = None

        paper_memory = writer_output.get("paper_memory") or {}
        if not isinstance(paper_memory, dict):
            paper_memory = {}
        chapters = writer_output.get("chapters") or []
        citations = writer_output.get("citations") or []
        modeler_output = results.get("modeler_agent") or {}
        if not isinstance(modeler_output, dict):
            modeler_output = {}

        try:
            from ..services.consistency_checker import get_consistency_checker

            # 2. 构建权威术语表 G（合并 paper_memory + modeler）
            glossary: Dict[str, str] = {}  # term -> 来源章节
            for term, chap in (paper_memory.get("terminology") or {}).items():
                if term:
                    glossary[term] = str(chap) if chap else "paper_memory.terminology"
            for glyph, info in (paper_memory.get("symbols") or {}).items():
                if not glyph:
                    continue
                src = (info.get("chapter") if isinstance(info, dict) else None) or "paper_memory.symbols"
                glossary[glyph] = src
            for bucket in ("model_names", "algorithms", "datasets", "metrics"):
                for name in (paper_memory.get(bucket) or []):
                    if name and name not in glossary:
                        glossary[name] = f"paper_memory.{bucket}"
            for m in (modeler_output.get("sub_problem_models") or []):
                if not isinstance(m, dict):
                    continue
                mn = m.get("model_name")
                if mn and mn not in glossary:
                    glossary[mn] = "modeler.model_name"
                alg = m.get("algorithm") or {}
                if isinstance(alg, dict) and alg.get("name"):
                    glossary.setdefault(alg["name"], "modeler.algorithm.name")
                for dv in (m.get("decision_variables") or []):
                    if isinstance(dv, dict) and dv.get("name"):
                        glossary.setdefault(dv["name"], "modeler.decision_variables")

            # 3. 复用 ConsistencyChecker（terminology 对偶冲突 / 模型名漏提及 / 引用孤立 / 摘要↔结论数字）
            chapter_summaries = [
                {"id": c.get("id"), "title": c.get("title"), "summary": c.get("summary", "")}
                for c in chapters if isinstance(c, dict)
            ]
            report = get_consistency_checker().check(
                task_id=task_id,
                latex_code=latex_code,
                chapter_summaries=chapter_summaries,
                paper_memory=paper_memory,
                bib_entries=citations,
                solver_numerical_results=None,
            )
            report_dict = report.to_dict()
            node_issues: List[Dict[str, Any]] = list(report_dict.get("issues") or [])

            # 4. 自实现符号一致性（补 ConsistencyChecker._check_symbol_consistency 空缺）
            symbol_defs: Dict[str, List[tuple]] = {}  # glyph -> [(meaning, location)]
            # 4a. "符号说明"表格行（含 & 且含 $...$）
            for raw_line in latex_code.split("\n"):
                line = raw_line.strip()
                if "&" not in line or "$" not in line:
                    continue
                sym_match = re.search(r"\$([^$]+)\$", line)
                if not sym_match:
                    continue
                glyph = sym_match.group(1).strip()
                parts = line.split("&", 1)
                meaning = parts[1].strip().rstrip("\\").strip() if len(parts) > 1 else ""
                meaning = meaning.split("&")[0].strip()
                if glyph and meaning:
                    symbol_defs.setdefault(glyph, []).append((meaning, "符号说明表"))
            # 4b. 行内定义："称/记/设/令 $X$ 为/表示/代表 …"
            inline_pat = re.compile(r"(?:称|记|设|令)\s*\$([^$]+)\$\s*(?:为|表示|代表)([^，。,;\n\\]{1,30})")
            for m in inline_pat.finditer(latex_code):
                glyph = m.group(1).strip()
                meaning = m.group(2).strip()
                if glyph and meaning:
                    symbol_defs.setdefault(glyph, []).append((meaning, "行内定义"))
            # 4c. 同一 glyph ≥2 个不同 meaning → 冲突
            for glyph, defs in symbol_defs.items():
                meanings = {d[0] for d in defs}
                if len(defs) >= 2 and len(meanings) >= 2:
                    detail = "；".join(f"{d[1]}: {d[0]}" for d in defs[:3])
                    node_issues.append({
                        "category": "symbol",
                        "severity": "high",
                        "location": "全文",
                        "message": f"符号 ${glyph}$ 含义冲突：{detail}",
                    })

            # 5. 缩略语一致性
            acronym_defs: Dict[str, List[str]] = {}  # acronym -> [expansions]
            # 5a. 中文全称（…）ABC"
            for m in re.finditer(r"([一-龥]{2,12})\s*[（(]\s*([A-Z]{2,8})\s*[）)]", latex_code):
                expansion, acr = m.group(1).strip(), m.group(2).strip()
                acronym_defs.setdefault(acr, []).append(expansion)
            # 5a2. 英文缩略语（中文全称）"ABC（卷积神经网络）"
            for m in re.finditer(r"\b([A-Z]{2,8})\s*[（(]\s*([一-龥]{2,12})\s*[）)]", latex_code):
                acr, expansion = m.group(1).strip(), m.group(2).strip()
                acronym_defs.setdefault(acr, []).append(expansion)
            # 5b. 英文全称 "ABC (Full Name)"
            for m in re.finditer(r"\b([A-Z]{2,8})\s*[（(]\s*([A-Za-z][A-Za-z\s]{2,40})\s*[）)]", latex_code):
                acr, expansion = m.group(1).strip(), m.group(2).strip()
                acronym_defs.setdefault(acr, []).append(expansion)
            # 5c. 全称不一致
            for acr, expansions in acronym_defs.items():
                unique = list(dict.fromkeys(e for e in expansions if e))
                if len(unique) >= 2:
                    node_issues.append({
                        "category": "acronym",
                        "severity": "high",
                        "location": "全文",
                        "message": f"缩略语 {acr} 全称不一致：{unique[0]} vs {unique[1]}",
                    })
            # 5d. 使用但从未定义（≥2 次以降噪，过滤常见英文/编号噪声，限 10 条）
            common_noise = {"THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "ARE", "BUT", "NOT", "ALL", "USE", "USING", "FIG", "TAB"}
            acr_counts: Dict[str, int] = {}
            for acr in re.findall(r"\b([A-Z]{2,8})\b", latex_code):
                acr_counts[acr] = acr_counts.get(acr, 0) + 1
            undefined_count = 0
            for acr, cnt in acr_counts.items():
                if acr in common_noise or acr in acronym_defs:
                    continue
                if cnt >= 2 and undefined_count < 10:
                    node_issues.append({
                        "category": "acronym",
                        "severity": "medium",
                        "location": "全文",
                        "message": f"缩略语 {acr} 出现 {cnt} 次但未给出全称定义。",
                    })
                    undefined_count += 1

            # 6. 术语表覆盖校验：登记术语/符号/模型名未出现在最终正文（限 20 条）
            coverage_count = 0
            for term, src in glossary.items():
                if term and len(term) >= 2 and term not in latex_code and coverage_count < 20:
                    node_issues.append({
                        "category": "terminology",
                        "severity": "low",
                        "location": "glossary",
                        "message": f"登记术语/符号 '{term}'（来源 {src}）未出现在最终正文，可能写作时遗漏。",
                    })
                    coverage_count += 1

            # 7. 合并报告
            stats = {
                "terminology": sum(1 for i in node_issues if i.get("category") == "terminology"),
                "symbol": sum(1 for i in node_issues if i.get("category") == "symbol"),
                "acronym": sum(1 for i in node_issues if i.get("category") == "acronym"),
                "model_name": sum(1 for i in node_issues if i.get("category") == "model_name"),
                "citation": sum(1 for i in node_issues if i.get("category") == "citation"),
                "conclusion": sum(1 for i in node_issues if i.get("category") == "conclusion"),
            }
            has_high = any(i.get("severity") == "high" for i in node_issues)
            final_report = {
                "enabled": True,
                "passed": not has_high,
                "issue_count": len(node_issues),
                "stats": stats,
                "issues": node_issues,
                "glossary_size": len(glossary),
            }

            # 8. 持久化（镜像 fact_check 做法，写 final/terminology_consistency_report.json）
            if output_dir:
                try:
                    report_path = output_dir / "final" / "terminology_consistency_report.json"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(
                        json.dumps(final_report, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                    logger.info(f"[LangGraph:{task_id}] terminology_consistency: 报告已保存 {report_path}")
                except Exception as disk_exc:
                    logger.warning(f"[LangGraph:{task_id}] terminology_consistency 报告保存失败: {disk_exc}")

            # 6. 写回 state._quality_issues（无则新增）
            quality_issues = list(state.get("_quality_issues") or [])
            for iss in node_issues:
                quality_issues.append({"stage": "terminology_consistency", "task_id": task_id, **iss})

            # 9. 通知：未通过则列前 5 条 high/medium issue，通过则提示
            high_count = sum(1 for i in node_issues if i.get("severity") == "high")
            medium_count = sum(1 for i in node_issues if i.get("severity") == "medium")
            if high_count or medium_count:
                notable = [i for i in node_issues if i.get("severity") in ("high", "medium")][:5]
                summary_lines = "\n".join(
                    f"  - [{i.get('severity', '')}/{i.get('category', '')}] {i.get('message', '')}"
                    for i in notable
                )
                self._post_chat(
                    task_id, "coordinator",
                    f"⚠️ 术语一致性检查发现 {final_report['issue_count']} 个问题"
                    f"（高危 {high_count}，中危 {medium_count}）。\n"
                    + (summary_lines + "\n" if summary_lines else "")
                    + "报告已保存至 final/terminology_consistency_report.json，请人工审核。",
                )
            else:
                self._post_chat(task_id, "coordinator", "✅ 术语一致性检查通过")

            # 10. 写回 results（ref 方式，标准范式）+ _quality_issues + current_step
            ref_update = self._set_result(state, "terminology_consistency", final_report)
            logger.info(
                f"[LangGraph:{task_id}] terminology_consistency: passed={final_report['passed']} "
                f"issues={final_report['issue_count']} glossary={final_report['glossary_size']}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "_quality_issues": quality_issues,
                "current_step": "terminology_consistency_done",
            }

        except Exception as exc:
            logger.warning(
                f"[LangGraph:{task_id}] terminology_consistency 失败（降级放行）: {exc}",
                exc_info=True,
            )
            return {**state, "current_step": "terminology_consistency_failed"}

    async def _node_structure_coherence_check(self, state: TaskState) -> TaskState:
        """post 阶段·章节连贯性确定性闸门（插入 peer_review accept → fact_check 之间）。

        定位为 peer_review（语义性 LLM 评审）的确定性补充：peer_review 易漏判
        结构性缺陷（缺章/悬空引用/数字自相矛盾），本节点用确定性规则 + 符号审计兜底。
        新增 TaskState.structure_coherence_passed: bool（沿用 ast_audit_passed 范式）。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] structure_coherence_check start")

        results = self._resolve_results(state)
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        use_critique = state.get("use_critique", True)
        writer_output = results.get("writer_agent") or {}
        if not isinstance(writer_output, dict):
            writer_output = {}
        latex_code = writer_output.get("latex_code", "") or ""

        # ===== 层 0 · 前置闸门 =====
        if (
            workflow_type in ("quick", "code_focused")
            or not use_critique
            or not writer_output
            or not latex_code
        ):
            logger.info(
                f"[LangGraph:{task_id}] structure_coherence skipped "
                f"(workflow={workflow_type}, use_critique={use_critique}, has_latex={bool(latex_code)})"
            )
            self._post_chat(task_id, "coordinator", "ℹ️ 章节连贯性校验跳过（快速/代码模式或无论文输出）")
            return {
                **state,
                "current_step": "structure_coherence_skipped",
                "structure_coherence_passed": True,
            }

        self._update_progress(task_id, state.get("problem_text", ""), 82, "章节连贯性校验中")

        try:
            # ----- 局部确定性工具 -----
            def _norm_title(t: str) -> str:
                t = (t or "").strip()
                t = re.sub(r"^\d+([\.、]\d+)*\s*", "", t)
                return t.strip()

            def _section_of(ctx: str) -> str:
                cl = (ctx or "").lower()
                if "abstract" in cl or "摘要" in (ctx or ""):
                    return "abstract"
                if any(k in cl for k in ("result", "结果", "实验", "experiment")):
                    return "results"
                return "other"

            def _extract_section_body(title_substr: str) -> str:
                pat = (
                    r"\\section\{[^}]*" + re.escape(title_substr) + r"[^}]*\}"
                    r"(.*?)(?=\\section|\\end\{document\})"
                )
                m = re.search(pat, latex_code, re.DOTALL | re.IGNORECASE)
                return m.group(1) if m else ""

            def _parse_json_lenient(content: str) -> Dict[str, Any]:
                content = (content or "").strip()
                if content.startswith("```"):
                    lines = content.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    content = "\n".join(lines).strip()
                s = content.find("{")
                e = content.rfind("}")
                if s != -1 and e != -1 and e > s:
                    try:
                        return json.loads(content[s:e + 1])
                    except Exception:
                        return {}
                return {}

            missing_chapters: List[str] = []
            dangling_refs: List[str] = []
            dangling_cites: List[str] = []
            symbol_issues: List[Dict[str, Any]] = []
            numeric_clashes: List[Dict[str, Any]] = []
            llm_issues: List[Dict[str, Any]] = []

            # ===== 层 1 · 确定性结构校验（无 LLM）=====
            # 1a. 章节完整性与顺序（writer 内部 _global_consistency_check 只看 summary，不校验 LaTeX 真实结构）
            from ..agents.writer_agent import _resolve_chapter_plan, WriterAgent
            plan = _resolve_chapter_plan(template) or []
            found_sections = re.findall(r"\\section\{([^}]*)\}", latex_code)
            found_norm = [_norm_title(t) for t in found_sections]
            plan_titles: List[str] = []
            for ch in plan:
                if isinstance(ch, dict) and ch.get("section_level", 0) >= 1:
                    plan_titles.append(_norm_title(ch.get("title", "")))
            prev_idx = -1
            order_mismatch = False
            for pt in plan_titles:
                if not pt:
                    continue
                idx = None
                for i, fn in enumerate(found_norm):
                    if fn and (pt == fn or pt in fn or fn in pt):
                        idx = i
                        break
                if idx is None:
                    missing_chapters.append(pt)
                    continue
                if idx < prev_idx:
                    order_mismatch = True
                prev_idx = max(prev_idx, idx)

            # 1b. 悬空交叉引用（引用了不存在的 label）
            labels: set = set()
            for m in re.finditer(r"\\label\{([^}]*)\}", latex_code):
                for k in m.group(1).split(","):
                    k = k.strip()
                    if k:
                        labels.add(k)
            refs: set = set()
            for m in re.finditer(r"\\(?:ref|eqref|autoref)\{([^}]*)\}", latex_code):
                for k in m.group(1).split(","):
                    k = k.strip()
                    if k:
                        refs.add(k)
            dangling_refs = sorted(refs - labels)

            # 1c. 悬空文献引用（复用 WriterAgent._scan_cite_keys 静态方法）
            cite_keys = set(WriterAgent._scan_cite_keys(latex_code))
            citations = writer_output.get("citations", []) if isinstance(writer_output.get("citations"), list) else []
            defined_cites = {
                c.get("key") for c in citations
                if isinstance(c, dict) and c.get("key")
            }
            dangling_cites = sorted(cite_keys - defined_cites)

            # 1d. 符号一致性（符号在正文使用却未在符号说明章定义）
            paper_memory = writer_output.get("paper_memory", {})
            symbols = paper_memory.get("symbols", {}) if isinstance(paper_memory, dict) else {}
            notation_body = ""
            for kw in ("符号说明", "符号", "Notation", "notation", "Symbols", "Nomenclature"):
                notation_body = _extract_section_body(kw)
                if notation_body:
                    break
            for sym, info in (symbols or {}).items():
                if not isinstance(sym, str):
                    continue
                if sym in latex_code and sym not in notation_body:
                    symbol_issues.append({
                        "symbol": sym,
                        "severity": "warning",
                        "category": "symbol_undefined",
                        "message": f"符号 '{sym}' 在正文使用但未在符号说明章节中定义",
                    })

            # ===== 层 2 · 数值/声明一致性（复用 symbolic_auditor + fact_checker）=====
            from ..services.fact_checker import get_fact_checker
            from ..services.symbolic_auditor import (
                check_comparison_claims, check_metric_ranges, audit_experiment_results,
            )
            nums = get_fact_checker().extract_numbers_from_latex(latex_code) or {}

            # 2a. 跨章数字一致性（摘要 vs 结果，同一语义数字相对差异>5% → error）
            abstract_nums = [(c, v) for c, v in nums.items() if _section_of(c) == "abstract"]
            result_nums = [(c, v) for c, v in nums.items() if _section_of(c) == "results"]
            for ctx_a, va in abstract_nums:
                for ctx_b, vb in result_nums:
                    base = max(abs(va), abs(vb), 1e-9)
                    same_domain = (va <= 1.0 and vb <= 1.0) or (va > 1.0 and vb > 1.0)
                    if same_domain and abs(va - vb) / base > 0.05:
                        numeric_clashes.append({
                            "severity": "error",
                            "category": "numeric_clash",
                            "message": (
                                f"摘要与结果数字不一致: {va} vs {vb} (相对差异>5%) "
                                f"— '{ctx_a.strip()[:30]}' / '{ctx_b.strip()[:30]}'"
                            ),
                        })
                        break

            # 2b. 对比声明一致性（"X 优于 Y" 后跟两处数值 → 喂 check_comparison_claims）
            comparison_claims: List[Dict[str, Any]] = []
            for m in re.finditer(
                r"([\w一-龥\-]{2,30})\s*(?:优于|好于|超越|胜过|outperform\w*|better than)\s*([\w一-龥\-]{2,30})",
                latex_code,
            ):
                method_a, method_b = m.group(1).strip(), m.group(2).strip()
                window = latex_code[m.end():m.end() + 120]
                wlow = window.lower()
                metric = "accuracy"
                if any(k in wlow for k in ("loss", "mse", "mae", "rmse", "error", "误差", "损失")):
                    metric = "loss"
                found_nums = re.findall(r"-?\d+\.?\d*", window)
                if len(found_nums) >= 2:
                    try:
                        comparison_claims.append({
                            "method_a": method_a,
                            "method_b": method_b,
                            "metric": metric,
                            "value_a": float(found_nums[0]),
                            "value_b": float(found_nums[1]),
                            "claim": "A优于B",
                        })
                    except ValueError:
                        pass

            # 2c. 指标范围（accuracy>1 等，喂 check_metric_ranges）
            metrics: Dict[str, Any] = {}
            metric_patterns = {
                "accuracy": [r"accuracy\s*[=:：]?\s*(\d+\.?\d*)", r"准确率\s*[=:：]?\s*(\d+\.?\d*)"],
                "precision": [r"precision\s*[=:：]?\s*(\d+\.?\d*)", r"精确率\s*[=:：]?\s*(\d+\.?\d*)"],
                "f1_score": [r"f1[ _]?score\s*[=:：]?\s*(\d+\.?\d*)", r"f1\s*[=:：]?\s*(\d+\.?\d*)"],
                "auc": [r"\bauc\s*[=:：]?\s*(\d+\.?\d*)"],
            }
            for name, pats in metric_patterns.items():
                for pat in pats:
                    mm = re.search(pat, latex_code, re.IGNORECASE)
                    if mm:
                        try:
                            metrics[name] = (float(mm.group(1)), 0.0, 1.0)
                        except ValueError:
                            pass
                        break

            # 2d. 综合符号审计（复用 symbolic_auditor 三个函数）
            cc_findings = check_comparison_claims(comparison_claims) if comparison_claims else []
            mr_findings = check_metric_ranges(metrics) if metrics else []
            report_sym = audit_experiment_results(numbers=nums or None)
            sym_findings: List[Any] = list(cc_findings) + list(mr_findings)
            if report_sym is not None:
                sym_findings.extend(report_sym.findings)
            comparison_contradictions = [f for f in sym_findings if getattr(f, "category", "") == "comparison"]

            # ===== 层 3 · LLM 过渡连贯性审计（token 预算受限，缺口填补）=====
            from ..core.context_compressor import estimate_tokens
            chapters = writer_output.get("chapters", []) if isinstance(writer_output.get("chapters"), list) else []
            summaries = [
                {"title": c.get("title", ""), "summary": c.get("summary", "")}
                for c in chapters if isinstance(c, dict)
            ]
            writer_self_issues = writer_output.get("consistency_issues", []) if isinstance(writer_output.get("consistency_issues"), list) else []
            existing_issues_text = "\n".join(
                str((i.get("description") or i.get("message") or i) if isinstance(i, dict) else i)
                for i in writer_self_issues
            )
            token_cost = estimate_tokens(summaries) + estimate_tokens(existing_issues_text)
            llm_budget = 8000
            raw_issues: List[Dict[str, Any]] = []
            llm_ran = False
            if token_cost < llm_budget:
                agent = self.agents.get("peer_review_agent") or self.agents.get("research_agent")
                if agent is not None:
                    plan_order = "\n".join(
                        f"{i + 1}. {c.get('title', '')}" for i, c in enumerate(chapters)
                    )
                    summaries_text = "\n\n".join(
                        f"【{s['title']}】\n{s['summary']}" for s in summaries
                    )
                    prompt = (
                        "【章节过渡与逻辑主线审计】\n"
                        "只评价章节之间的过渡句、逻辑承接、逻辑主线是否连贯，不要评价文笔或用词。\n\n"
                        f"期望章节顺序：\n{plan_order}\n\n"
                        f"各章节摘要：\n{summaries_text}\n\n"
                        f"writer 自检已发现的问题（请勿重复）：\n{existing_issues_text or '（无）'}\n\n"
                        "返回 JSON：\n"
                        '{"issues":[{"type":"transition","severity":"warning",'
                        '"description":"...","affected_chapters":["..."],"suggestion":"..."}]}'
                    )
                    try:
                        resp = await agent.call_llm(
                            messages=[
                                {"role": "system", "content": "你是学术论文结构连贯性审稿人，只关注章节过渡与逻辑主线。"},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.2,
                        )
                        content = (
                            resp.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                            if isinstance(resp, dict) else "{}"
                        )
                        parsed = _parse_json_lenient(content)
                        raw_issues = parsed.get("issues", []) if isinstance(parsed, dict) else []
                        llm_ran = True
                    except Exception as llm_exc:
                        logger.warning(f"[LangGraph:{task_id}] structure_coherence LLM 审计失败: {llm_exc}")
                        raw_issues = []
            # 与 writer 自检去重合并（避免重复告警）
            existing_descs = {
                str((i.get("description") or i.get("message") or "")).strip().lower()[:60]
                for i in writer_self_issues if isinstance(i, dict)
            }
            raw_count = len(raw_issues)
            for li in raw_issues:
                if not isinstance(li, dict):
                    continue
                d = str(li.get("description", "")).strip().lower()[:60]
                if d and d in existing_descs:
                    continue
                llm_issues.append(li)

            # ===== 层 4 · 汇总与路由信号 =====
            findings: List[Dict[str, Any]] = []
            for mc in missing_chapters:
                findings.append({"severity": "error", "category": "missing_chapter", "message": f"缺失章节: {mc}"})
            if order_mismatch:
                findings.append({"severity": "warning", "category": "order_mismatch", "message": "章节顺序与模板规划不一致"})
            for dr in dangling_refs:
                findings.append({"severity": "error", "category": "dangling_ref", "message": f"悬空交叉引用: \\ref{{{dr}}} 无对应 \\label"})
            for dc in dangling_cites:
                findings.append({"severity": "warning", "category": "dangling_cite", "message": f"悬空文献引用: \\cite{{{dc}}} 未在 references 中定义"})
            findings.extend(symbol_issues)
            for f in sym_findings:
                findings.append({"severity": f.severity, "category": f.category, "message": f.message})
            findings.extend(numeric_clashes)
            for li in llm_issues:
                findings.append({
                    "severity": li.get("severity", "warning"),
                    "category": li.get("type", "transition"),
                    "message": li.get("description", ""),
                    "suggestion": li.get("suggestion", ""),
                })

            error_count = sum(1 for f in findings if f.get("severity") == "error")
            warning_count = sum(1 for f in findings if f.get("severity") == "warning")
            passed = error_count == 0
            score = max(0, 100 - error_count * 15 - warning_count * 5)

            report: Dict[str, Any] = {
                "task_id": task_id,
                "template": template,
                "passed": passed,
                "score": score,
                "finding_count": len(findings),
                "missing_chapters": missing_chapters,
                "order_mismatch": order_mismatch,
                "dangling_refs": dangling_refs,
                "dangling_cites": dangling_cites,
                "symbol_issues": symbol_issues,
                "numeric_clashes": numeric_clashes,
                "comparison_contradictions": [
                    {"severity": f.severity, "category": f.category, "message": f.message}
                    for f in comparison_contradictions
                ],
                "llm_issues": llm_issues,
                "writer_self_issues_merged": bool(llm_ran and len(llm_issues) < raw_count),
                "findings": findings,
            }

            ref_update = self._set_result(state, "structure_coherence", report)
            new_results = {**state.get("results", {}), **ref_update}

            # claims_trace（沿用 _route_peer_review 的 v8.1 追溯范式）
            trace_entry = {
                "timestamp": datetime.now().isoformat(),
                "step": "structure_coherence",
                "coherence_passed": passed,
                "finding_count": len(findings),
                "defect_breakdown": {
                    "missing_chapters": len(missing_chapters),
                    "dangling_refs": len(dangling_refs),
                    "dangling_cites": len(dangling_cites),
                    "symbol_issues": len(symbol_issues),
                    "numeric_clashes": len(numeric_clashes),
                    "comparison_contradictions": len(comparison_contradictions),
                    "llm_issues": len(llm_issues),
                    "errors": error_count,
                    "warnings": warning_count,
                },
            }
            claims_trace = list(state.get("claims_trace", []))
            claims_trace.append(trace_entry)

            # 校验问题写回 state._quality_issues（无则新增）
            quality_issues = list(state.get("_quality_issues", []))
            for f in findings:
                quality_issues.append({
                    "source": "structure_coherence",
                    "severity": f.get("severity", "warning"),
                    "category": f.get("category", ""),
                    "message": f.get("message", ""),
                })

            # 结构性回环：失败 + 可修订 → findings 转 review_feedback 写回 writer/peer_review 结果
            revision_count = writer_output.get("_revision_count", 0) or state.get("revision_count", 0)
            needs_revision = (not passed) and use_critique and revision_count < 3 and error_count > 0
            if needs_revision:
                suggested_edits = [
                    {"location": f.get("category", ""), "suggestion": f.get("message", "")}
                    for f in findings
                ]
                issues_list = [f.get("message", "") for f in findings]
                review_feedback = {
                    "recommendation": "revise",
                    "overall_score": round(score / 20.0, 2),
                    "scores": {},
                    "comments": {"major": issues_list, "minor": []},
                    "suggested_edits": suggested_edits,
                    "issues": issues_list,
                    "instruction": (
                        f"章节连贯性校验发现 {error_count} 处严重问题（score={score}），"
                        f"请根据以下 {len(suggested_edits)} 条结构/数字问题定向修订："
                    ),
                }
                updated_writer = {**writer_output, "_pending_structure_revisions": review_feedback}
                self._result_store.set(task_id, "writer_agent", updated_writer)
                new_results["writer_agent"] = _ref_key("writer_agent")
                pr = results.get("peer_review_agent")
                if isinstance(pr, dict):
                    synth_pr = {
                        **pr,
                        "recommendation": "revise",
                        "overall_score": max(1, min(4, round(score / 25.0))),
                        "suggested_edits": suggested_edits,
                        "comments": {"major": issues_list, "minor": []},
                        "scores": pr.get("scores", {}),
                        "_structure_coherence_synthesized": True,
                    }
                    self._result_store.set(task_id, "peer_review_agent", synth_pr)
                    new_results["peer_review_agent"] = _ref_key("peer_review_agent")
                logger.info(
                    f"[LangGraph:{task_id}] structure_coherence FAILED → 回环 writer 定向修订 "
                    f"(revision_count={revision_count}, score={score})"
                )

            if passed:
                self._post_chat(
                    task_id, "coordinator",
                    f"✅ 章节连贯性校验通过（{len(findings)} 处问题，score={score}）",
                )
            else:
                self._post_chat(
                    task_id, "coordinator",
                    f"⚠️ 章节连贯性问题：缺章 {len(missing_chapters)}/悬空引用 {len(dangling_refs)}/"
                    f"数字矛盾 {len(numeric_clashes)}（共 {len(findings)} 处，score={score}）",
                )

            logger.info(
                f"[LangGraph:{task_id}] structure_coherence_check done: "
                f"passed={passed}, score={score}, findings={len(findings)} "
                f"(errors={error_count}, warnings={warning_count}), needs_revision={needs_revision}"
            )

            return {
                **state,
                "results": new_results,
                "current_step": "structure_coherence_check",
                "structure_coherence_passed": passed,
                "claims_trace": claims_trace,
                "_quality_issues": quality_issues,
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] structure_coherence_check 异常: {e}", exc_info=True)
            return {**state, "current_step": "structure_coherence_check", "structure_coherence_passed": True}

    async def _node_abstract_quality_check(self, state: TaskState) -> TaskState:
        """摘要完整性校验（位于 writer 与 peer_review 之间）。

        检查 writer 产出的摘要是否：
          1) 非空且无占位符；
          2) 字数落在模板要求的区间内；
          3) 覆盖全部子问题（按 id/序号/名称点名）；
          4) 覆盖 solver.numerical_results 的关键数值（复用 FactChecker 做容差匹配）；
          5) 提及 modeler 的多数模型/方法。

        数字来源全部为 solver.numerical_results，不编造；必要时将缺失数值追加到摘要末尾。
        失败时 fail-forward（不阻塞主流程），校验问题写回 state._quality_issues。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] abstract_quality_check: start")
        try:
            results = self._resolve_results(state)
            writer_output = results.get("writer_agent", {}) or {}
            abstract = writer_output.get("abstract", "") if isinstance(writer_output, dict) else ""
            template = state.get("paper_template", "math_modeling")
            sub_problems = state.get("sub_problems", []) or []
            revision_count = state.get("revision_count", 0)

            self._update_progress(task_id, state.get("problem_text", ""), 72, "摘要完整性校验中")

            issues: List[Dict[str, Any]] = []
            score = 100.0

            # Check1 非空 & 无占位符
            placeholders = ["待补充", "XXX", "TODO", "（摘要待补充）", "内容待补充", "待填写", "[摘要]"]
            found_ph = [p for p in placeholders if p in abstract]
            if not abstract or len(abstract) < 50:
                issues.append({"severity": "error", "category": "empty",
                               "message": "摘要为空或过短(<50字)"})
                score -= 30
            if found_ph:
                issues.append({"severity": "error", "category": "placeholder",
                               "message": f"摘要含占位符: {found_ph}"})
                score -= 20

            # Check2 字数范围（按模板）
            ranges = {"math_modeling": (300, 1000), "coursework": (200, 800),
                      "financial_analysis": (200, 800), "research_survey": (300, 1200)}
            lo, hi = ranges.get(template, (300, 1000))
            n = len(abstract)
            if n < lo:
                issues.append({"severity": "warning", "category": "length",
                               "message": f"摘要 {n} 字 < 下限 {lo}"})
                score -= 10
            elif n > hi:
                issues.append({"severity": "warning", "category": "length",
                               "message": f"摘要 {n} 字 > 上限 {hi}"})
                score -= 5

            # Check3 子问题覆盖：每个子问题是否在摘要中被点名
            cn_num = ["一", "二", "三", "四", "五", "六", "七", "八"]
            covered: List[Any] = []
            missing_sp: List[Any] = []
            for sp in sub_problems:
                sp_id = sp.get("id")
                name = sp.get("name", sp.get("description", ""))
                # idx 支持整数 id 与可解析为整数的 id
                idx = None
                if isinstance(sp_id, int) and 1 <= sp_id <= 8:
                    idx = sp_id - 1
                else:
                    try:
                        sid = int(sp_id)
                        if 1 <= sid <= 8:
                            idx = sid - 1
                    except (TypeError, ValueError):
                        idx = None
                pats = [f"问题{sp_id}", f"问题 {sp_id}",
                        f"第{cn_num[idx]}问" if idx is not None else "",
                        f"针对问题{sp_id}", f"针对问题 {sp_id}"]
                hit = any(p and p in abstract for p in pats) or (bool(name) and name[:4] in abstract)
                (covered if hit else missing_sp).append(sp_id)
            if sub_problems and missing_sp:
                ratio = len(covered) / len(sub_problems)
                sev = "error" if ratio < 0.8 else "warning"
                issues.append({"severity": sev, "category": "coverage",
                               "message": f"摘要未覆盖 {len(missing_sp)}/{len(sub_problems)} 个子问题: {missing_sp}"})
                score -= 20 if sev == "error" else 8

            # Check4 数值结果覆盖 —— 复用 FactChecker（不编造）
            fc = get_fact_checker()
            solver_output = results.get("solver_agent", {}) or {}
            solves = solver_output.get("sub_problem_solutions", []) if isinstance(solver_output, dict) else []
            abstract_numbers = fc.extract_numbers_from_latex(abstract)  # Dict[ctx, value]
            key_nums: List[tuple] = []
            for sol in solves:
                # 兼容两种结构：sol.numerical_results 与 sol.results.numerical_results
                nr = sol.get("numerical_results")
                if not isinstance(nr, dict) or not nr:
                    res = sol.get("results", {})
                    nr = res.get("numerical_results", {}) if isinstance(res, dict) else {}
                if not isinstance(nr, dict):
                    nr = {}
                for k, v in nr.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 1e9 and k != "状态":
                        key_nums.append((str(k), float(v)))
            missing_nums = [(k, v) for k, v in key_nums
                            if not any(fc._relative_diff(v, av) <= 0.05
                                       for av in abstract_numbers.values())]
            if key_nums and missing_nums:
                mr = len(missing_nums) / len(key_nums)
                sev = "error" if mr > 0.5 else "warning"
                issues.append({"severity": sev, "category": "numerical",
                               "message": f"摘要缺失 {len(missing_nums)}/{len(key_nums)} 个关键数值: {[k for k, _ in missing_nums[:5]]}"})
                score -= 20 if sev == "error" else 8

            # Check5 方法/模型提及
            modeler_output = results.get("modeler_agent", {}) or {}
            models = modeler_output.get("sub_problem_models", []) if isinstance(modeler_output, dict) else []
            missing_methods: List[str] = []
            for m in models:
                mname = m.get("model_name", "") or m.get("model_type", "")
                alg = m.get("algorithm", {})
                alg_name = alg.get("name", "") if isinstance(alg, dict) else str(alg)
                tokens = [t for t in [mname, alg_name] if t]
                if tokens and not any(t in abstract for t in tokens):
                    missing_methods.append(mname or alg_name)
            if models and len(missing_methods) > len(models) * 0.5:
                issues.append({"severity": "warning", "category": "method",
                               "message": f"摘要未提及多数模型/方法: {missing_methods[:5]}"})
                score -= 8

            score = max(0.0, score)
            hard_fail_cats = {"empty", "placeholder"}
            passed = score >= 70 and not any(
                i["severity"] == "error" and i["category"] in (hard_fail_cats | {"coverage", "numerical"})
                for i in issues
            )

            # 自动补全：把缺失的关键数值追加到摘要末尾（数字全部来自 solver.numerical_results，不编造）
            abstract_patched = abstract
            supplemented = False
            if missing_nums and not passed and len(abstract) < hi:
                supplement = "主要结果：" + "；".join(f"{k}={v:g}" for k, v in missing_nums[:6]) + "。"
                abstract_patched = abstract.rstrip("。") + "。" + supplement
                supplemented = True

            # 写回 writer_agent（含质量报告 + 补全后摘要），供下游 peer_review/fact_check 使用
            updated = dict(writer_output) if isinstance(writer_output, dict) else {}
            if supplemented:
                updated["abstract"] = abstract_patched
            updated["_abstract_quality"] = {
                "score": round(score, 1), "passed": passed, "issues": issues,
                "coverage": {"covered": len(covered), "total": len(sub_problems), "missing": missing_sp},
                "numerical": {"key_total": len(key_nums), "missing": len(missing_nums)},
                "supplemented": supplemented, "revision_count": revision_count,
                "checked_at": datetime.now().isoformat(),
            }
            ref_update = self._set_result(state, "writer_agent", updated)

            # 校验问题写回 state._quality_issues（无则新增）
            quality_issues = list(state.get("_quality_issues", []))
            quality_issues.append({
                "node": "abstract_quality_check",
                "task_id": task_id,
                "passed": passed,
                "score": round(score, 1),
                "issues": issues,
                "supplemented": supplemented,
                "checked_at": datetime.now().isoformat(),
            })

            self._post_chat(
                task_id, "abstract_check",
                f"{'✅' if passed else '⚠️'} 摘要完整性{'通过' if passed else '不达标'} (score={score:.0f})"
                + (f"，已自动补全 {len(missing_nums)} 个数值" if supplemented else "")
            )
            logger.info(
                f"[LangGraph:{task_id}] abstract_quality_check: passed={passed}, "
                f"score={score:.1f}, issues={len(issues)}, supplemented={supplemented}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "current_step": "abstract_quality_check_done",
                "abstract_quality_passed": passed,
                "_quality_issues": quality_issues,
            }
        except Exception as exc:
            # 校验本身异常 → fail-forward，不阻塞主流程，不因 checker 崩溃打回 writer
            logger.warning(f"[LangGraph:{task_id}] abstract_quality_check failed: {exc}", exc_info=True)
            return {**state, "current_step": "abstract_quality_check_failed", "abstract_quality_passed": True}

    async def _node_final_polish(self, state: TaskState) -> TaskState:
        """终稿润色：确定性 LaTeX 修正 + 悬空引用清理 + 数值护栏 + 可选 LLM 润色。

        位于 fact_check -> compliance_check 之后、summary 之前，保证润色基于已过
        数值核查与（金融模板）已清洗的文本。元数据写回 writer_agent 结果，沿用
        compliance_check 范式；校验问题追加到 state["_quality_issues"]。
        """
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] final_polish: 终稿润色开始")
        try:
            results = self._resolve_results(state)
            writer_output = results.get("writer_agent", {}) or {}
            if not isinstance(writer_output, dict):
                writer_output = {}
            # compliance_check 若已写回 _compliance_cleaned 文本，此处天然取到清洗后版本
            latex = writer_output.get("latex_code", "")
            if not latex:
                logger.info(f"[LangGraph:{task_id}] final_polish: 无 LaTeX 稿件，跳过润色")
                return {**state, "current_step": "final_polish_skipped"}

            self._update_progress(task_id, state["problem_text"], 88, "终稿润色中")
            template = state.get("paper_template", "math_modeling")
            report: Dict[str, Any] = {
                "deterministic_fixes": [],
                "citation_issues": [],
                "numeric_guard": None,
                "llm_polish": None,
            }

            # ===== Step 2: 确定性 LaTeX 修正（无 LLM，纯正则/计数）=====
            polished, fixes = self._polish_latex_deterministic(latex)
            report["deterministic_fixes"] = fixes

            # ===== Step 3: 引用清洗（复用 writer_agent._scan_cite_keys）=====
            agent = self.agents.get("writer_agent")
            cite_keys = []
            if agent is not None and hasattr(agent, "_scan_cite_keys"):
                cite_keys = agent._scan_cite_keys(polished)
            citations_src = writer_output.get("citations")
            if not citations_src:
                citations_src = (writer_output.get("paper_memory", {}) or {}).get("citations", [])
            bib_keys = {
                c.get("key") for c in (citations_src or [])
                if isinstance(c, dict) and c.get("key")
            }
            dangling = [k for k in cite_keys if k not in bib_keys]
            if dangling:
                polished = self._strip_dangling_cites(polished, dangling)
                report["citation_issues"] = dangling

            # ===== Step 4: 数值完整性护栏（复用 get_fact_checker）=====
            fc = get_fact_checker()
            try:
                output_dir = get_project_output_dir(state.get("project_name"))
            except Exception:
                output_dir = None
            solves = self._load_solves(output_dir, results)
            latex_nums = fc.extract_numbers_from_latex(polished)
            solve_nums = fc.extract_numbers_from_solves(solves)
            drift = [
                i for i in fc.compare(latex_nums, solve_nums, 0.05)
                if i.relative_diff is None or i.relative_diff > 0.05
            ]
            baseline = (results.get("fact_checker", {}) or {}).get("issue_count", 0)
            drift_count = len(drift)
            # passed：无漂移 且 未在 fact_check 基线之外新增漂移
            numeric_passed = (drift_count == 0) and (drift_count <= baseline)
            report["numeric_guard"] = {
                "drift_count": drift_count,
                "passed": numeric_passed,
                "baseline_issue_count": baseline,
            }

            # ===== Step 5: 可选 LLM 润色（use_critique 闸门 + 必须过数值护栏）=====
            if state.get("use_critique", True) and numeric_passed:
                try:
                    llm_polished = await self._llm_polish_abstract(polished, writer_output, template)
                    if llm_polished and llm_polished != polished:
                        if self._numbers_unchanged(polished, llm_polished, fc):
                            polished = llm_polished
                            report["llm_polish"] = "applied"
                        else:
                            report["llm_polish"] = "reverted(numeric drift)"
                    else:
                        report["llm_polish"] = "skipped(no change)"
                except Exception as e:
                    report["llm_polish"] = f"failed:{e}"
                    logger.warning(f"[LangGraph:{task_id}] final_polish LLM 润色失败: {e}")
            else:
                report["llm_polish"] = "skipped(guard/critique off)"

            # ===== 写回 writer_agent 结果（镜像 compliance_check）=====
            updated = {
                **writer_output,
                "latex_code": polished,
                "_final_polished": True,
                "_polish_report": report,
                "_polished_at": datetime.now().isoformat(),
            }
            ref_update = self._set_result(state, "writer_agent", updated)

            # ===== 落盘：final/main.tex 与 papers/paper_{task_id}.tex 同步 =====
            try:
                if output_dir is not None:
                    final_dir = output_dir / "final"
                    final_dir.mkdir(parents=True, exist_ok=True)
                    (final_dir / "main.tex").write_text(polished, encoding="utf-8")
                    papers_dir = output_dir / "papers"
                    papers_dir.mkdir(parents=True, exist_ok=True)
                    (papers_dir / f"paper_{task_id}.tex").write_text(polished, encoding="utf-8")
                    logger.info(f"[LangGraph:{task_id}] final_polish: 已同步润色稿到磁盘")
            except Exception as disk_exc:
                logger.warning(f"[LangGraph:{task_id}] final_polish 磁盘回写失败: {disk_exc}")

            # ===== 校验问题写回 state._quality_issues（无则新增）=====
            quality_issues: List[Dict[str, Any]] = list(state.get("_quality_issues", []) or [])
            for f in fixes:
                if f.get("severity") in ("error", "warning"):
                    quality_issues.append({
                        "stage": "final_polish",
                        "category": f.get("category", "latex"),
                        "severity": f.get("severity"),
                        "detail": f.get("detail", ""),
                    })
            if dangling:
                quality_issues.append({
                    "stage": "final_polish", "category": "dangling_cite",
                    "detail": f"{len(dangling)} 处悬空引用已清理: {', '.join(dangling[:5])}",
                })
            if not numeric_passed:
                quality_issues.append({
                    "stage": "final_polish", "category": "numeric_drift",
                    "detail": f"数值护栏告警：drift_count={drift_count}, baseline={baseline}",
                })

            self._post_chat(
                task_id, "final_polish",
                f"✨ 终稿润色完成：{len(fixes)} 处格式修正，{len(dangling)} 处悬空引用清理，"
                f"数值护栏{'通过' if report['numeric_guard'].get('passed') else '告警'}，"
                f"LLM润色={report['llm_polish']}",
            )
            logger.info(
                f"[LangGraph:{task_id}] final_polish: 完成 fixes={len(fixes)} "
                f"dangling={len(dangling)} drift={drift_count} llm={report['llm_polish']}"
            )

            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "_quality_issues": quality_issues,
                "current_step": "final_polish_done",
            }
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] final_polish 失败: {e}", exc_info=True)
            return {**state, "current_step": "final_polish_failed"}

    # ------------------------------------------------------------------
    # 节点辅助方法（紧邻 _save_output_files 之后）
    # ------------------------------------------------------------------

    def _polish_latex_deterministic(self, latex: str) -> Tuple[str, List[Dict[str, Any]]]:
        """确定性 LaTeX 修正（无 LLM，纯正则/计数）。

        返回 (polished, fixes)：fixes 为每处修正的记录 dict。
        (a) 中文引号规范：``...'' -> " "、`...' -> ' '（仅中文上下文）；
        (b) 去重 \\end{document}（只保留最后1个）、去重连续 \\maketitle；
        (c) 压缩 ≥3 连续空行为 2；
        (d) 环境配对校验：统计 \\begin{env}/\\end{env} 数量，不匹配记入 fixes。
        """
        fixes: List[Dict[str, Any]] = []
        if not latex:
            return latex, fixes
        cjk = re.compile(r"[一-鿿]")
        polished = latex

        # (a) 中文引号规范——先处理双引号 ``...'' ，再处理单引号 `...'
        def _dbl(m: re.Match) -> str:
            pre = polished[max(0, m.start() - 30):m.start()]
            post = polished[m.end():min(len(polished), m.end() + 30)]
            if cjk.search(pre) or cjk.search(post):
                fixes.append({
                    "category": "chinese_quote", "severity": "warning",
                    "detail": f"``...'' -> 中文双引号: {m.group(1)[:30]}",
                })
                return f"“{m.group(1)}”"
            return m.group(0)
        polished = re.sub(r"``(.+?)''", _dbl, polished, flags=re.DOTALL)

        def _sgl(m: re.Match) -> str:
            pre = polished[max(0, m.start() - 30):m.start()]
            post = polished[m.end():min(len(polished), m.end() + 30)]
            if cjk.search(pre) or cjk.search(post):
                fixes.append({
                    "category": "chinese_quote", "severity": "warning",
                    "detail": f"`...' -> 中文单引号: {m.group(1)[:30]}",
                })
                return f"‘{m.group(1)}’"
            return m.group(0)
        polished = re.sub(r"(?<!`)`([^'\n]+?)'(?!')", _sgl, polished)

        # (b) 去重 \end{document}（只保留最后1个）
        end_docs = list(re.finditer(r"\\end\{document\}", polished))
        if len(end_docs) > 1:
            for m in reversed(end_docs[:-1]):
                polished = polished[:m.start()] + polished[m.end():]
            fixes.append({
                "category": "dup_end_document", "severity": "warning",
                "detail": f"removed {len(end_docs) - 1} duplicate \\end{{document}}",
            })
        # 去重连续 \maketitle
        polished, n = re.subn(r"(\\maketitle\s*){2,}", r"\1", polished)
        if n:
            fixes.append({
                "category": "dup_maketitle", "severity": "info",
                "detail": f"dedup {n} block(s) of consecutive \\maketitle",
            })

        # (c) 压缩 ≥3 连续空行（>=4 个换行）为 2（3 个换行）
        polished, n = re.subn(r"\n{4,}", "\n\n\n", polished)
        if n:
            fixes.append({
                "category": "blank_lines", "severity": "info",
                "detail": f"compressed {n} block(s) of >=3 consecutive blank lines",
            })

        # (d) 环境配对校验
        envs = ["abstract", "table", "tabular", "figure", "equation",
                "align", "thebibliography", "appendices"]
        for env in envs:
            begins = len(re.findall(r"\\begin\{" + re.escape(env) + r"\}", polished))
            ends = len(re.findall(r"\\end\{" + re.escape(env) + r"\}", polished))
            if begins != ends:
                fixes.append({
                    "category": "env_mismatch", "severity": "error",
                    "detail": f"\\begin{{{env}}}={begins} vs \\end{{{env}}}={ends}",
                })
        return polished, fixes

    def _strip_dangling_cites(self, latex: str, dangling: List[str]) -> str:
        """移除/收紧 \\cite{...} 中无 bib 条目的悬空引用 key。

        \\cite{a,b,c} 中移除 dangling key，保留有效 key；若全部悬空则删除整个 \\cite。
        """
        if not latex or not dangling:
            return latex
        dangling_set = set(dangling)

        def _filter(m: re.Match) -> str:
            cmd = m.group(1)
            keys = [k.strip() for k in m.group(2).split(",") if k.strip()]
            kept = [k for k in keys if k not in dangling_set]
            if not kept:
                return ""
            return f"{cmd}{{{','.join(kept)}}}"

        return re.sub(r"(\\cite[a-z]*)\{([^}]+)\}", _filter, latex)

    def _load_solves(self, output_dir, results: Dict[str, Any]) -> Any:
        """加载 solves：优先 final/solves.json，回退 solver_agent.sub_problem_solutions。"""
        if output_dir is not None:
            solves_file = output_dir / "final" / "solves.json"
            if not solves_file.exists():
                solves_file = output_dir / "solves.json"
            if solves_file.exists():
                try:
                    return json.loads(solves_file.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"_load_solves: failed to read {solves_file}: {e}")
        solver_output = results.get("solver_agent") or {}
        if isinstance(solver_output, dict):
            return solver_output.get("sub_problem_solutions", [])
        return []

    async def _llm_polish_abstract(self, polished: str, writer_output: Dict[str, Any], template: str) -> str:
        """受限 LLM 润色：只许修摘要/标题/错别字/表述，禁改数字与 \\cite。

        用 writer_agent.call_llm 发一个受限 prompt，解析返回 JSON 的 latex_code。
        异常向上抛出，由调用方捕获记为 failed。
        """
        agent = self.agents.get("writer_agent")
        if agent is None:
            return polished
        abstract = writer_output.get("abstract", "") or ""
        title = writer_output.get("title", "") or ""
        prompt = (
            "你是学术论文终稿润色助手。只允许做以下受限修改：\n"
            "1. 润色摘要(abstract)与标题(title)的中文表述、修正错别字；\n"
            "2. 改善行文流畅度与用词准确性。\n"
            "严禁改动任何数字、\\cite 引用、公式、表格数据、图表内容。\n\n"
            f"当前标题：{title}\n"
            f"当前摘要：{abstract}\n"
            f"当前 LaTeX 全文：\n{polished}\n\n"
            "返回 JSON：{{\"latex_code\": \"润色后的完整LaTeX源代码\"}}"
        )
        messages = [
            {"role": "system", "content": "你是严谨的论文润色编辑，只做表述层面优化，绝不改动数字与引用。"},
            {"role": "user", "content": prompt},
        ]
        response = await agent.call_llm(messages=messages, temperature=0.2)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = agent._extract_json(content) if hasattr(agent, "_extract_json") else {}
        new_latex = parsed.get("latex_code", "") if isinstance(parsed, dict) else ""
        new_latex = (new_latex or "").strip()
        return new_latex if new_latex else polished

    def _numbers_unchanged(self, before: str, after: str, fc) -> bool:
        """判定润色前后 LaTeX 数字集合是否一致（防 LLM 引入数据漂移/造假）。"""
        try:
            before_nums = set(fc.extract_numbers_from_latex(before).values())
            after_nums = set(fc.extract_numbers_from_latex(after).values())
            return before_nums == after_nums
        except Exception:
            return False


    # ------------------------------------------------------------------
    # Graph 构建
    # ------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(TaskState)

        # 节点注册
        builder.add_node("requirement_decomposition", self._node_requirement_decomposition)
        builder.add_node("preflight_decision", self._node_preflight_decision)
        builder.add_node("analyzer", self._node_analyzer)
        builder.add_node("research_vote", self._node_research_vote)  # v8.4.3: 多智能体投票决策（是否联网检索论文/代码）
        builder.add_node("parallel_analysis", self._node_parallel_analysis)  # v7.1: 并行分析（内部调用 data/research/innovation）
        builder.add_node("discuss_approach", self._node_discuss_approach)
        builder.add_node("modeler", self._node_modeler)
        builder.add_node("algorithm_engineer", self._node_algorithm_engineer)
        builder.add_node("financial_analyst", self._node_financial_analyst)
        builder.add_node("iterative_solver", self._node_iterative_solver)
        builder.add_node("writer", self._node_writer)
        builder.add_node("peer_review", self._node_peer_review)
        builder.add_node("experiment", self._node_experiment)
        builder.add_node("figure", self._node_figure)
        builder.add_node("fact_check", self._node_fact_check)
        builder.add_node("compliance_check", self._node_compliance_check)  # v8.0: 金融合规审查
        builder.add_node("summary", self._node_summary)
        builder.add_node("cannot_solve", self._node_cannot_solve)
        builder.add_node("self_collect", self._node_self_collect)
        builder.add_node("wait_user", self._node_wait_user)
        # v8.2: 防沙箱死亡螺旋三机制节点
        builder.add_node("coder_agent_node", self._node_coder_agent)
        builder.add_node("ast_audit_node", self._node_ast_audit)
        builder.add_node("sandbox_execution_node", self._node_sandbox_execution)
        builder.add_node("reviewer_reflection_node", self._node_reviewer_reflection)
        # v8.4: 17 个新节点（pre/mid/post 阶段质量门与审查）
        builder.add_node("requirement_validation", self._node_requirement_validation)  # pre: 需求分解后不验完整性
        builder.add_node("data_quality_check", self._node_data_quality_check)  # pre: 数据缺失/脏数据无门禁
        builder.add_node("literature_dedup", self._node_literature_dedup)  # pre: 文献重复风险
        builder.add_node("novelty_check", self._node_novelty_check)  # pre: 创新点是否已被覆盖
        builder.add_node("method_feasibility", self._node_method_feasibility)  # pre: 方法可行性预评估
        builder.add_node("context_compression_node", self._node_context_compression)  # mid: 上下文压缩未在图里显式触发
        builder.add_node("code_style_check", self._node_code_style_check)  # mid: 代码风格不一致
        builder.add_node("reproducibility_check", self._node_reproducibility_check)  # mid: 方法可复现性（审查核心缺失）
        builder.add_node("formula_validity_check", self._node_formula_validity_check)  # post: LaTeX 公式有效性
        builder.add_node("table_consistency_check", self._node_table_consistency_check)  # post: 表格内部一致性
        builder.add_node("figure_caption_check", self._node_figure_caption_check)  # post: 图表说明与正文一致
        builder.add_node("citation_density_check", self._node_citation_density_check)  # post: 引用密度合理性
        builder.add_node("reference_completeness", self._node_reference_completeness)  # post: 参考文献完整性
        builder.add_node("terminology_consistency", self._node_terminology_consistency)  # post: 术语统一性
        builder.add_node("structure_coherence_check", self._node_structure_coherence_check)  # post: 章节连贯性
        builder.add_node("abstract_quality_check", self._node_abstract_quality_check)  # post: 摘要完整性
        builder.add_node("final_polish", self._node_final_polish)  # post: 终稿润色
        # 注意：data、research、innovation 节点已移除（由 parallel_analysis 内部并行调用）

        # 入口
        builder.set_entry_point("requirement_decomposition")

        # 条件边
        builder.add_conditional_edges(
            "preflight_decision",
            self._route_preflight,
            {
                "analyze_only": "analyzer",
                "standard": "analyzer",
                "quick": "analyzer",
                "deep_research": "analyzer",
                "code_focused": "analyzer",
                "research_paper": "analyzer",
                "self_collect": "self_collect",
                "abort": "cannot_solve",
            },
        )

        builder.add_conditional_edges(
            "peer_review",
            self._route_peer_review,
            {
                "revise": "writer",
                "experiment": "experiment",  # v8.1: 缺少实验/消融不足
                "iterative_solver": "iterative_solver",  # v8.1: 数字矛盾/结果不合理
                "accept": "fact_check",
                "wait_user": "wait_user",
                "abort": "cannot_solve",
            },
        )

        # v8.2: 统一路由 — iterative_solver 完成后决定下一步
        # 合并原 _route_solver（重试/升级）和 _route_to_sandbox_or_writer（安全壳流程）
        builder.add_conditional_edges(
            "iterative_solver",
            self._route_after_solver,
            {
                "retry": "iterative_solver",
                "escalate": "cannot_solve",
                "abort": "cannot_solve",
                "coder_agent": "coder_agent_node",
                "ast_audit": "ast_audit_node",
            },
        )

        # 条件边：analyzer → research_vote（v8.4.3: 多智能体投票决策是否联网检索）
        # 投票节点内部含快路径（纯建模题 0 LLM）与降级（LLM 失败回退白名单），
        # 无论 analyzer 结论如何都先过投票节点，再进并行分析。
        builder.add_edge("analyzer", "research_vote")
        builder.add_edge("research_vote", "parallel_analysis")

        # 并行分析 → 条件路由到建模 Agent
        builder.add_conditional_edges(
            "parallel_analysis",
            self._route_after_parallel_analysis,
            {
                "modeler": "modeler",
                "algorithm_engineer": "algorithm_engineer",
                "financial_analyst": "financial_analyst",
                "writer": "writer",
                "discuss": "discuss_approach",
            },
        )

        # 条件边：discuss_approach
        builder.add_conditional_edges(
            "discuss_approach",
            self._route_after_discuss_approach,
            {
                "modeler": "modeler",
                "algorithm_engineer": "algorithm_engineer",
                "financial_analyst": "financial_analyst",
                "writer": "writer",
            },
        )

        # 建模节点 → solver（非 CCF-A）或 experiment（CCF-A）
        builder.add_conditional_edges(
            "modeler",
            self._route_to_experiment_or_solver,
            {"experiment": "experiment", "iterative_solver": "iterative_solver"},
        )
        builder.add_conditional_edges(
            "algorithm_engineer",
            self._route_to_experiment_or_solver,
            {"experiment": "experiment", "iterative_solver": "iterative_solver"},
        )
        builder.add_conditional_edges(
            "financial_analyst",
            self._route_to_experiment_or_solver,
            {"experiment": "experiment", "iterative_solver": "iterative_solver"},
        )

        # 条件边：experiment → 迭代或继续
        builder.add_conditional_edges(
            "experiment",
            self._route_after_experiment,
            {
                "experiment": "experiment",   # 迭代优化
                "iterative_solver": "iterative_solver",  # 正常流程
            },
        )

        # v8.2: 防沙箱死亡螺旋流程（所有模板都接入安全壳保护）
        # CCF-A 模板: iterative_solver → coder_agent → ast_audit → sandbox → reviewer → figure → writer
        # 非 CCF-A 模板: iterative_solver → ast_audit → sandbox → figure → writer
        # 注：iterative_solver 的路由已在上方统一定义（_route_after_solver）
        builder.add_edge("coder_agent_node", "ast_audit_node")  # CCF-A: coder → ast_audit
        builder.add_edge("ast_audit_node", "code_style_check")  # mid: 代码风格检查（旁路接入 sandbox 链）
        builder.add_edge("code_style_check", "sandbox_execution_node")  # 所有模板: ast_audit → code_style → sandbox
        builder.add_conditional_edges(
            "sandbox_execution_node",
            self._route_after_sandbox,
            {
                "reviewer": "reviewer_reflection_node",  # CCF-A: 进入越狱熔断
                "figure": "figure",                      # 非 CCF-A: 直接进入图表
            },
        )
        builder.add_conditional_edges(
            "reviewer_reflection_node",
            self._route_after_reviewer,
            {
                "coder_agent": "coder_agent_node",
                "figure": "figure",
            },
        )

        # v8.4: figure → context_compression → literature_dedup → method_feasibility → writer（旁路接入，不进条件路由）
        builder.add_edge("figure", "context_compression_node")
        builder.add_edge("context_compression_node", "literature_dedup")
        builder.add_edge("literature_dedup", "method_feasibility")
        builder.add_edge("method_feasibility", "writer")
        # v8.4: writer → [10 个 post 质量门] → novelty_check → peer_review（替换原 writer→peer_review）
        builder.add_edge("writer", "formula_validity_check")
        builder.add_edge("formula_validity_check", "table_consistency_check")
        builder.add_edge("table_consistency_check", "figure_caption_check")
        builder.add_edge("figure_caption_check", "citation_density_check")
        builder.add_edge("citation_density_check", "reference_completeness")
        builder.add_edge("reference_completeness", "terminology_consistency")
        builder.add_edge("terminology_consistency", "structure_coherence_check")
        builder.add_edge("structure_coherence_check", "abstract_quality_check")
        builder.add_edge("abstract_quality_check", "final_polish")
        builder.add_edge("final_polish", "novelty_check")
        builder.add_edge("novelty_check", "peer_review")
        # v8.4: fact_check → reproducibility_check → compliance_check → summary（旁路接入可复现性审查）
        builder.add_edge("fact_check", "reproducibility_check")
        builder.add_edge("reproducibility_check", "compliance_check")  # v8.0: fact_check → reproducibility → compliance_check → summary
        builder.add_edge("compliance_check", "summary")
        builder.add_edge("cannot_solve", "summary")
        builder.add_edge("summary", END)
        builder.add_edge("self_collect", "preflight_decision")
        # v7.2: wait_user 不再连接到 END（避免流程中断）
        # 改为自循环：等待用户输入后重新评估 peer_review
        builder.add_edge("wait_user", "peer_review")

        # v8.4: requirement_decomposition → requirement_validation → data_quality_check → preflight_decision
        builder.add_edge("requirement_decomposition", "requirement_validation")
        builder.add_edge("requirement_validation", "data_quality_check")
        builder.add_edge("data_quality_check", "preflight_decision")

        return builder.compile()

    # ------------------------------------------------------------------
    # 需求分解节点
    # ------------------------------------------------------------------
    async def _node_requirement_decomposition(self, state: TaskState) -> TaskState:
        """长提示词自动分解（>3000字符时触发）。"""
        task_id = state["task_id"]
        problem_text = state.get("problem_text", "")

        if len(problem_text) < 3000:
            logger.info(f"[LangGraph:{task_id}] 问题文本较短({len(problem_text)}字)，跳过需求分解")
            return {**state, "requirement_plan": None, "current_step": "requirement_decomposition_skip"}

        logger.info(f"[LangGraph:{task_id}] 问题文本较长({len(problem_text)}字)，启动需求分解")
        try:
            from .requirement_decomposer import RequirementDecomposerAgent
            agent = RequirementDecomposerAgent()
            context = {
                "task_id": task_id,
                "project_name": state.get("project_name"),
                "problem_text": problem_text,
                "files": state.get("files", []),
            }
            plan = await agent.execute(task_input={}, context=context)

            if plan and not plan.get("_fallback"):
                logger.info(f"[LangGraph:{task_id}] 需求分解完成: {len(plan.get('subtasks', []))} 个子任务")
                return {**state, "requirement_plan": plan, "current_step": "requirement_decomposition_done"}
            else:
                logger.info(f"[LangGraph:{task_id}] 需求分解降级为原始文本")
                return {**state, "requirement_plan": None, "current_step": "requirement_decomposition_skip"}
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 需求分解失败: {e}")
            return {**state, "requirement_plan": None, "current_step": "requirement_decomposition_skip"}

    # ------------------------------------------------------------------
    # 创新发现节点
    # ------------------------------------------------------------------
    async def _node_innovation(self, state: TaskState) -> TaskState:
        """从文献调研结果中发现研究空白并提出创新方案。"""
        task_id = state["task_id"]
        results = self._resolve_results(state)
        research_output = results.get("research_agent", {})
        analyzer_output = results.get("analyzer_agent", {})

        # 如果没有足够数据，跳过创新分析
        papers = research_output.get("papers", []) if isinstance(research_output, dict) else []
        if len(papers) < 2:
            logger.info(f"[LangGraph:{task_id}] 论文不足2篇，跳过创新分析")
            return {**state, "innovation_analysis": None, "current_step": "innovation_skip"}

        logger.info(f"[LangGraph:{task_id}] 启动创新发现分析（{len(papers)}篇论文）")
        try:
            from .innovation_agent import InnovationAgent
            agent = InnovationAgent()
            context = {
                "task_id": task_id,
                "project_name": state.get("project_name"),
                "problem_text": state.get("problem_text"),
                "results": {
                    "research_agent": research_output,
                    "analyzer_agent": analyzer_output,
                },
            }
            analysis = await agent.execute(task_input={}, context=context)
            return {**state, "innovation_analysis": analysis, "current_step": "innovation_done"}
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 创新分析失败: {e}")
            return {**state, "innovation_analysis": None, "current_step": "innovation_failed"}

    # ------------------------------------------------------------------
    # 任务总结节点
    # ------------------------------------------------------------------
    async def _node_summary(self, state: TaskState) -> TaskState:
        """任务完成后生成结构化总结报告，并整理知识库。"""
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] 生成任务总结报告")

        # 1. 生成总结报告
        summary = None
        try:
            from .summary_agent import SummaryAgent
            agent = SummaryAgent()
            results = self._resolve_results(state)
            context = {
                "task_id": task_id,
                "project_name": state.get("project_name"),
                "problem_text": state.get("problem_text"),
                "paper_template": state.get("paper_template"),
                "workflow_type": state.get("workflow_type"),
                "results": results,
                "sub_problems": state.get("sub_problems", []),
            }
            summary = await agent.execute(task_input={}, context=context)
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 任务总结失败: {e}")

        # 2. 整理知识库（下载的文献/数据集自动分类）
        try:
            from ..services.knowledge_organizer import run_full_organization
            from ..core.paths import get_project_output_dir, get_project_base_dir
            from ..core.knowledge_manager import get_knowledge_manager
            project_name = state.get("project_name")
            task_dir = get_project_output_dir(project_name) / task_id
            # 扫描范围：task 输出目录 + 全局参考文献目录 + 项目 reading 目录
            global_refs = get_project_base_dir(None) / "global_references"
            reading_dir = get_project_base_dir(project_name) / "reading" if project_name else None
            kb = get_knowledge_manager()
            org_result = run_full_organization(
                task_id, str(task_dir), kb,
                extra_scan_dirs=[str(global_refs)] + ([str(reading_dir)] if reading_dir and reading_dir.is_dir() else []),
            )
            organized_count = len(org_result.get("organized", []))
            logger.info(f"[LangGraph:{task_id}] 知识库整理完成: {organized_count} 个资源")
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 知识库整理失败: {e}")

        return {**state, "task_summary": summary, "current_step": "summary_done"}

    # ------------------------------------------------------------------
    # 节点实现（骨架，逐步填充）
    # ------------------------------------------------------------------
    async def _node_preflight_decision(self, state: TaskState) -> TaskState:
        """读取 preflight 报告并设置初始配置，更新进度。"""
        preflight = state.get("preflight") or {}
        task_id = state["task_id"]
        from ..core.task_persistence import save_task_metadata
        try:
            save_task_metadata(
                task_id=task_id,
                problem_text=state["problem_text"],
                status="running",
                created_at=datetime.now().isoformat(),
                progress=5,
                current_step="preflight_decision",
            )
        except Exception:
            pass
        logger.info(f"[LangGraph:{task_id}] preflight_decision: workflow={preflight.get('recommended_workflow')}, template={preflight.get('recommended_template')}")
        return {
            **state,
            "paper_template": preflight.get("recommended_template", state.get("paper_template", "math_modeling")),
            "workflow_type": preflight.get("recommended_workflow", state.get("workflow_type", "standard")),
            "mode": preflight.get("recommended_mode", state.get("mode", "batch")),
            "current_step": "preflight_decision_done",
        }

    async def _node_analyzer(self, state: TaskState) -> TaskState:
        """调用 analyzer_agent，更新进度与黑板。"""
        state = await self._check_user_input(state)

        agent = self.agents.get("analyzer_agent")
        if not agent:
            return {**state, "current_step": "analyzer_missing"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "analyzer_agent", "analysis")
        self._update_progress(task_id, state["problem_text"], 15, "问题分析中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        output = await agent.execute(
            task_input={"action": "analyze", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )
        output["_contract"] = get_contract_validator().validate("analyzer_agent", output)

        ref_update = self._set_result(state, "analyzer_agent", output)
        sub_problems = output.get("sub_problems", [])

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("analyzer_agent", output)
            wm.sub_problems = sub_problems
            if output.get("problem_type"):
                wm.update_problem(type=output["problem_type"])

        self._post_chat(task_id, "analyzer_agent", f"问题分析完成，识别 {len(sub_problems)} 个子问题")
        bus.emit_agent_complete(task_id, "analyzer_agent", "analysis", f"识别 {len(sub_problems)} 个子问题")
        logger.info(f"[LangGraph:{task_id}] analyzer: {len(sub_problems)} sub_problems")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "sub_problems": sub_problems, "current_step": "analyzer_done"}

    async def _node_data(self, state: TaskState) -> TaskState:
        """调用 data_agent 分析数据文件。"""
        agent = self.agents.get("data_agent")
        if not agent or not state.get("files"):
            logger.info(f"[LangGraph:{state['task_id']}] data: no files, skipping")
            return {**state, "current_step": "data_skipped"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "data_agent", "data_analysis")
        self._update_progress(task_id, state["problem_text"], 25, "数据分析中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        output = await agent.execute(
            task_input={"action": "analyze_data", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )

        ref_update = self._set_result(state, "data_agent", output)

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("data_agent", output)
            wm.data_insights = output.get("insights", [])

        self._post_chat(task_id, "data_agent", "数据分析完成")
        bus.emit_agent_complete(task_id, "data_agent", "data_analysis")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "data_done"}

    async def _node_research(self, state: TaskState) -> TaskState:
        """调用 research_agent 搜集文献，根据 workflow_type 调整搜索策略。

        v6.0 新增：
        - 跨论文研究空白识别（deep_search 模式自动触发）
        - 将 gap 分析结果注入 context 供后续 Agent 使用
        """
        agent = self.agents.get("research_agent")
        if not agent:
            return {**state, "current_step": "research_skipped"}

        task_id = state["task_id"]
        workflow = state.get("workflow_type", "standard")

        # quick / code_focused 模式跳过文献搜集
        if workflow in ("quick", "code_focused"):
            logger.info(f"[LangGraph:{task_id}] research: skipped (workflow={workflow})")
            return {**state, "current_step": "research_skipped"}

        bus = get_event_bus()
        bus.emit_agent_start(task_id, "research_agent", "literature_search")
        self._update_progress(task_id, state["problem_text"], 35, "文献搜集中")
        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")

        all_papers = []
        all_methods = []

        if workflow == "deep_research":
            # 深度研究：多角度搜索
            search_actions = ["search", "search_background", "search_methods"]
        else:
            search_actions = ["search"]

        # v8.4.3: 多智能体投票决策门控——T1 被否决时退做 T0 网页背景（用户认可 T0 无需投票）
        decision = state.get("research_decision") or {}
        allow_t1 = decision.get("allow_t1", True)
        allow_t2 = decision.get("allow_t2", False)
        if not allow_t1:
            # T1 论文检索被投票否决：用 T0 网页背景替代，避免空跑
            search_actions = ["search_background" if a in ("search", "search_methods") else a for a in search_actions]
            logger.info(f"[LangGraph:{task_id}] research: T1 被投票否决，退做 T0 网页背景")
        # T2 代码检索（仅复杂任务且投票放行才追加）
        if allow_t2:
            search_actions.append("code_search")
            logger.info(f"[LangGraph:{task_id}] research: T2 代码检索已放行，追加 code_search action")

        for action in search_actions:
            try:
                output = await agent.execute(
                    task_input={"action": action, "problem_text": state["problem_text"]},
                    context=self._agent_context(state),
                )
                all_papers.extend(output.get("papers", []))
                all_methods.extend(output.get("methods", []))
            except Exception as exc:
                logger.warning(f"[LangGraph:{task_id}] research.{action} failed: {exc}")

        result = {"papers": all_papers, "methods": all_methods}
        ref_update = self._set_result(state, "research_agent", result)

        # v6.0: 跨论文研究空白识别（deep_search 或 research_paper 模式自动触发）
        gap_analysis = None
        if workflow in ("deep_research", "research_paper") and len(all_papers) >= 3:
            try:
                # 如果 research_agent 有 _identify_cross_paper_gaps 方法，调用它
                if hasattr(agent, '_identify_cross_paper_gaps'):
                    gap_analysis = await agent._identify_cross_paper_gaps(all_papers, state["problem_text"])
                    if gap_analysis:
                        result["cross_paper_gaps"] = gap_analysis
                        logger.info(f"[LangGraph:{task_id}] 跨论文研究空白识别完成，发现 {len(gap_analysis.get('gaps', []))} 个 gap")
                        self._post_chat(task_id, "research_agent", f"跨论文研究空白识别完成，发现 {len(gap_analysis.get('gaps', []))} 个创新机会")
            except Exception as exc:
                logger.warning(f"[LangGraph:{task_id}] 跨论文研究空白识别失败: {exc}")

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.add_literature(all_papers, source="research_agent")
            for m in all_methods:
                wm.add_method(m)
            if gap_analysis:
                wm.set_result("cross_paper_gaps", gap_analysis)

        self._post_chat(task_id, "research_agent", f"文献搜集完成，{len(all_papers)} 篇文献，{len(all_methods)} 个方法")
        bus.emit_agent_complete(task_id, "research_agent", "literature_search", f"{len(all_papers)} 篇文献, {len(all_methods)} 个方法")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "research_done"}

    async def _node_modeler(self, state: TaskState) -> TaskState:
        """逐个子问题建模：每个子问题独立建模，前序结果递进传递给后序。"""
        state = await self._check_user_input(state)

        agent = self.agents.get("modeler_agent")
        if not agent:
            return {**state, "current_step": "modeler_missing"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "modeler_agent", "modeling")
        sub_problems = state.get("sub_problems", [])
        results = self._resolve_results(state)
        all_models = []

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")

        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            sp_name = sp.get("name", sp.get("description", f"子问题{sp_id}"))[:80]
            progress = 45 + int(10 * (i + 1) / max(len(sub_problems), 1))
            self._update_progress(task_id, state["problem_text"], progress, f"建模中：{sp_name}")

            # 前序模型摘要（递进传递）
            prev_model_summary = ""
            for j, pm in enumerate(all_models):
                prev_name = pm.get("sub_problem_name", f"子问题{j+1}")
                prev_obj = pm.get("objective_function", "")
                prev_vars = pm.get("decision_variables", [])
                prev_model_summary += f"- {prev_name}: {prev_obj[:80]}，变量: {', '.join([v.get('name','') for v in prev_vars[:3]])}\n"

            try:
                output = await agent.execute(
                    task_input={"action": "build_model", "sub_problem_id": sp_id},
                    context={
                        **self._agent_context(state),
                        "results": results,
                        "sub_problems": sub_problems,
                        "sub_problem_index": i,
                        "sub_problem": sp,
                        "previous_models": all_models,
                        "previous_model_summary": prev_model_summary,
                    },
                )
                # 注入来源和防编造标记
                output["_agent_source"] = "modeler_agent"
                fabrication_check = self._validate_no_fabrication("modeler_agent", output)
                output.update(fabrication_check)

                all_models.append({**output, "sub_problem_id": sp_id, "sub_problem_name": sp_name})
                self._post_chat(task_id, "modeler_agent", f"[{i+1}/{len(sub_problems)}] 建模完成：{sp_name}（{output.get('model_name', '')}）")
            except Exception as exc:
                logger.error(f"[LangGraph:{task_id}] modeler sp{sp_id} failed: {exc}")
                all_models.append({"sub_problem_id": sp_id, "sub_problem_name": sp_name, "error": str(exc)})

        modeler_output = {"sub_problem_models": all_models}
        ref_update = self._set_result(state, "modeler_agent", modeler_output)

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("modeler_agent", modeler_output)
            for m in all_models:
                wm.add_method({"name": m.get("model_name", ""), "type": m.get("model_type", ""), "sub_problem": m.get("sub_problem_name", "")})

        self._post_chat(task_id, "modeler_agent", f"全部 {len(sub_problems)} 个子问题建模完成")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "modeler_done"}

    async def _node_algorithm_engineer(self, state: TaskState) -> TaskState:
        """调用 algorithm_engineer_agent 设计算法/方法。

        保存原始丰富输出到 results["algorithm_engineer_agent"]；
        调用归一化方法得到标准 sub_problem_models，保存到 results["modeler_agent"]（兼容 solver/writer）。
        """
        state = await self._check_user_input(state)

        agent = self.agents.get("algorithm_engineer_agent")
        if not agent:
            return {**state, "current_step": "algorithm_engineer_missing"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 45, "算法设计中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        try:
            output = await agent.execute(
                task_input={"action": "design_algorithm", "problem_text": state["problem_text"]},
                context=self._agent_context(state),
            )
        except Exception as exc:
            logger.error(f"[LangGraph:{task_id}] algorithm_engineer failed: {exc}")
            return {**state, "current_step": "algorithm_engineer_failed"}

        # 防编造校验
        fabrication_check = self._validate_no_fabrication("algorithm_engineer_agent", output)
        output.update(fabrication_check)

        # 保存原始输出
        ref_raw = self._set_result(state, "algorithm_engineer_agent", output)

        # 归一化到标准 modeler_agent 格式
        normalized = self._normalize_algorithm_engineer_output(output)
        ref_norm = self._set_result(state, "modeler_agent", normalized)

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("algorithm_engineer_agent", output)
            wm.set_result("modeler_agent", normalized)

        self._post_chat(task_id, "algorithm_engineer_agent", "算法设计完成")
        return {
            **state,
            "results": {**state.get("results", {}), **ref_raw, **ref_norm},
            "current_step": "algorithm_engineer_done",
        }

    async def _node_financial_analyst(self, state: TaskState) -> TaskState:
        """调用 financial_analyst_agent 建立金融模型。

        保存原始丰富输出到 results["financial_analyst_agent"]；
        调用归一化方法得到标准 sub_problem_models，保存到 results["modeler_agent"]（兼容 solver/writer）。
        """
        state = await self._check_user_input(state)

        agent = self.agents.get("financial_analyst_agent")
        if not agent:
            return {**state, "current_step": "financial_analyst_missing"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 45, "金融模型建立中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        try:
            output = await agent.execute(
                task_input={"action": "build_financial_model", "problem_text": state["problem_text"]},
                context=self._agent_context(state),
            )
        except Exception as exc:
            logger.error(f"[LangGraph:{task_id}] financial_analyst failed: {exc}")
            return {**state, "current_step": "financial_analyst_failed"}

        # 防编造校验
        fabrication_check = self._validate_no_fabrication("financial_analyst_agent", output)
        output.update(fabrication_check)

        # 保存原始输出
        ref_raw = self._set_result(state, "financial_analyst_agent", output)

        # 归一化到标准 modeler_agent 格式
        normalized = self._normalize_financial_analyst_output(output)
        ref_norm = self._set_result(state, "modeler_agent", normalized)

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("financial_analyst_agent", output)
            wm.set_result("modeler_agent", normalized)

        self._post_chat(task_id, "financial_analyst_agent", "金融模型建立完成")
        return {
            **state,
            "results": {**state.get("results", {}), **ref_raw, **ref_norm},
            "current_step": "financial_analyst_done",
        }

    async def _node_iterative_solver(self, state: TaskState) -> TaskState:
        """逐个子问题求解 + 自主迭代修复 + 代码自动演化（v6.0）。

        对每个子问题：
        1. 用对应模型结果调 solver_agent
        2. Harness 评判（ResultValidator + CrossValidator + CodeManifest）
        3. 失败时注入错误分类和修复建议，重试（最多 max_solver_iterations 次）
        4. 仍失败则多 Agent 投票决定 retry / collect_data / abort
        5. v6.0: 成功后可选进入代码自动演化循环，迭代改进代码
        """
        state = await self._check_user_input(state)

        agent = self.agents.get("solver_agent")
        if not agent:
            return {**state, "current_step": "solver_missing"}

        task_id = state["task_id"]
        sub_problems = state.get("sub_problems", [])
        results = self._resolve_results(state)
        modeler_output = results.get("modeler_agent", {})
        all_models = modeler_output.get("sub_problem_models", [])
        all_solutions = []
        all_attempts = list(state.get("solver_attempts", []))
        escalation = state.get("escalation_count", 0)

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")

        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            sp_name = sp.get("name", sp.get("description", f"子问题{sp_id}"))[:80]
            progress = 55 + int(20 * (i + 1) / max(len(sub_problems), 1))
            self._update_progress(task_id, state["problem_text"], progress, f"求解中：{sp_name}")

            # 找到对应的模型
            model_for_sp = next((m for m in all_models if m.get("sub_problem_id") == sp_id), {})

            # 前序求解结果摘要（递进传递）
            prev_solve_summary = ""
            for j, ps in enumerate(all_solutions):
                prev_name = ps.get("sub_problem_name", f"子问题{j+1}")
                prev_findings = ps.get("results", {}).get("key_findings", [])
                prev_numerical = ps.get("results", {}).get("numerical_results", {})
                numerical_str = ", ".join([f"{k}={v}" for k, v in prev_numerical.items() if k != "状态"])
                prev_solve_summary += f"- {prev_name}: {'; '.join(str(f) for f in prev_findings[:2])}, 数值: {numerical_str or '见结果'}\n"

            # 迭代求解（含自动修复）
            sp_attempts = []
            sp_success = False
            fix_context = ""

            for attempt in range(self.cfg.max_solver_iterations):
                try:
                    output = await agent.execute(
                        task_input={"action": "solve", "sub_problem_id": sp_id, "problem_text": state["problem_text"] + fix_context},
                        context={
                            **self._agent_context(state),
                            "results": results,
                            "sub_problems": sub_problems,
                            "sub_problem_index": i,
                            "sub_problem": sp,
                            "model_result": model_for_sp,
                            "section_results": all_solutions,
                            "previous_solutions": all_solutions,
                            "previous_solution_summary": prev_solve_summary,
                        },
                    )

                    # Harness 评判
                    harness = await self._run_harness(output)
                    output["harness"] = harness
                    sp_attempts.append(output)
                    all_attempts.append(output)

                    if output.get("execution_success") and harness.get("passed"):
                        sp_success = True
                        all_solutions.append({**output, "sub_problem_id": sp_id, "sub_problem_name": sp_name})
                        self._post_chat(task_id, "solver_agent", f"[{i+1}/{len(sub_problems)}] 求解成功：{sp_name}")
                        break

                    # 构造修复上下文用于下一次尝试
                    error_info = output.get("error", "")
                    exec_output = output.get("execution_result", {}).get("output", "")
                    classification = output.get("error_classification", {})
                    fix_hint = "\n".join(classification.get("fixes", []))
                    fix_context = (
                        f"\n\n## 上次求解失败（第 {attempt+1} 次）\n"
                        f"错误类型: {classification.get('category', 'unknown')}\n"
                        f"错误信息: {error_info[:500]}\n"
                        f"修复建议: {fix_hint}\n请修正代码后重新求解。"
                    )

                except Exception as exc:
                    logger.error(f"[LangGraph:{task_id}] solver sp{sp_id} attempt {attempt+1} failed: {exc}")
                    sp_attempts.append({"error": str(exc), "execution_success": False})

            # v6.0: 代码自动演化 —— 求解成功后迭代改进代码
            if sp_success and all_solutions:
                last_solution = all_solutions[-1]
                try:
                    from .solver_agent import evolve_solution
                    code_files = last_solution.get("code_files", [])
                    if code_files and code_files[0].get("code"):
                        initial_code = code_files[0]["code"]
                        problem_context = f"{sp_name}: {model_for_sp.get('objective_function', '')[:100]}"
                        evolution_result = await evolve_solution(
                            solver=agent,
                            initial_code=initial_code,
                            problem_context=problem_context,
                            sp_id=sp_id,
                            project_name=state.get("project_name"),
                            enable_evolution=True,
                            max_evaluations=6,
                        )
                        if evolution_result.get("evolved") and evolution_result.get("improved"):
                            # 用演化后的最优代码替换
                            last_solution["code_files"] = [{
                                **code_files[0],
                                "code": evolution_result["best_code"],
                                "description": f"代码自动演化后（改进 {evolution_result.get('improvement', 0):.1%}）",
                            }]
                            last_solution["code_evolution"] = {
                                "improved": True,
                                "improvement": evolution_result.get("improvement"),
                                "generations": len(evolution_result.get("generations", [])),
                                "total_evaluations": evolution_result.get("total_evaluations"),
                            }
                            self._post_chat(
                                task_id, "solver_agent",
                                f"[{i+1}/{len(sub_problems)}] 代码自动演化完成：改进 {evolution_result.get('improvement', 0):.1%}"
                            )
                            logger.info(f"[LangGraph:{task_id}] 代码自动演化完成: sp_id={sp_id}, improvement={evolution_result.get('improvement', 0):.4f}")
                except Exception as exc:
                    logger.warning(f"[LangGraph:{task_id}] 代码自动演化失败: {exc}")

            if not sp_success:
                # 达到迭代上限 → 多 Agent 投票
                if len(all_attempts) >= self.cfg.max_solver_iterations:
                    # v8.4.6: 5次重试都失败 → 降级 HTTP API 代码生成（写文件+执行+3次迭代修复），不降级模板
                    http_sol = await self._solver_http_fallback(
                        agent, task_id, sp_id, sp_name, sp, model_for_sp, state, i, len(sub_problems)
                    )
                    if http_sol is not None:
                        all_solutions.append(http_sol)
                        continue
                    # HTTP 降级也失败 → 多 Agent 投票
                    vote = await self._multi_agent_vote(state, sp_attempts[-1], all_attempts)
                    if vote == "retry" and escalation < self.cfg.max_solver_escalations:
                        escalation += 1
                        self._post_chat(task_id, "coordinator", f"子问题 {sp_name} 求解失败，Agent 投票决定重试（第 {escalation} 次升级）")
                    elif vote == "collect_data":
                        return {**state, "solver_attempts": all_attempts, "escalation_count": escalation, "current_step": "self_collect"}
                    else:
                        return {
                            **state,
                            "solver_attempts": all_attempts,
                            "escalation_count": escalation,
                            "current_step": "cannot_solve",
                            "cannot_solve_report": {"reason": f"子问题 {sp_name} 求解失败，多 Agent 投票判定无法继续", "vote": vote, "attempts": len(all_attempts)},
                        }
                all_solutions.append({"sub_problem_id": sp_id, "sub_problem_name": sp_name, "error": "求解失败", "execution_success": False})

        # 汇总求解结果
        solver_output = {"sub_problem_solutions": all_solutions, "execution_success": all(s.get("execution_success", False) for s in all_solutions)}
        ref_update = self._set_result(state, "solver_agent", solver_output)

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("solver_agent", solver_output)
            for s in all_solutions:
                findings = s.get("results", {}).get("key_findings", [])
                if findings:
                    wm.set_result("solver_agent", {**wm.results.get("solver_agent", {}), "last_findings": findings})

        self._post_chat(task_id, "solver_agent", f"全部 {len(sub_problems)} 个子问题求解完成")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "solver_attempts": all_attempts, "escalation_count": escalation, "current_step": "solver_done"}

    async def _solver_http_fallback(
        self, agent, task_id: str, sp_id: int, sp_name: str,
        sp: Dict[str, Any], model_for_sp: Dict[str, Any],
        state: TaskState, idx: int, total: int,
    ) -> Optional[Dict[str, Any]]:
        """v8.4.6: solver 5次重试失败后，降级 HTTP API 代码生成（非模板代码）。

        调 agent._call_claude_coder_http：call_llm 生成代码 + 写文件 + 执行 + 3次迭代修复。
        产出代码（无论执行是否成功）→ 返回 solution dict；彻底无代码 → 返回 None（上层走多 Agent 投票）。
        """
        try:
            from .solver_agent import CLAUDE_CODER_SYSTEM
            from ..core.paths import get_project_output_dir
            import os as _os
            import json as _json
            workspace = str(get_project_output_dir(state.get("project_name")))
            http_prompt = (
                "请为以下数学建模子问题生成可直接运行的 Python 求解代码。\n\n"
                f"## 子问题\n名称：{sp_name}\n描述：{sp.get('description', '')[:300]}\n\n"
                f"## 问题背景\n{state['problem_text'][:800]}\n\n"
                f"## 模型\n{_json.dumps(model_for_sp, ensure_ascii=False)[:800]}\n\n"
                "## 输出要求\n返回 JSON：{\"code\":\"完整Python代码(含import,末尾用json.dumps打印结果)\","
                "\"key_findings\":[],\"numerical_results\":{},\"interpretation\":\"\"}"
            )
            http_res = await agent._call_claude_coder_http(
                task_description=http_prompt,
                system_instruction=CLAUDE_CODER_SYSTEM,
                workspace_dir=workspace,
                timeout=300,
            )
            code = http_res.get("code", "")
            if not code:
                logger.warning(f"[LangGraph:{task_id}] solver sp{sp_id} HTTP 降级未产出代码")
                return None
            ok = http_res.get("success", False)
            sol = {
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name,
                "model": model_for_sp,
                "code_files": [{
                    "filename": _os.path.basename(http_res.get("file_path", "solver_http.py")),
                    "language": "python",
                    "code": code,
                    "description": f"HTTP API 代码生成（5次重试后降级，{'执行成功' if ok else '执行失败'}）",
                    "executed": ok,
                }],
                "results": {
                    "key_findings": http_res.get("key_findings", []),
                    "numerical_results": http_res.get("numerical_results", {}),
                    "interpretation": http_res.get("interpretation", ""),
                },
                "execution_success": ok,
                "execution_attempts": http_res.get("attempts", 1),
                "execution_error": http_res.get("execution_stderr", ""),
                "_degraded": True,
                "_degraded_by": "http_api_coder_fallback",
                "_degraded_reason": "solver 5次重试失败，HTTP API 降级生成代码",
            }
            self._post_chat(task_id, "solver_agent",
                f"[{idx+1}/{total}] {sp_name} 5次重试失败，HTTP API 降级生成代码（{'成功' if ok else '代码已生成但执行失败'}）")
            logger.info(f"[LangGraph:{task_id}] solver sp{sp_id} HTTP 降级: success={ok}")
            return sol
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] solver sp{sp_id} HTTP 降级异常: {exc}")
            return None

    async def _run_harness(self, sol_result: Dict[str, Any]) -> Dict[str, Any]:
        """综合 Harness 评判。"""
        numerical = sol_result.get("numerical_results", {})
        if not isinstance(numerical, dict):
            numerical = {}

        validation = get_result_validator().validate(numerical, {})

        cross = []
        try:
            cross = await get_cross_validator().cross_check(
                "primary", numerical,
                "secondary_estimate", {k: v * 0.95 for k, v in numerical.items() if isinstance(v, (int, float))},
            )
        except Exception as exc:
            logger.debug(f"CrossValidator skipped: {exc}")

        manifest_valid = True
        try:
            manifest = sol_result.get("code_manifest", {})
            if manifest and "manifest" in manifest:
                parsed = parse_manifest_from_dict(manifest["manifest"])
                report = validate_manifest(parsed)
                manifest_valid = report.valid
        except Exception as exc:
            logger.debug(f"CodeManifest validation skipped: {exc}")

        passed = (
            validation.get("valid", False)
            and manifest_valid
            and all(not getattr(c, "diverged", False) for c in cross)
        )

        return {
            "passed": passed,
            "validation": validation,
            "cross_check": [c.__dict__ if hasattr(c, "__dict__") else dict(c) for c in cross],
            "manifest_valid": manifest_valid,
        }

    async def _multi_agent_vote(self, state: TaskState, sol_result: Dict[str, Any], attempts: List[Dict[str, Any]]) -> str:
        """多 Agent 评议投票：retry / collect_data / abort。"""
        last_error = attempts[-1].get("error", "")[:300]
        last_output = attempts[-1].get("execution_result", {}).get("output", "")[:300]
        prompt = (
            "基于以下求解失败信息，判断原因并只回复一个单词：\n"
            "- 代码 bug / 实现错误 → 回复 \"retry\"\n"
            "- 数据不足 / 问题本身不可解 → 回复 \"collect_data\"\n"
            "- 其他无法继续的情况 → 回复 \"abort\"\n\n"
            f"错误信息：{last_error}\n"
            f"执行输出：{last_output}"
        )

        agents_to_poll = ["analyzer_agent", "modeler_agent", "peer_review_agent"]
        votes = []
        for agent_name in agents_to_poll:
            agent = self.agents.get(agent_name)
            if not agent:
                continue
            try:
                resp = await agent.call_llm([
                    {"role": "system", "content": "You are a diagnostic assistant. Reply with exactly one word: retry, collect_data, or abort."},
                    {"role": "user", "content": prompt},
                ], temperature=0.1)
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "").lower()
                for v in ["retry", "collect_data", "abort"]:
                    if v in content:
                        votes.append(v)
                        break
            except Exception as exc:
                logger.debug(f"Vote from {agent_name} failed: {exc}")

        if not votes:
            return "abort"

        from collections import Counter
        return Counter(votes).most_common(1)[0][0]

    async def _node_writer(self, state: TaskState) -> TaskState:
        """调用 writer_agent 生成论文。"""
        state = await self._check_user_input(state)

        agent = self.agents.get("writer_agent")
        if not agent:
            return {**state, "current_step": "writer_missing"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "writer_agent", "writing")
        self._update_progress(task_id, state["problem_text"], 70, "论文写作中")

        # 从 writer_agent 历史结果读取修订次数（更可靠）
        resolved = self._resolve_results(state)
        writer_history = resolved.get("writer_agent", {})
        revision_count = (writer_history.get("_revision_count", 0) if isinstance(writer_history, dict) else 0) + 1
        logger.info(f"[LangGraph:{task_id}] writer node start, revision_count={revision_count}")

        # ===== 修订模式：注入 Peer Review 反馈 =====
        review_feedback = None
        if revision_count > 1:
            peer_review = resolved.get("peer_review_agent", {})
            if peer_review and isinstance(peer_review, dict):
                scores = peer_review.get("scores", {})
                comments = peer_review.get("comments", {})
                suggested_edits = peer_review.get("suggested_edits", [])
                rec = peer_review.get("recommendation", "")
                overall = peer_review.get("overall_score", 0)
                # 适配 writer_agent._format_peer_review_feedback 的期望格式：
                # comments: {major: [...], minor: [...]}
                # suggested_edits: [{location, suggestion}]
                normalized_edits = []
                for ed in suggested_edits:
                    if isinstance(ed, dict):
                        normalized_edits.append({
                            "location": ed.get("target", ed.get("location", "")),
                            "suggestion": ed.get("change", ed.get("suggestion", "")),
                        })
                    else:
                        normalized_edits.append(str(ed))
                # 合并 issues 列表（writer_agent 在 chapter 级别读取 issues/feedback 字段）
                major_list = comments.get("major", []) if isinstance(comments, dict) else []
                issues_list = [str(m) for m in major_list] + [
                    f"{ed.get('location', '')}: {ed.get('suggestion', '')}" for ed in normalized_edits
                ]
                review_feedback = {
                    "recommendation": rec,
                    "overall_score": overall,
                    "scores": scores,
                    "comments": comments if isinstance(comments, dict) else {"major": [], "minor": []},
                    "suggested_edits": normalized_edits,
                    "issues": issues_list,
                    "instruction": (
                        f"上一轮审稿评分 {overall}/5（{rec}），"
                        f"请根据以下 {len(normalized_edits)} 条修改建议重写论文："
                    ),
                }
                self._post_chat(
                    task_id, "coordinator",
                    f"📝 第 {revision_count} 稿修订：审稿评分 {overall}/5，"
                    f"{len(major_list)} 条主要意见，{len(normalized_edits)} 条修改建议",
                )

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        task_input = {
            "action": "write",
            "problem_text": state["problem_text"],
            "sub_problems": state.get("sub_problems", []),
            "use_critique": state.get("use_critique", True),
        }
        if review_feedback:
            task_input["review_feedback"] = review_feedback
        try:
            output = await agent.execute(
                task_input=task_input,
                context=self._agent_context(state),
            )
        except Exception as writer_exc:
            logger.error(f"[LangGraph:{task_id}] writer agent failed: {writer_exc}")
            output = {
                "latex_code": "",
                "abstract": "",
                "title": "",
                "_error": str(writer_exc),
                "_degraded": True,
                "_degraded_reason": f"writer_agent 执行失败: {writer_exc}",
            }
            self._post_chat(task_id, "coordinator", f"⚠️ 论文写作异常：{writer_exc}，已生成降级标记")
        output["_contract"] = get_contract_validator().validate("writer_agent", output)
        output["_revision_count"] = revision_count

        ref_update = self._set_result(state, "writer_agent", output)
        self._post_chat(task_id, "writer_agent", f"论文写作完成（第 {revision_count} 稿）")
        logger.info(f"[LangGraph:{task_id}] writer node done, posted 第 {revision_count} 稿")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "writer_done", "revision_count": revision_count}

    async def _node_peer_review(self, state: TaskState) -> TaskState:
        """调用 peer_review_agent 进行同行评议。"""
        agent = self.agents.get("peer_review_agent")
        if not agent or not self.cfg.enable_peer_review:
            return {**state, "current_step": "peer_review_skipped"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "peer_review_agent", "peer_review")
        self._update_progress(task_id, state["problem_text"], 80, "同行评议中")

        try:
            output = await agent.execute(
                task_input={"action": "review", "problem_text": state["problem_text"]},
                context=self._agent_context(state),
            )
        except Exception as pr_exc:
            logger.error(f"[LangGraph:{task_id}] peer_review agent failed: {pr_exc}")
            # 审稿失败时自动放行（避免阻塞全流程），但标记降级
            output = {
                "recommendation": "accept",
                "overall_score": 3,
                "scores": {},
                "comments": {"major": [], "minor": []},
                "suggested_edits": [],
                "_degraded": True,
                "_degraded_reason": f"peer_review_agent 执行失败: {pr_exc}",
            }
            self._post_chat(task_id, "coordinator", f"⚠️ 同行评议异常：{pr_exc}，已自动放行")

        ref_update = self._set_result(state, "peer_review_agent", output)
        rec = (output.get("recommendation") or "").lower()
        score = output.get("overall_score", 0)
        self._post_chat(task_id, "peer_review_agent", f"同行评议完成：{rec}，得分 {score}")
        bus.emit_agent_complete(task_id, "peer_review_agent", "peer_review", f"{rec}, score={score}")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "peer_review_done"}
    async def _node_experiment(self, state: TaskState) -> TaskState:
        """调用 experimentation_agent 设计并执行实验（CCF-A 模板才启用）。

        v6.0 新增：
        - NAS：自动搜索最优网络架构（图像任务）
        - 自动损失函数设计：进化搜索最优损失函数
        - AutoML：自动超参数优化
        """
        agent = self.agents.get("experimentation_agent")
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}
        if not agent or not self.cfg.enable_experiment_design or template not in ccf_a:
            return {**state, "current_step": "experiment_skipped"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 55, "实验执行中")

        results = self._resolve_results(state)
        modeling_agent = self._select_modeling_agent(template, state.get("workflow_type", "standard"))
        modeling_result = results.get(modeling_agent, {}) if modeling_agent else {}

        # v6.0: 自动损失函数设计（如果方法描述中有损失函数相关）
        loss_design_result = None
        try:
            from ..core.loss_design import create_loss_design_agent
            loss_agent = create_loss_design_agent(population_size=6, max_generations=3)
            method = modeling_result.get("proposed_method", {}) if isinstance(modeling_result, dict) else {}
            task_type = "classification"  # 默认，可根据问题推断
            baseline_losses = ["cross_entropy", "mse"]  # 默认 baselines
            loss_design_result = await loss_agent.design(
                task_type=task_type,
                baseline_losses=baseline_losses,
            )
            logger.info(f"[LangGraph:{task_id}] 自动损失函数设计完成，fitness={loss_design_result.get('fitness', 0):.4f}")
            self._post_chat(task_id, "experimentation_agent", "自动损失函数设计完成")
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] 自动损失函数设计失败: {exc}")

        # v6.0: NAS 神经架构搜索 — 由协调者和研究员共同讨论决定
        nas_result = None
        try:
            from ..core.nas import create_nas_agent
            from ..core.security import wrap_user_content

            # 让研究员分析问题，判断是否需要 NAS
            researcher = self.agents.get("research_agent")
            nas_decision = None
            if researcher:
                nas_prompt = f"""请分析以下问题，判断是否需要使用 NAS（神经架构搜索）来设计最优神经网络架构。

问题：{state['problem_text'][:500]}

判断标准：
1. 问题是否涉及图像处理、计算机视觉、目标检测、图像分割等任务？
2. 问题是否需要设计或优化神经网络架构？
3. 问题是否涉及深度学习模型的选择或改进？

请返回 JSON 格式：
{{"need_nas": true/false, "reason": "判断理由", "task_type": "classification/detection/segmentation/generation/other"}}

只返回 JSON，不要其他内容。"""
                try:
                    resp = await researcher.call_llm([{"role": "user", "content": wrap_user_content(nas_prompt)}])
                    content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                    # 提取 JSON
                    import json, re
                    json_match = re.search(r'\{[^{}]*"need_nas"[^{}]*\}', content)
                    if json_match:
                        nas_decision = json.loads(json_match.group())
                except Exception as e:
                    logger.warning(f"[LangGraph:{task_id}] NAS 决策分析失败: {e}")

            # 根据研究员的分析决定是否执行 NAS
            need_nas = nas_decision.get("need_nas", False) if nas_decision else False
            task_type = nas_decision.get("task_type", "classification") if nas_decision else "classification"

            if need_nas:
                logger.info(f"[LangGraph:{task_id}] 研究员建议执行 NAS: {nas_decision.get('reason', '')}")
                self._post_chat(task_id, "orchestrator", f"研究员分析：需要 NAS（{nas_decision.get('reason', '')}）")

                nas_agent = create_nas_agent(population_size=6, max_generations=3)
                baselines = []
                if isinstance(modeling_result, dict):
                    baselines = modeling_result.get("experiment_design", {}).get("baselines", [])
                nas_result = await nas_agent.search(
                    problem_description=state["problem_text"],
                    baseline_methods=baselines,
                )
                logger.info(f"[LangGraph:{task_id}] NAS 搜索完成，fitness={nas_result.get('fitness', 0):.4f}")
                self._post_chat(task_id, "experimentation_agent", "NAS 神经架构搜索完成")
            else:
                reason = nas_decision.get("reason", "问题不需要 NAS") if nas_decision else "无法分析"
                logger.info(f"[LangGraph:{task_id}] 跳过 NAS: {reason}")
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] NAS 流程异常: {exc}")

        # v6.0: AutoML 超参数优化
        automl_result = None
        try:
            from ..services.automl import create_search_space_from_method, AutoMLService
            if isinstance(modeling_result, dict):
                method = modeling_result.get("proposed_method", {})
                if method and method.get("hyperparameters"):
                    search_space = create_search_space_from_method(method)
                    automl_service = AutoMLService(search_space)

                    # 构建真实评估器：用超参配置生成代码 + 快速训练评估
                    import tempfile
                    import subprocess
                    import sys
                    import os

                    def _automl_objective(cfg: dict) -> float:
                        """用给定超参训练简单模型，返回验证准确率。"""
                        # 构建一个简单的 PyTorch 训练脚本
                        lr = cfg.get("learning_rate", 0.001)
                        batch_size = cfg.get("batch_size", 32)
                        hidden_size = cfg.get("hidden_size", 64)
                        epochs = 2  # 快速评估

                        script = f'''
import torch, torch.nn as nn, torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import torchvision, torchvision.transforms as transforms
import json, sys

transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.5,),(0.5,))])
trainset = torchvision.datasets.CIFAR10(root="./data", train=True, download=True, transform=transform)
loader = DataLoader(trainset, batch_size={batch_size}, shuffle=True, num_workers=0)

device = "cuda" if torch.cuda.is_available() else "cpu"
model = nn.Sequential(
    nn.Flatten(), nn.Linear(32*32*3, {hidden_size}), nn.ReLU(),
    nn.Linear({hidden_size}, 10)
).to(device)
optimizer = optim.Adam(model.parameters(), lr={lr})
criterion = nn.CrossEntropyLoss()

for epoch in range({epochs}):
    for inputs, labels in loader:
        inputs, labels = inputs.to(device), labels.to(device)
        optimizer.zero_grad()
        loss = criterion(model(inputs), labels)
        loss.backward()
        optimizer.step()

# 简单评估
correct, total = 0, 0
for inputs, labels in loader:
    inputs, labels = inputs.to(device), labels.to(device)
    _, pred = model(inputs).max(1)
    correct += pred.eq(labels).sum().item()
    total += labels.size(0)
    if total > 500: break
acc = correct / max(total, 1)
print(json.dumps({{"accuracy": round(acc, 4)}}))
'''
                        try:
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir='/tmp') as f:
                                f.write(script)
                                script_path = f.name
                            result = subprocess.run(
                                [sys.executable, script_path],
                                capture_output=True, text=True, timeout=120,
                                env={**os.environ, 'PYTHONPATH': '/tmp'}
                            )
                            for line in result.stdout.splitlines():
                                if '"accuracy"' in line:
                                    data = json.loads(line)
                                    acc = data.get("accuracy", 0.0)
                                    logger.debug(f"AutoML trial: cfg={cfg}, accuracy={acc}")
                                    return acc
                        except Exception as e:
                            logger.debug(f"AutoML trial failed: {e}")
                        finally:
                            try: os.unlink(script_path)
                            except: pass
                        return 0.0  # 训练失败返回最低分

                    automl_result = automl_service.search(
                        objective=_automl_objective,
                        max_trials=10,
                        strategy="tpe",
                        direction="maximize",
                    )
                    logger.info(f"[LangGraph:{task_id}] AutoML 搜索完成，最优值={automl_result.get('best_value', 0):.4f}")
                    self._post_chat(task_id, "experimentation_agent", "AutoML 超参数优化完成")
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] AutoML 搜索失败: {exc}")

        output = await agent.execute(
            task_input={
                "action": "execute",
                "problem_text": state["problem_text"],
                "modeling_result": modeling_result,
                "solver_result": results.get("solver_agent", {}),
                "project_name": state.get("project_name"),
                "task_id": task_id,
                # v6.0: 注入自主设计结果
                "nas_result": nas_result,
                "loss_design_result": loss_design_result,
                "automl_result": automl_result,
            },
            context=self._agent_context(state),
        )

        # 将自主设计结果合并到输出
        if nas_result:
            output["nas_architecture"] = nas_result.get("best_architecture")
            output["nas_code"] = nas_result.get("pytorch_code")
        if loss_design_result:
            output["loss_function_code"] = loss_design_result.get("pytorch_code")
            output["loss_tree"] = loss_design_result.get("best_loss_tree")
        if automl_result:
            output["automl_best_params"] = automl_result.get("best_params")
            output["automl_report"] = automl_result

        ref_update = self._set_result(state, "experimentation_agent", output)
        executed = output.get("executed", False)
        self._post_chat(
            task_id,
            "experimentation_agent",
            f"实验{'执行完成' if executed else '设计完成（未执行）'}"
            f"{' + NAS' if nas_result else ''}"
            f"{' + LossDesign' if loss_design_result else ''}"
            f"{' + AutoML' if automl_result else ''}",
        )

        # 实验闭环评估：检查是否需要迭代优化
        iteration_count = state.get("experiment_iterations", 0)
        max_iterations = self._get_config().experiment_max_iterations
        needs_iteration = self._evaluate_experiment_quality(output)

        if needs_iteration and iteration_count < max_iterations and executed:
            logger.info(f"[LangGraph:{task_id}] 实验质量不足，第 {iteration_count + 1}/{max_iterations} 轮迭代")
            self._post_chat(task_id, "experimentation_agent", f"实验质量不足，开始第 {iteration_count + 1} 轮迭代优化")
            # 将当前实验结果反馈给 experimentation_agent 进行改进
            output["iteration_feedback"] = self._generate_iteration_feedback(output)
            output["iteration_round"] = iteration_count + 1
            ref_update = self._set_result(state, "experimentation_agent", output)
            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "current_step": "experiment_iterating",
                "experiment_iterations": iteration_count + 1,
            }

        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "experiment_done"}

    def _evaluate_experiment_quality(self, experiment_output: Dict[str, Any]) -> bool:
        """评估实验质量，决定是否需要迭代。

        v8.1: 使用真实 metrics/失败率驱动，替代字段存在性判据。

        Returns:
            True 表示需要迭代。
        """
        if not isinstance(experiment_output, dict):
            return False

        # 1. 检查实验是否成功执行
        executed = experiment_output.get("executed", False)
        if not executed:
            return False

        # 2. 检查是否有实验结果
        experiment_result = experiment_output.get("experiment_result")
        if not experiment_result:
            return True  # 没有结果，需要重新执行

        # 3. 基于真实 metrics 评估质量
        plan = experiment_output.get("plan", {})
        metrics = plan.get("metrics", [])
        ablation_plan = plan.get("ablation_plan", [])
        baselines = plan.get("baselines", [])

        # 3.1 检查是否有 baseline 对比
        has_baseline_comparison = len(baselines) >= 2

        # 3.2 检查是否有消融实验
        has_ablation = len(ablation_plan) >= 1

        # 3.3 检查实验成功率（如果有结果）
        if isinstance(experiment_result, dict):
            success_rate = experiment_result.get("success_rate", 0)
            failed_experiments = experiment_result.get("failed_experiments", [])

            # 如果失败率过高（>30%），需要迭代
            if success_rate < 0.7 and len(failed_experiments) > 0:
                logger.info(f"实验成功率过低: {success_rate:.2%}，需要迭代优化")
                return True

            # 检查是否有关键指标缺失
            reported_metrics = experiment_result.get("metrics", {})
            if metrics and not reported_metrics:
                logger.info("实验未报告任何指标，需要迭代")
                return True

        # 3.4 检查 baseline 和 ablation 是否完整
        if executed and (not has_baseline_comparison or not has_ablation):
            logger.info(f"实验缺少完整对比: baseline={has_baseline_comparison}, ablation={has_ablation}")
            return True

        return False

    def _generate_iteration_feedback(self, experiment_output: Dict[str, Any]) -> str:
        """生成实验迭代反馈，指导 experimentation_agent 改进。

        v8.1: 基于真实 metrics/失败率生成详细反馈。
        """
        feedback_parts = []
        plan = experiment_output.get("plan", {})
        experiment_result = experiment_output.get("experiment_result", {})

        # 检查 baseline 对比
        baselines = plan.get("baselines", [])
        if len(baselines) < 2:
            feedback_parts.append(
                f"当前只有 {len(baselines)} 个 baseline，请添加至少2个强 baseline 方法"
                "（如 Random Forest、BERT-base 等）进行对比"
            )

        # 检查消融实验
        ablation_plan = plan.get("ablation_plan", [])
        if len(ablation_plan) < 1:
            feedback_parts.append(
                "缺少 ablation study，请添加消融实验验证各组件贡献"
                "（如：移除XX模块后性能下降多少）"
            )

        # 检查实验成功率
        if isinstance(experiment_result, dict):
            success_rate = experiment_result.get("success_rate", 0)
            failed_experiments = experiment_result.get("failed_experiments", [])

            if success_rate < 0.7:
                feedback_parts.append(
                    f"实验成功率过低 ({success_rate:.2%})，"
                    f"有 {len(failed_experiments)} 个实验失败，请分析失败原因并修复"
                )

            # 检查失败的实验类型
            for failed in failed_experiments[:3]:  # 只报告前3个失败
                exp_name = failed.get("name", "unknown")
                error = failed.get("error", "unknown error")
                feedback_parts.append(f"实验 '{exp_name}' 失败: {error}")

        # 检查指标报告
        metrics = plan.get("metrics", [])
        reported_metrics = experiment_result.get("metrics", {}) if isinstance(experiment_result, dict) else {}
        if metrics and not reported_metrics:
            feedback_parts.append(
                f"实验未报告任何指标，请确保报告以下指标: "
                f"{', '.join(m.get('name', '?') for m in metrics[:5])}"
            )

        return "；".join(feedback_parts) if feedback_parts else "请优化实验设计和结果分析"

    async def _node_figure(self, state: TaskState) -> TaskState:
        """调用 figure_agent 生成科研图表。"""
        agent = self.agents.get("figure_agent")
        if not agent:
            return {**state, "current_step": "figure_skipped"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 65, "科研图表生成中")

        results = self._resolve_results(state)
        solver_result = results.get("solver_agent", {})

        # 第一步：规划图表
        plan_output = await agent.execute(
            task_input={
                "action": "plan",
                "problem_text": state["problem_text"],
                "data": solver_result,
            },
            context=self._agent_context(state),
        )

        figures_plan = plan_output.get("figures", [])
        if not figures_plan:
            logger.info(f"[LangGraph:{task_id}] figure planning returned empty, skipping")
            return {**state, "current_step": "figure_skipped"}

        # 第二步：批量生成图表
        gen_output = await agent.execute(
            task_input={
                "action": "generate_all",
                "figure_plan": plan_output,
                "data": solver_result,
                "project_name": state.get("project_name"),
            },
            context=self._agent_context(state),
        )

        generated = gen_output.get("generated", 0)
        self._post_chat(
            task_id,
            "figure_agent",
            f"图表生成完成：规划 {len(figures_plan)} 个，成功生成 {generated} 个",
        )
        logger.info(f"[LangGraph:{task_id}] figure node done: {generated}/{len(figures_plan)} figures generated")

        ref_update = self._set_result(state, "figure_agent", gen_output)
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "figure_done"}

    async def _node_fact_check(self, state: TaskState) -> TaskState:
        """事实核查：对比 main.tex 与 solves.json 数字 + fabrication 拦截。"""
        if not self.cfg.enable_fact_check:
            return {**state, "current_step": "fact_check_skipped"}

        task_id = state["task_id"]
        project_name = state.get("project_name")
        try:
            output_dir = get_project_output_dir(project_name)
        except Exception:
            output_dir = None

        report: Dict[str, Any] = {"enabled": True, "passed": True}
        results = self._resolve_results(state)

        if output_dir:
            # ===== 关键时序修复：确保 fact_checker 所需的文件已存在 =====
            # fact_checker.check() 从磁盘读取 final/main.tex 和 solves.json，
            # 但这些文件在正常流程中仅在 _save_results（图执行完毕后）写入。
            # 此处提前将 writer / solver 结果物化到磁盘，保证事实核查不会因文件缺失而空转。
            try:
                # 写出 LaTeX 到 final/main.tex
                writer_output = results.get("writer_agent") or {}
                latex_code = writer_output.get("latex_code", "") if isinstance(writer_output, dict) else ""
                if latex_code:
                    final_dir = output_dir / "final"
                    final_dir.mkdir(parents=True, exist_ok=True)
                    final_tex = final_dir / "main.tex"
                    if not final_tex.exists():
                        final_tex.write_text(latex_code, encoding="utf-8")
                        logger.info(f"[LangGraph:{task_id}] fact_check: pre-wrote {final_tex}")

                # 写出求解结果到 solves.json（优先 final/，回退根目录）
                solver_output = results.get("solver_agent") or {}
                solves = solver_output.get("sub_problem_solutions", []) if isinstance(solver_output, dict) else []
                if solves:
                    solves_file = output_dir / "final" / "solves.json"
                    if not solves_file.exists():
                        solves_file.parent.mkdir(parents=True, exist_ok=True)
                        solves_file.write_text(
                            json.dumps(solves, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8",
                        )
                        logger.info(f"[LangGraph:{task_id}] fact_check: pre-wrote {solves_file}")
            except Exception as prewrite_exc:
                logger.warning(f"[LangGraph:{task_id}] fact_check pre-write failed: {prewrite_exc}")

            report = get_fact_checker().check(
                task_id=task_id,
                output_dir=output_dir,
            )

        # v7.2: 检查 fabrication flags（从 solver/modeler 传递过来）
        fabrication_issues = []
        for agent_name, agent_output in results.items():
            if isinstance(agent_output, dict):
                flags = agent_output.get("_fabrication_flags", [])
                score = agent_output.get("_fabrication_score", 0)
                if flags:
                    fabrication_issues.extend([f"[{agent_name}] {f}" for f in flags])
                if score > 0.5:
                    fabrication_issues.append(f"[{agent_name}] fabrication_score={score:.2f} (>0.5)")

        if fabrication_issues:
            report["fabrication_issues"] = fabrication_issues
            report["fabrication_warning"] = (
                f"检测到 {len(fabrication_issues)} 个潜在编造内容，建议人工审核后方可提交。"
            )
            logger.warning(f"Task {task_id}: fabrication issues detected: {fabrication_issues}")

        # 数值一致性检查
        if not report.get("passed"):
            report["review_required"] = True
            logger.warning(f"Task {task_id}: fact_check FAILED, review required")

        # ===== 保存事实核查报告到磁盘 + 通知用户 =====
        issue_count = report.get("issue_count", 0)
        has_issues = not report.get("passed") or fabrication_issues
        if has_issues:
            # 持久化报告到 final/ 目录
            try:
                if output_dir:
                    report_path = output_dir / "final" / "fact_check_report.json"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                    logger.info(f"Task {task_id}: fact_check report saved to {report_path}")
            except Exception as disk_exc:
                logger.warning(f"Task {task_id}: fact_check report save failed: {disk_exc}")

            # 通知用户具体问题
            issues_summary = []
            if not report.get("passed"):
                numeric_issues = report.get("issues", [])
                for iss in numeric_issues[:5]:
                    msg = iss.get("message", "") if isinstance(iss, dict) else str(iss)
                    issues_summary.append(msg)
            if fabrication_issues:
                issues_summary.extend(fabrication_issues[:3])

            self._post_chat(
                task_id, "coordinator",
                f"⚠️ 事实核查发现问题：{issue_count} 处数值不一致，"
                f"{len(fabrication_issues)} 处疑似编造。\n"
                + ("\n".join(f"  - {s}" for s in issues_summary[:5]) if issues_summary else "")
                + "\n报告已保存至 final/fact_check_report.json，请人工审核后修正。",
            )
        else:
            self._post_chat(task_id, "coordinator", "✅ 事实核查通过：论文数值与求解结果一致")

        self._set_result(state, "fact_checker", report)
        logger.info(f"Task {task_id}: fact_check passed={report['passed']} issues={report['issue_count']} fabrication={len(fabrication_issues)}")

        return {**state, "results": {**state.get("results", {}), "fact_checker": report}, "current_step": "fact_check_done"}

    async def _node_compliance_check(self, state: TaskState) -> TaskState:
        """v8.0: 金融报告合规审查 — 非 financial_analysis 模板直接跳过。

        检测到违规后，将清洗后的文本回写到 writer_agent 结果中，
        同时更新磁盘上的 final/main.tex。
        """
        template = state.get("paper_template", "")
        if template != "financial_analysis":
            return {**state, "current_step": "compliance_check_skipped"}

        task_id = state["task_id"]
        results = self._resolve_results(state)
        writer_output = results.get("writer_agent", {})
        report_text = ""
        if isinstance(writer_output, dict):
            report_text = writer_output.get("latex_code", "") or writer_output.get("abstract", "")

        if not report_text:
            logger.info(f"[LangGraph:{task_id}] compliance_check: 无论文内容，跳过")
            return {**state, "current_step": "compliance_check_skipped"}

        try:
            from ..agents.compliance_agent import ComplianceAgent
            agent = ComplianceAgent()
            result = await agent.execute(
                task_input={"report_text": report_text, "language": "zh"},
                context={},
            )
            violations = result.get("violations", [])
            cleaned_text = result.get("cleaned_text", "")
            if violations:
                logger.warning(f"[LangGraph:{task_id}] compliance_check: 检测到 {len(violations)} 个违规")
                writer_output["_compliance_violations"] = violations

            # ===== 回写清洗后文本到 writer_agent 结果和磁盘 =====
            if cleaned_text and cleaned_text != report_text and isinstance(writer_output, dict):
                # 更新 writer 结果中的 latex_code
                writer_output["latex_code"] = cleaned_text
                writer_output["_compliance_cleaned"] = True
                self._set_result(state, "writer_agent", writer_output)
                # 同步更新磁盘文件
                try:
                    output_dir = get_project_output_dir(state.get("project_name"))
                    final_tex = output_dir / "final" / "main.tex"
                    if final_tex.exists():
                        final_tex.write_text(cleaned_text, encoding="utf-8")
                    papers_tex = output_dir / "papers" / f"paper_{task_id}.tex"
                    if papers_tex.exists():
                        papers_tex.write_text(cleaned_text, encoding="utf-8")
                    logger.info(f"[LangGraph:{task_id}] compliance cleaned text written back to disk")
                except Exception as disk_exc:
                    logger.warning(f"[LangGraph:{task_id}] compliance text disk write failed: {disk_exc}")
                self._post_chat(
                    task_id, "compliance_agent",
                    f"⚠️ 合规审查：检测到 {len(violations)} 处违规投顾话术，已自动清洗并添加免责声明",
                )

            self._set_result(state, "compliance_agent", result)
            logger.info(f"[LangGraph:{task_id}] compliance_check done, passed={result.get('passed', True)}")
            return {**state, "results": {**state.get("results", {}), "compliance_agent": result}, "current_step": "compliance_check_done"}
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] compliance_check 失败: {e}")
            return {**state, "current_step": "compliance_check_failed"}

    async def _node_cannot_solve(self, state: TaskState) -> TaskState:
        report = {
            "task_id": state["task_id"],
            "reason": state.get("cannot_solve_report") or "无法继续求解",
            "solver_attempts": state.get("solver_attempts", []),
        }
        logger.warning(f"Task {state['task_id']} cannot_solve: {report['reason']}")
        return {**state, "current_step": "cannot_solve", "cannot_solve_report": report}

    async def _node_self_collect(self, state: TaskState) -> TaskState:
        """自主搜集数据：根据 preflight 的缺失数据描述，调用 self_collector 搜索并下载。"""
        task_id = state["task_id"]
        preflight = state.get("preflight") or {}

        # 获取缺失数据描述和搜索关键词
        missing_desc = preflight.get("missing_data_description", "")
        collect_keywords = preflight.get("collect_keywords", [])
        if not missing_desc and not collect_keywords:
            logger.warning(f"[LangGraph:{task_id}] self_collect: 无缺失数据描述，跳过")
            return {**state, "current_step": "self_collect_skipped", "phase": "self_collected"}

        self._update_progress(task_id, state["problem_text"], 12, "自主收集数据中")
        self._post_chat(task_id, "coordinator", f"🔍 正在自主收集数据：{missing_desc or ', '.join(collect_keywords)}")

        try:
            # 1. 搜索数据 URL（使用 web_search MCP 工具或内置搜索）
            search_query = missing_desc or " ".join(collect_keywords)
            urls = []
            try:
                from ..services.self_collector import extract_urls_from_search_result
                # 尝试使用 research_agent 的搜索能力查找数据集
                research_agent = self.agents.get("research_agent")
                if research_agent:
                    search_result = await research_agent.execute(
                        task_input={
                            "action": "search_datasets",
                            "query": search_query,
                            "limit": 5,
                        },
                        context={"problem_text": state["problem_text"]},
                    )
                    urls = extract_urls_from_search_result(search_result)
            except Exception as e:
                logger.warning(f"[LangGraph:{task_id}] 数据集搜索失败: {e}")

            # 2. 下载数据
            collected_files = []
            if urls:
                from ..services.self_collector import collect_urls
                download_results = await collect_urls(
                    urls=urls,
                    project_name=state.get("project_name"),
                    source_query=search_query,
                    concurrency=4,
                    timeout_sec=30,
                    max_size_mb=50,
                )
                collected_files = [r.filename for r in download_results if r.filename]
                failed = [r.url for r in download_results if r.error]
                if failed:
                    logger.warning(f"[LangGraph:{task_id}] 部分下载失败: {failed}")

            # 3. 更新 state
            if collected_files:
                self._post_chat(
                    task_id, "coordinator",
                    f"✅ 自主收集完成：下载了 {len(collected_files)} 个数据文件"
                )
                # 将新文件加入 files 列表
                existing_files = list(state.get("files", []) or [])
                from ..core.paths import get_project_data_subdir
                data_dir = get_project_data_subdir(state.get("project_name"), "self_collected")
                new_paths = [str(data_dir / f) for f in collected_files]
                updated_files = existing_files + new_paths
                return {
                    **state,
                    "files": updated_files,
                    "current_step": "self_collect_done",
                    "phase": "self_collected",
                    "self_collected_files": collected_files,
                }
            else:
                self._post_chat(
                    task_id, "coordinator",
                    "⚠️ 自主收集未找到数据，任务将继续但可能缺少数据支持"
                )
                return {
                    **state,
                    "current_step": "self_collect_failed",
                    "phase": "self_collected",
                    "cannot_solve_report": {
                        "reason": "自主数据收集失败：未找到可用数据源",
                        "suggestion": "请手动上传数据文件后重试",
                    },
                }
        except Exception as e:
            logger.error(f"[LangGraph:{task_id}] self_collect 节点异常: {e}")
            return {
                **state,
                "current_step": "self_collect_error",
                "phase": "self_collected",
                "cannot_solve_report": {
                    "reason": f"自主数据收集异常: {e}",
                    "suggestion": "请手动上传数据文件后重试",
                },
            }

    async def _node_discuss_approach(self, state: TaskState) -> TaskState:
        """多 Agent 讨论：分析师、研究员、建模专家讨论研究方案。

        每个 Agent 看到其他 Agent 的分析结果后给出自己的意见，
        形成讨论记录，最终由协调者综合决策。
        """
        task_id = state["task_id"]
        problem_text = state["problem_text"]
        results = self._resolve_results(state)
        room = get_chat_room(task_id)

        # 基础参与者
        participants = ["analyzer_agent", "research_agent"]

        # 动态选择建模专家
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent = self._select_modeling_agent(template, workflow_type)
        if modeling_agent == "modeler_agent":
            participants.append("modeler_agent")
        elif modeling_agent == "algorithm_engineer_agent":
            participants.append("algorithm_engineer_agent")
        elif modeling_agent == "financial_analyst_agent":
            participants.append("financial_analyst_agent")
        # 空字符串则不追加建模专家

        discussion_points = []

        # 构造讨论上下文
        context_summary = []
        for agent_name in ["analyzer_agent", "data_agent", "research_agent"]:
            out = results.get(agent_name, {})
            if out:
                summary = str(out)[:300]
                context_summary.append(f"【{agent_name}】{summary}")

        discuss_prompt = (
            f"## 研究课题讨论\n\n"
            f"**问题**：{problem_text[:300]}\n\n"
            f"**已有分析**：\n" + "\n".join(context_summary) + "\n\n"
            f"请从你的专业角度给出：\n"
            f"1. 对研究方向的建议\n"
            f"2. 推荐的建模方法\n"
            f"3. 潜在风险和注意事项\n"
            f"4. 创新点建议\n"
            f"请简洁回答（100字以内）。"
        )

        for agent_name in participants:
            agent = self.agents.get(agent_name)
            if not agent:
                continue
            try:
                resp = await agent.call_llm([
                    {"role": "system", "content": f"你是{self._agent_context(state).get('chat_room', room).team.get(agent_name, {}).get('role', agent_name) if room else agent_name}。请参与团队讨论。"},
                    {"role": "user", "content": discuss_prompt},
                ], temperature=0.5)
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    discussion_points.append({"agent": agent_name, "opinion": content})
                    if room:
                        room.post(agent_name, f"💡 {content}", "discussion")
            except Exception as exc:
                logger.debug(f"Discuss from {agent_name} failed: {exc}")

        # 协调者综合决策
        if discussion_points and room:
            opinions = "\n".join([f"- {d['agent']}: {d['opinion']}" for d in discussion_points])
            room.post("coordinator", f"📋 讨论总结：\n{opinions}\n\n综合各方意见，继续推进研究。", "discussion")

        self._post_chat(task_id, "coordinator", f"团队讨论完成，{len(discussion_points)} 位 Agent 参与")
        ref_update = self._set_result(state, "discussion", discussion_points)
        return {
            **state,
            "current_step": "discuss_done",
            "results": {**state.get("results", {}), **ref_update},
        }

    async def _node_wait_user(self, state: TaskState) -> TaskState:
        """检查用户输入，有则注入 context 继续执行"""
        task_id = state["task_id"]
        room = get_chat_room(task_id)

        if room:
            # 检查是否有新用户消息
            last_check = state.get("last_input_check", 0)
            user_msgs = room.get_user_messages_since(since=last_check)

            if user_msgs:
                new_msgs = [{"sender": m.sender, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in user_msgs]
                all_msgs = state.get("user_messages", [])
                all_msgs.extend(new_msgs)
                room.post("coordinator", f"📝 收到 {len(new_msgs)} 条用户反馈，继续执行并调整...", "broadcast")

                return {
                    **state,
                    "user_messages": all_msgs,
                    "last_input_check": time.time(),
                    "current_step": "processing_user_feedback",
                    "should_pause": False,
                }

            # 无用户消息，直接继续
            room.post("coordinator", "🔄 继续自动执行...", "broadcast")

        return {**state, "current_step": "auto_continuing", "should_pause": False}

    # ------------------------------------------------------------------
    # 条件路由
    # ------------------------------------------------------------------
    def _route_preflight(self, state: TaskState) -> str:
        preflight = state.get("preflight") or {}

        # 已经过 self_collect 阶段 → 直接按 workflow_type 走（避免无限循环）
        if state.get("phase") == "self_collected":
            workflow = state.get("workflow_type", "standard")
            if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
                return workflow
            return "standard"

        # 无 preflight 报告时使用 state 中的 workflow_type（兼容旧流程）
        if not preflight:
            workflow = state.get("workflow_type", "standard")
            if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
                return workflow
            return "standard"

        # 综述/调研类任务不需要数据文件，直接走 deep_research 工作流
        template = preflight.get("recommended_template", "")
        workflow = preflight.get("recommended_workflow", state.get("workflow_type", "standard"))
        if template == "research_survey" or workflow == "deep_research":
            if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
                return workflow
            return "deep_research"

        adequacy = preflight.get("data_adequacy", "sufficient")
        if adequacy == "missing" and preflight.get("llm_should_collect"):
            return "self_collect"
        if adequacy == "missing":
            return "abort"
        if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
            return workflow
        return "standard"

    def _route_peer_review(self, state: TaskState) -> str:
        review = self._resolve_results(state).get("peer_review_agent", {})
        rec = (review.get("recommendation") or "").lower()
        score = review.get("overall_score", 0)

        # 用户已关闭自评/迭代优化 → 直接接受，不进入修订循环
        if not state.get("use_critique", True):
            logger.info(f"[LangGraph:{state['task_id']}] use_critique=False, peer review 直接通过")
            return "accept"

        if rec == "accept" or score >= 4.0:
            return "accept"
        if rec == "reject":
            return "abort"

        # v7.2: 全自动模式 — 不再等待用户，直接自动迭代
        # 优先从 writer_agent 结果读取修订次数，fallback 到顶层 state
        writer_result = self._resolve_results(state).get("writer_agent", {})
        revision_count = writer_result.get("_revision_count", 0) if isinstance(writer_result, dict) else 0
        revision_count = revision_count or state.get("revision_count", 0)
        logger.info(f"[LangGraph:{state['task_id']}] peer review route: rec={rec}, score={score}, revision_count={revision_count}")

        # 3 次修订后直接接受（不再等待用户）
        if revision_count >= 3:
            logger.info(f"[LangGraph:{state['task_id']}] auto-accept after {revision_count} revisions (score={score})")
            return "accept"

        # v8.1: 按缺陷类型路由 — 区分文笔问题 vs 实验/数据问题
        defect_type = self._classify_review_defects(review)
        logger.info(f"[LangGraph:{state['task_id']}] defect_type={defect_type}")

        # 记录 claims 追溯信息
        trace_entry = {
            "timestamp": datetime.now().isoformat(),
            "revision_count": revision_count,
            "defect_type": defect_type,
            "review_score": score,
            "recommendation": rec,
            "suggested_edits": review.get("suggested_edits", []),
            "major_comments": review.get("comments", {}).get("major", []),
            "reproducibility_score": review.get("reproducibility", {}).get("score", 3),
        }
        claims_trace = state.get("claims_trace", [])
        claims_trace.append(trace_entry)

        if defect_type == "experiment":
            # 缺少实验 / 消融不足 / 基线不公平 → 回到 experiment
            return "experiment"
        elif defect_type == "solver":
            # 数字矛盾 / 结果不合理 → 回到 solver 重新计算
            return "iterative_solver"
        else:
            # 文笔问题 / 其他 → 回到 writer
            return "revise"

    def _route_solver(self, state: TaskState) -> str:
        attempts = state.get("solver_attempts", [])
        escalation = state.get("escalation_count", 0)

        if not attempts:
            return "retry"

        last = attempts[-1]
        if last.get("execution_success"):
            return "success"

        if len(attempts) >= self.cfg.max_solver_iterations:
            if escalation >= self.cfg.max_solver_escalations:
                return "abort"
            return "escalate"

        return "retry"

    def _classify_review_defects(self, review: Dict[str, Any]) -> str:
        """分析 peer_review 输出，判断缺陷类型。

        Returns:
            "experiment" — 缺少实验 / 消融不足 / 基线不公平
            "solver" — 数字矛盾 / 结果不合理
            "writer" — 文笔问题 / 其他
        """
        suggested_edits = review.get("suggested_edits", [])
        comments = review.get("comments", {})
        major_comments = comments.get("major", [])
        reproducibility = review.get("reproducibility", {})

        # 关键词匹配规则
        experiment_keywords = [
            "实验", "experiment", "消融", "ablation", "基线", "baseline",
            "对比实验", "对比方法", "SOTA", "state-of-the-art", "reproducibility",
            "复现", "随机种子", "random seed", "超参数", "hyperparameter",
            "数据集", "dataset", "训练", "training", "评估", "evaluation",
        ]

        solver_keywords = [
            "数字", "结果", "数值", "矛盾", "不一致", "inconsistent",
            "误差", "error", "精度", "accuracy", "收敛", "convergence",
            "失败", "failed", "异常", "anomaly", "不合理", "unreasonable",
        ]

        # 检查 suggested_edits
        experiment_score = 0
        solver_score = 0

        for edit in suggested_edits:
            target = (edit.get("target") or "").lower()
            change = (edit.get("change") or "").lower()
            text = f"{target} {change}"

            for kw in experiment_keywords:
                if kw.lower() in text:
                    experiment_score += 1

            for kw in solver_keywords:
                if kw.lower() in text:
                    solver_score += 1

        # 检查 major comments
        for comment in major_comments:
            comment_lower = comment.lower()
            for kw in experiment_keywords:
                if kw.lower() in comment_lower:
                    experiment_score += 2  # major comment 权重更高

            for kw in solver_keywords:
                if kw.lower() in comment_lower:
                    solver_score += 2

        # 检查 reproducibility 分数
        repro_score = reproducibility.get("score", 3)
        if repro_score <= 2:
            experiment_score += 3

        # 检查 soundness 分数（技术严谨性）
        scores = review.get("scores", {})
        soundness = scores.get("soundness", 3)
        if soundness <= 2:
            solver_score += 2

        logger.debug(f"Defect scores: experiment={experiment_score}, solver={solver_score}")

        # 决策
        if experiment_score >= 3 and experiment_score > solver_score:
            return "experiment"
        elif solver_score >= 3 and solver_score > experiment_score:
            return "solver"
        else:
            return "writer"

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _agent_context(self, state: TaskState) -> Dict[str, Any]:
        """构造传给 Agent.execute 的 context（模板感知）。"""
        room = get_chat_room(state["task_id"])
        results = self._resolve_results(state)
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")

        # 合并 model + solve 的 section_results（writer_agent 期望 list[dict]）
        modeler_output = results.get("modeler_agent", {})
        solver_output = results.get("solver_agent", {})
        models = modeler_output.get("sub_problem_models", [])
        solutions = solver_output.get("sub_problem_solutions", [])
        sub_problems = state.get("sub_problems", [])

        section_results = []
        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            model = next((m for m in models if m.get("sub_problem_id") == sp_id), {})
            solve = next((s for s in solutions if s.get("sub_problem_id") == sp_id), {})
            section_results.append(
                {
                    "sub_problem_id": sp_id,
                    "sub_problem_name": sp.get("name", ""),
                    "sub_problem_desc": sp.get("description", ""),
                    "model": model,
                    "solve": solve,
                }
            )

        # 基础上下文
        ctx = {
            "problem_text": state["problem_text"],
            "chat_room": room,
            "task_id": state["task_id"],
            "data_files": state.get("files", []),
            "knowledge_base_id": state.get("knowledge_base_id"),
            "task_kb_id": state.get("task_kb_id"),
            "workflow_type": workflow_type,
            "template": template,
            "results": results,
            "section_results": section_results,
            "sub_problems": sub_problems,
            "requirement_plan": state.get("requirement_plan"),  # 需求分解结果（所有Agent可读）
            "innovation_analysis": state.get("innovation_analysis"),  # 创新发现（所有Agent可读）
            "task_summary": state.get("task_summary"),  # 任务总结（所有Agent可读）
            "research_decision": state.get("research_decision"),  # v8.4.3: 投票决策（T1/T2 门控）
            "working_memory": self._get_working_memory(state["task_id"]),  # v8.4.6: 注入共享黑板，agent 可读
        }

        # 用户反馈注入
        user_messages = state.get("user_messages", [])
        user_feedback_text = ""
        if user_messages:
            latest = user_messages[-1]
            user_feedback_text = f"\n\n【用户最新指令】\n{latest.get('content', '')}\n\n请根据用户指令调整你的方案。如果用户指令与当前步骤无关，在输出中说明并继续原计划。"

        ctx["user_feedback_text"] = user_feedback_text
        ctx["user_messages"] = user_messages

        # ===== 模板特定上下文 =====
        research_output = results.get("research_agent", {})
        analyzer_output = results.get("analyzer_agent", {})

        if template == "research_survey":
            # 调研报告：重点是文献、研究空白、创新点
            ctx["literature"] = research_output.get("papers", []) if isinstance(research_output, dict) else []
            ctx["methods"] = research_output.get("methods", []) if isinstance(research_output, dict) else []
            ctx["research_gaps"] = analyzer_output.get("research_gaps", []) if isinstance(analyzer_output, dict) else []
            ctx["problem_type"] = analyzer_output.get("problem_type", "") if isinstance(analyzer_output, dict) else ""

        elif template in ("math_modeling", "coursework"):
            # 数学建模/课程作业：重点是模型、求解、数据
            ctx["modeling_approach"] = modeler_output.get("overall_approach", "") if isinstance(modeler_output, dict) else ""
            ctx["solver_results"] = solver_output.get("sub_problem_solutions", []) if isinstance(solver_output, dict) else []
            ctx["data_insights"] = results.get("data_agent", {}).get("insights", []) if isinstance(results.get("data_agent"), dict) else []

        elif template == "financial_analysis":
            # 金融分析：重点是金融数据、风险指标、回测结果
            financial_output = results.get("financial_analyst_agent", {})
            ctx["financial_models"] = financial_output.get("models", []) if isinstance(financial_output, dict) else []
            ctx["risk_metrics"] = financial_output.get("risk_metrics", {}) if isinstance(financial_output, dict) else {}
            ctx["backtest_results"] = financial_output.get("backtest", {}) if isinstance(financial_output, dict) else {}

        elif template in ("neurips_2024", "ieee_conference", "acm_sigconf", "springer_lncs"):
            # CCF-A 论文：重点是方法创新、实验对比、理论分析
            algo_output = results.get("algorithm_engineer_agent", {})
            ctx["algorithm_design"] = algo_output.get("algorithm_design", "") if isinstance(algo_output, dict) else ""
            ctx["complexity_analysis"] = algo_output.get("complexity_analysis", "") if isinstance(algo_output, dict) else ""
            ctx["experiment_plan"] = algo_output.get("experiment_plan", {}) if isinstance(algo_output, dict) else {}
            ctx["literature"] = research_output.get("papers", []) if isinstance(research_output, dict) else []
            ctx["methods"] = research_output.get("methods", []) if isinstance(research_output, dict) else []

        return ctx

    def _collect_degraded_markers(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """递归收集所有结果中的 _degraded 标记"""
        degraded = []

        def _scan(obj: Any, path: str = ""):
            if isinstance(obj, dict):
                if obj.get("_degraded"):
                    degraded.append({
                        "path": path or "root",
                        "agent": obj.get("_degraded_by", "unknown"),
                        "reason": obj.get("_degraded_reason", ""),
                    })
                for k, v in obj.items():
                    _scan(v, f"{path}.{k}" if path else k)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _scan(item, f"{path}[{i}]")

        for agent_name, output in results.items():
            if agent_name.startswith("_"):
                continue
            _scan(output, agent_name)

        return degraded

    def _save_results(self, task_id: str, state: TaskState) -> None:
        """持久化结果到 task_result.json 和 checkpoints。"""
        from ..core.task_persistence import save_task_result, save_task_checkpoint, save_task_metadata, save_task_messages
        results = self._resolve_results(state)

        # 将 state 级别的字段合并到 results 中（这些不经过 result_store）
        for key in ("requirement_plan", "innovation_analysis", "task_summary"):
            val = state.get(key)
            if val is not None:
                results[key] = val

        # 收集所有降级标记，生成质量报告
        degraded_items = self._collect_degraded_markers(results)
        if degraded_items:
            results["_quality_report"] = {
                "total_degraded": len(degraded_items),
                "degraded_items": degraded_items,
                "warning": "部分环节因服务不可用而降级生成，内容可能不准确，请人工审核标记为 [DEGRADED] 的部分",
            }
            logger.warning(f"[LangGraph:{task_id}] 质量报告: {len(degraded_items)} 个降级项")

        if results:
            save_task_result(task_id, {"task_id": task_id, "output": results})
            for agent_name, output in results.items():
                try:
                    save_task_checkpoint(task_id, "langgraph", agent_name, output)
                except Exception as exc:
                    logger.debug(f"Checkpoint save failed for {agent_name}: {exc}")

        # ===== 保存输出文件到项目目录（代码 / 论文 / 模型 / 求解结果）=====
        project_name = state.get("project_name")
        writer_ok = "writer_agent" in results
        try:
            saved_files = self._save_output_files(
                task_id, state.get("problem_text", ""), results,
                project_name=project_name,
            )
            if saved_files:
                self._post_chat(task_id, "coordinator", f"已保存 {len(saved_files)} 个文件到 output 目录")
        except Exception as exc:
            logger.error(f"[LangGraph:{task_id}] 保存输出文件失败: {exc}")

        # ===== 组装交付文件夹（项目名_日期）=====
        if writer_ok:
            try:
                from ..services.deliverable import assemble_deliverable
                task_output_dir = get_project_output_dir(project_name)
                # 收集聊天室事件作为时间线
                chat_events = []
                try:
                    room = get_chat_room(task_id)
                    if room:
                        chat_events = [
                            {"timestamp": getattr(m, "timestamp", ""), "agent": getattr(m, "sender", ""),
                             "message": getattr(m, "content", str(m))}
                            for m in (room.get_messages() or [])
                        ]
                except Exception:
                    pass
                deliverable_path = assemble_deliverable(
                    task_id=task_id,
                    output_dir=task_output_dir,
                    results=results,
                    state=state,
                    project_name=project_name,
                    chat_events=chat_events,
                )
                if deliverable_path:
                    self._post_chat(
                        task_id, "coordinator",
                        f"📁 交付文件夹已生成: {deliverable_path.name}/（含论文、参考文献、数据、实验日志、参数等）",
                    )
                    logger.info(f"[LangGraph:{task_id}] deliverable folder: {deliverable_path}")
            except Exception as dl_exc:
                logger.exception(f"[LangGraph:{task_id}] deliverable assembly failed: {dl_exc}")

        # ===== Camera-Ready 打包（可选，兼容旧流程）=====
        if writer_ok:
            try:
                from ..services.camera_ready import collect_artifacts, build
                task_output_dir = get_project_output_dir(project_name)
                template = state.get("paper_template", "math_modeling")
                artifact = collect_artifacts(task_id, task_output_dir, template_id=template)
                cr_result = build(task_id, artifact, task_output_dir, make_zip=True, max_zip_mb=50)
                self._post_chat(
                    task_id, "coordinator",
                    f"📦 Camera-ready 打包完成：{cr_result.zip_path or 'N/A'}，"
                    f"编译验证={'通过' if cr_result.verification.get('success') else '未通过'}",
                )
                logger.info(f"[LangGraph:{task_id}] camera-ready done: {cr_result.zip_path}")
            except Exception as cr_exc:
                logger.exception(f"[LangGraph:{task_id}] camera-ready failed: {cr_exc}")

        # 保存聊天记录到磁盘
        try:
            room = get_chat_room(task_id)
            if room:
                msgs = room.get_messages()
                save_task_messages(task_id, msgs)
        except Exception as exc:
            logger.debug(f"Messages save failed: {exc}")

        # 提取经验教训到持久化记忆
        try:
            from ..core.memory import get_memory_manager
            mm = get_memory_manager()
            mm.extract_lessons_from_result(task_id, results)
            # 提取文献/方法经验
            mm.extract_literature_lessons(task_id, results)
            logger.info(f"[LangGraph:{task_id}] 经验教训已提取到记忆系统")
        except Exception as exc:
            logger.debug(f"Lessons extraction failed: {exc}")

        # 标记任务完成状态
        cannot_solve = state.get("cannot_solve_report")
        # 检测是否有 agent 失败（writer 缺失 → 视为任务失败）
        writer_ok = "writer_agent" in results

        # 当跳过建模时，不再强制要求 solver_agent 结果
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent = self._select_modeling_agent(template, workflow_type)
        skip_modeling = not modeling_agent

        solver_ok = "solver_agent" in results or skip_modeling

        critical_missing = (
            state.get("workflow_type") == "standard"
            and (not writer_ok or not solver_ok)
        )
        error_msg = ""
        if cannot_solve:
            error_msg = str(cannot_solve.get("reason", "无法求解"))
        elif critical_missing:
            missing = []
            if not writer_ok:
                missing.append("writer_agent")
            if not solver_ok:
                missing.append("solver_agent")
            error_msg = f"关键 Agent 缺失: {', '.join(missing)}"

        # v7.2: 检查是否需要暂停（should_pause 标志）
        should_pause = state.get("should_pause", False)

        if cannot_solve or critical_missing:
            save_task_metadata(
                task_id=task_id, problem_text=state.get("problem_text", ""),
                status="failed", created_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
                error=error_msg,
            )
        elif should_pause:
            # 暂停状态：任务未完成，等待用户输入
            save_task_metadata(
                task_id=task_id, problem_text=state.get("problem_text", ""),
                status="paused", created_at=datetime.now().isoformat(),
                error="等待用户反馈",
            )
        else:
            save_task_metadata(
                task_id=task_id, problem_text=state.get("problem_text", ""),
                status="completed", created_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
                progress=100, current_step="已完成",
            )

    # ------------------------------------------------------------------
    # 节点辅助方法
    # ------------------------------------------------------------------
    def _update_progress(self, task_id: str, problem_text: str, progress: int, step: str) -> None:
        """更新任务进度到持久化（同时保存 checkpoint 用于断点续传）。"""
        from ..core.task_persistence import save_task_metadata, save_task_checkpoint
        try:
            save_task_metadata(
                task_id=task_id, problem_text=problem_text,
                status="running", created_at=datetime.now().isoformat(),
                progress=progress, current_step=step,
            )
        except Exception:
            pass
        # 增量保存 checkpoint，用于断点续传
        try:
            save_task_checkpoint(task_id, "langgraph", step, {"progress": progress, "step": step})
        except Exception:
            pass

    def _get_working_memory(self, task_id: str):
        """获取任务的 WorkingMemory 黑板。

        v8.4.6: 原代码调 mm.get_task_memory(task_id)——MemoryManager 没有此方法
        （正确方法为 get_working / create_task_memory），被 try/except 吞掉后永远
        返回 None，导致 12 处 wm.set_result/add_* 全是死代码、共享黑板形同虚设。
        修复：优先 get_working，未创建则 create_task_memory 兜底。
        """
        try:
            mm = get_memory_manager()
            wm = mm.get_working(task_id)
            if wm is None:
                wm, _ = mm.create_task_memory(task_id)
            return wm
        except Exception:
            return None

    def _post_chat(self, task_id: str, sender: str, message: str) -> None:
        """向 ChatRoom 发送消息。"""
        try:
            room = get_chat_room(task_id)
            if room:
                room.post(sender, message, "broadcast")
        except Exception as e:
            logger.debug(f"[LangGraph:{task_id}] ChatRoom 消息发送失败: {e}")

    def _save_output_files(
        self,
        task_id: str,
        problem_text: str,
        results: Dict[str, Any],
        project_name: Optional[str] = None,
    ) -> List[str]:
        """将求解器生成的代码和论文写入项目输出目录（与经典编排器保持一致）。

        Returns:
            已保存的文件路径列表。
        """
        output_dir = get_project_output_dir(project_name)
        code_dir = output_dir / "code"
        papers_dir = output_dir / "papers"
        code_dir.mkdir(parents=True, exist_ok=True)
        papers_dir.mkdir(parents=True, exist_ok=True)

        saved_files: List[str] = []

        # ===== 1. 保存代码文件 =====
        solver_output = results.get("solver_agent") or {}
        solves = solver_output.get("sub_problem_solutions", []) if isinstance(solver_output, dict) else []
        for sol in solves:
            sp_id = sol.get("sub_problem_id", "?")
            code_files = sol.get("code_files", [])
            for cf in code_files:
                filename = cf.get("filename", f"solver_sub{sp_id}.py")
                code_content = cf.get("code", "")
                if code_content:
                    filepath = code_dir / filename
                    filepath.write_text(code_content, encoding="utf-8")
                    saved_files.append(str(filepath))
                    # 保存对应的执行结果
                    numerical = sol.get("numerical_results", {})
                    if numerical and isinstance(numerical, dict):
                        result_file = code_dir / f"{filepath.stem}_result.json"
                        result_file.write_text(
                            json.dumps(numerical, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        saved_files.append(str(result_file))

        # ===== 2. 保存论文（LaTeX）=====
        writer_output = results.get("writer_agent") or {}
        latex_code = writer_output.get("latex_code", "") if isinstance(writer_output, dict) else ""
        if latex_code:
            paper_file = papers_dir / f"paper_{task_id}.tex"
            paper_file.write_text(latex_code, encoding="utf-8")
            saved_files.append(str(paper_file))
            # Markdown 版本
            md_code = writer_output.get("markdown_code", "") or writer_output.get("content", "")
            if md_code and len(md_code) > 100:
                md_file = papers_dir / f"paper_{task_id}.md"
                md_file.write_text(md_code, encoding="utf-8")
                saved_files.append(str(md_file))
            # 复制到 final/main.tex 供 camera-ready collect_artifacts 读取
            final_dir = output_dir / "final"
            final_dir.mkdir(parents=True, exist_ok=True)
            final_tex = final_dir / "main.tex"
            final_tex.write_text(latex_code, encoding="utf-8")
            saved_files.append(str(final_tex))
            # 保存 solution.json
            final_solution = final_dir / "solution.json"
            final_solution.write_text(
                json.dumps({
                    "title": writer_output.get("title", ""),
                    "abstract": writer_output.get("abstract", ""),
                    "keywords": writer_output.get("keywords", []),
                    "solver_agent": solver_output,
                    "writer_agent": writer_output,
                }, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            saved_files.append(str(final_solution))

        # ===== 3. 保存完整模型描述 JSON =====
        modeler_output = results.get("modeler_agent") or {}
        models = modeler_output.get("sub_problem_models", []) if isinstance(modeler_output, dict) else []
        if models:
            models_file = output_dir / "models.json"
            models_file.write_text(
                json.dumps(models, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            saved_files.append(str(models_file))

        # ===== 4. 保存完整求解结果 JSON =====
        if solves:
            solves_file = output_dir / "solves.json"
            solves_file.write_text(
                json.dumps(solves, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            saved_files.append(str(solves_file))

        logger.info(f"[LangGraph:{task_id}] 共保存 {len(saved_files)} 个输出文件到 output 目录")
        return saved_files
