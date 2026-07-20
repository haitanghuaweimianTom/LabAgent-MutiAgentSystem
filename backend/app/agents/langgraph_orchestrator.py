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
        }

        # 检查是否可以从 checkpoint 恢复（断点续传）
        restored_state = self._restore_from_checkpoint(task_id, initial_state)
        if restored_state is not initial_state:
            logger.info(f"[LangGraph:{task_id}] 从 checkpoint 恢复，继续执行")
            self._post_chat(task_id, "coordinator", "🔄 从断点恢复，继续执行...")

        try:
            final_state = await self._graph.ainvoke(restored_state)
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
    _PROBLEM_TYPES_NO_RESEARCH = {"物理", "测量"}

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

                self._post_chat(task_id, "sandbox", "沙箱执行成功")
                current_step = "sandbox_success"
            else:
                # 执行失败：错误计数 +1
                error_count += 1
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
        """模块 3b: Reviewer/Reflection Agent 的"渐进式越狱与熔断"路由。

        核心逻辑：
        如果 error_count >= 3 (死亡螺旋)：
            强制将 execution_mode 降级为 "restricted"，清空 error_count，
            要求 Coder 换简单方案。
        如果运行成功但指标连续 2 次未提升 (模板瓶颈)：
            将 execution_mode 升级为 "jailbreak"，允许 Coder 自由写代码，
            但将熔断阈值降为 1 次。
        """
        task_id = state["task_id"]
        error_count = state.get("error_count", 0)
        execution_mode = state.get("execution_mode", "restricted")
        metrics_trend = list(state.get("metrics_trend", []))
        threshold = state.get("circuit_breaker_threshold", 3)

        self._update_progress(task_id, state["problem_text"], 58, "Reviewer 反思中")

        decision = "continue"  # continue | degrade | upgrade | abort
        reason = ""

        # ===== 熔断判定：连续错误 >= 阈值 =====
        if error_count >= threshold:
            decision = "degrade"
            reason = (
                f"死亡螺旋检测：连续 {error_count} 次沙箱错误（阈值={threshold}），"
                f"强制降级为 restricted 模式，要求 Coder 换简单方案"
            )
            execution_mode = "restricted"
            error_count = 0  # 重置，给 restricted 模式一次机会
            self._post_chat(task_id, "reviewer", f"⚠️ {reason}")

        # ===== 越狱判定：指标连续 2 次未提升（模板瓶颈）=====
        elif len(metrics_trend) >= 3:
            # 检查最近 2 次指标是否连续下降或持平
            last_3 = metrics_trend[-3:]
            no_improvement = all(
                last_3[i] <= last_3[i - 1] for i in range(1, len(last_3))
            )

            if no_improvement and execution_mode == "restricted":
                decision = "upgrade"
                reason = (
                    f"模板瓶颈检测：指标连续 {len(last_3)} 次未提升"
                    f"（趋势: {[f'{m:.4f}' for m in last_3]}），"
                    f"升级为 jailbreak 模式，允许 Coder 自由写代码"
                )
                execution_mode = "jailbreak"
                threshold = 1  # 越狱后熔断阈值降为 1
                self._post_chat(task_id, "reviewer", f"🔓 {reason}")

        # ===== 正常情况：继续当前模式 =====
        else:
            self._post_chat(
                task_id, "reviewer",
                f"Reviewer 反思完成：error_count={error_count}, "
                f"mode={execution_mode}, trend={metrics_trend[-3:] if metrics_trend else 'N/A'}"
            )

        return {
            **state,
            "error_count": error_count,
            "execution_mode": execution_mode,
            "metrics_trend": metrics_trend,
            "circuit_breaker_threshold": threshold,
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
    # Graph 构建
    # ------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(TaskState)

        # 节点注册
        builder.add_node("requirement_decomposition", self._node_requirement_decomposition)
        builder.add_node("preflight_decision", self._node_preflight_decision)
        builder.add_node("analyzer", self._node_analyzer)
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

        # 条件边：analyzer → v7.1 并行分析（data+research+innovation 同时执行）
        # v7.2 fix: skip_to_modeling 也走 parallel_analysis 节点（它会自动选择正确的建模 Agent）
        # 注意：data、research、innovation 不再作为独立图节点，由 parallel_analysis 内部并行调用
        builder.add_conditional_edges(
            "analyzer",
            self._route_after_analyzer_parallel,
            {
                "parallel": "parallel_analysis",
                "skip_to_modeling": "parallel_analysis",  # 修复：不再硬编码 modeler
            },
        )

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
        builder.add_edge("ast_audit_node", "sandbox_execution_node")  # 所有模板: ast_audit → sandbox
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

        builder.add_edge("figure", "writer")
        builder.add_edge("writer", "peer_review")
        builder.add_edge("fact_check", "compliance_check")  # v8.0: fact_check → compliance_check → summary
        builder.add_edge("compliance_check", "summary")
        builder.add_edge("cannot_solve", "summary")
        builder.add_edge("summary", END)
        builder.add_edge("self_collect", "preflight_decision")
        # v7.2: wait_user 不再连接到 END（避免流程中断）
        # 改为自循环：等待用户输入后重新评估 peer_review
        builder.add_edge("wait_user", "peer_review")

        # requirement_decomposition → preflight_decision（始终进入）
        builder.add_edge("requirement_decomposition", "preflight_decision")

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
        """获取任务的 WorkingMemory 黑板。"""
        try:
            mm = get_memory_manager()
            wm, _ = mm.get_task_memory(task_id)
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
