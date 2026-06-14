"""Agent 输出契约校验（Harness 扩展 Phase 5）。

用 Pydantic 定义每个 Agent 期望输出的 schema，并在 LangGraph 节点中对
原始输出做验证。验证失败不阻断主流程，但会记录 warning/error 供下游决策。
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError


class AnalystOutput(BaseModel):
    sub_problems: List[Dict[str, Any]]
    problem_type: Optional[str] = None
    difficulty: Optional[str] = None
    keywords: List[str] = []
    summary: Optional[str] = None


class DataOutput(BaseModel):
    analyses: List[Dict[str, Any]] = []
    insights: List[str] = []
    schemas: List[Dict[str, Any]] = []


class ModelOutput(BaseModel):
    models: List[Dict[str, Any]] = []
    section_results: List[Dict[str, Any]] = []


class SolverOutput(BaseModel):
    sub_problem_solutions: List[Dict[str, Any]] = []
    execution_success: bool = False
    numerical_results: Dict[str, Any] = {}
    error: Optional[str] = None


class WriterOutput(BaseModel):
    latex_code: Optional[str] = None
    chapters: List[Dict[str, Any]] = []
    bib_entries: List[Dict[str, Any]] = []


AGENT_SCHEMAS = {
    "analyzer_agent": AnalystOutput,
    "data_agent": DataOutput,
    "modeler_agent": ModelOutput,
    "solver_agent": SolverOutput,
    "writer_agent": WriterOutput,
}


class ContractValidator:
    """Agent 输出 schema 校验器。"""

    def validate(self, agent_name: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """校验 agent 输出是否符合预定义 schema。

        Returns:
            {
                "valid": bool,
                "agent": str,
                "errors": List[str],
                "warnings": List[str],
            }
        """
        schema_cls = AGENT_SCHEMAS.get(agent_name)
        if schema_cls is None:
            return {
                "valid": True,
                "agent": agent_name,
                "errors": [],
                "warnings": [f"未定义 {agent_name} 的 schema，跳过校验"],
            }

        errors: List[str] = []
        warnings: List[str] = []
        try:
            schema_cls(**output)
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(x) for x in err.get("loc", []))
                msg = err.get("msg", "")
                errors.append(f"{loc}: {msg}")
        except Exception as e:
            errors.append(f"校验异常: {e}")

        # 业务级 warning
        if agent_name == "solver_agent" and not output.get("numerical_results"):
            warnings.append("numerical_results 为空")
        if agent_name == "writer_agent" and not output.get("latex_code"):
            warnings.append("latex_code 为空")

        return {
            "valid": len(errors) == 0,
            "agent": agent_name,
            "errors": errors,
            "warnings": warnings,
        }


_contract_validator: Optional[ContractValidator] = None


def get_contract_validator() -> ContractValidator:
    global _contract_validator
    if _contract_validator is None:
        _contract_validator = ContractValidator()
    return _contract_validator
