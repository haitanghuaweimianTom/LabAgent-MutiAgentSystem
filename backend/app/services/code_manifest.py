"""Code Manifest —— 复杂任务的代码拆分方案（Phase 3）。

与 [[code-generation-modular-preference]] 强一致：当 LLM 写复杂代码时，
**强制**按需拆分为多文件，避免单文件过长导致上下文稀释。

本模块提供：
- :class:`CodeFileSpec` —— 单个 .py 文件的规约
- :class:`CodeManifest` —— 整个任务的代码清单
- :func:`split_by_complexity` —— 根据行数/职责数自动给出拆分建议
- :func:`validate_manifest` —— 校验 LLM 给出的 manifest 是否满足硬规则
- :func:`render_files_block` —— 渲染给 LLM 的 manifest 提示词

硬规则（与 :file:`backend/app/agents/solver_agent.py` 中 FILE_SPLIT_RULES 一致）：
- 单一文件 > 300 行 → 必拆
- 涉及 ≥ 3 个职责（数据/模型/训练/评估/可视化）→ 必拆
- 子问题数 ≥ 2 → 必拆
- helper 函数被 ≥ 2 个下游复用 → 必拆
"""
from __future__ import annotations
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# 角色 → 推荐文件名后缀（命名约定）
ROLE_FILENAME_HINT = {
    "data_processing": "data_process",
    "model": "model",
    "train": "train",
    "evaluate": "eval",
    "visualize": "viz",
    "utility": "utils",
    "entry": "main",  # 入口
}


@dataclass
class CodeFileSpec:
    """单个 .py 文件的规约。"""

    path: str  # 如 "data_process_sub1.py"
    role: str  # data_processing / model / train / evaluate / visualize / utility / entry
    code: str = ""
    description: str = ""
    depends_on: List[str] = field(default_factory=list)  # 依赖的其他 file path
    entry_point: bool = False  # 是否入口文件（只能 1 个）

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeFileSpec":
        return cls(
            path=str(data.get("path", "solver.py")),
            role=str(data.get("role", "solver")),
            code=str(data.get("code", "")),
            description=str(data.get("description", "")),
            depends_on=list(data.get("depends_on", []) or []),
            entry_point=bool(data.get("entry_point", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CodeManifest:
    """整个任务的代码清单。"""

    files: List[CodeFileSpec] = field(default_factory=list)
    runner: str = "python"  # python / jupyter / shell
    notes: str = ""

    @property
    def entry(self) -> Optional[CodeFileSpec]:
        for f in self.files:
            if f.entry_point:
                return f
        return self.files[0] if self.files else None

    @property
    def total_loc(self) -> int:
        return sum(len(f.code.splitlines()) for f in self.files)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files": [f.to_dict() for f in self.files],
            "runner": self.runner,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeManifest":
        files = [CodeFileSpec.from_dict(f) for f in data.get("files", []) or []]
        return cls(
            files=files,
            runner=str(data.get("runner", "python")),
            notes=str(data.get("notes", "")),
        )


# ==================== 拆分建议 ====================

@dataclass
class SplitSuggestion:
    """根据问题复杂度给出拆分建议。"""

    should_split: bool
    reasons: List[str] = field(default_factory=list)
    suggested_files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def split_by_complexity(
    estimated_loc: int,
    roles: List[str],
    sub_problem_count: int = 1,
    reusable_helpers: int = 0,
) -> SplitSuggestion:
    """根据复杂度自动判断是否需要拆分 + 建议文件名。

    Args:
        estimated_loc: 估算总代码行数（含所有文件总和）。
        roles: 本任务涉及的职责列表（``"data_processing"`` / ``"model"`` /
            ``"train"`` / ``"evaluate"`` / ``"visualize"``）。
        sub_problem_count: 子问题数量。
        reusable_helpers: 计划被 ≥ 2 个下游复用的 helper 函数数量。

    Returns:
        :class:`SplitSuggestion`，含 should_split + reasons + suggested_files。
    """
    reasons: List[str] = []
    files: List[str] = []

    if estimated_loc > 300:
        reasons.append(f"estimated_loc={estimated_loc} > 300")
    if len(set(roles)) >= 3:
        reasons.append(f"roles={len(set(roles))} ≥ 3")
    if sub_problem_count >= 2:
        reasons.append(f"sub_problems={sub_problem_count} ≥ 2")
    if reusable_helpers >= 2:
        reasons.append(f"reusable_helpers={reusable_helpers} ≥ 2")

    if reasons:
        # 建议拆分：按 roles 派生
        for role in set(roles):
            hint = ROLE_FILENAME_HINT.get(role, role)
            if sub_problem_count >= 2:
                files.append(f"{hint}_sub1.py")
                if sub_problem_count >= 3:
                    files.append(f"{hint}_sub2.py")
            else:
                files.append(f"{hint}.py")
        files.append("utils.py")
        files.append("main.py")
        return SplitSuggestion(should_split=True, reasons=reasons, suggested_files=files)

    return SplitSuggestion(should_split=False, reasons=[], suggested_files=["solver.py"])


# ==================== 校验 ====================

@dataclass
class ValidationReport:
    """manifest 校验报告。"""

    valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_manifest(
    manifest: CodeManifest,
    estimated_loc: Optional[int] = None,
    role_count: Optional[int] = None,
    sub_problem_count: int = 1,
) -> ValidationReport:
    """校验 manifest 是否满足硬规则。

    Args:
        manifest: LLM 给出的代码清单。
        estimated_loc: 估算总行数（None 时从 manifest 自动计算）。
        role_count: 不同 role 的数量（None 时自动算）。
        sub_problem_count: 子问题数。

    Returns:
        :class:`ValidationReport`，valid=False 时阻断重写。
    """
    issues: List[str] = []
    warnings: List[str] = []

    if not manifest.files:
        issues.append("manifest.files is empty")
        return ValidationReport(valid=False, issues=issues, warnings=warnings)

    # 1. entry_point 检查
    entries = [f for f in manifest.files if f.entry_point]
    if len(entries) > 1:
        issues.append(f"manifest has {len(entries)} entry_point files (must be 0 or 1)")
    if len(entries) == 0 and len(manifest.files) > 1:
        warnings.append("multi-file manifest without explicit entry_point; using first file")

    # 2. path 唯一性
    paths = [f.path for f in manifest.files]
    if len(paths) != len(set(paths)):
        dups = [p for p in paths if paths.count(p) > 1]
        issues.append(f"duplicate file paths: {set(dups)}")

    # 3. 行数/职责数硬规则
    total_loc = estimated_loc if estimated_loc is not None else manifest.total_loc
    distinct_roles = role_count if role_count is not None else len({f.role for f in manifest.files})

    if len(manifest.files) == 1:
        if total_loc > 300:
            issues.append(
                f"single-file manifest with {total_loc} LOC > 300, must split (hard rule)"
            )
        if distinct_roles >= 3:
            issues.append(
                f"single-file manifest with {distinct_roles} roles, must split (hard rule)"
            )
        if sub_problem_count >= 2:
            issues.append(
                f"single-file manifest but {sub_problem_count} sub-problems, must split (hard rule)"
            )

    # 4. depends_on 合法性（每个依赖必须是已声明的文件）
    path_set = set(paths)
    for f in manifest.files:
        for dep in f.depends_on:
            if dep not in path_set:
                issues.append(f"file {f.path!r} depends on {dep!r} which is not in manifest")

    return ValidationReport(
        valid=len(issues) == 0,
        issues=issues,
        warnings=warnings,
    )


# ==================== LLM 提示词片段 ====================

CODE_MANIFEST_PROMPT = """

【代码 manifest 规范（必须遵守）】
请在返回 JSON 中给出 ``code_files`` 数组（**多文件时**用 manifest 格式），
每项形如：
```
{"path": "data_process_sub1.py", "role": "data_processing", "code": "完整Python", "description": "...", "entry_point": false}
```

【拆分硬规则】任一满足即必须拆为多文件：
- 单一文件 > 300 行
- 涉及 ≥ 3 个职责（data_processing / model / train / evaluate / visualize）
- 子问题数 ≥ 2
- helper 被 ≥ 2 个下游复用

命名约定：
- data_process_<sub_id>.py —— 数据处理
- model_<sub_id>.py —— 模型/算法定义
- train_<sub_id>.py —— 训练流程
- eval_<sub_id>.py —— 评估与指标
- viz_<sub_id>.py —— 图表生成
- utils.py —— 公共工具
- main.py —— 入口（多文件时必须有一个 ``entry_point: true``）

单文件时也建议给出 ``code_files=[{"path": "solver.py", "role": "solver", "code": "..."}]``。
"""


def render_files_block(manifest: CodeManifest) -> str:
    """把 manifest 渲染为可读的 summary 文本，供下游 writer / reviewer 使用。"""
    lines: List[str] = [f"# Code Manifest ({len(manifest.files)} files, {manifest.total_loc} LOC)"]
    for f in manifest.files:
        flags = []
        if f.entry_point:
            flags.append("ENTRY")
        if f.depends_on:
            flags.append("deps=" + ",".join(f.depends_on))
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"- {f.path} (role={f.role}){flag_str}: {f.description}")
    return "\n".join(lines)


# ==================== 解析 ====================

def parse_manifest_from_dict(data: Dict[str, Any]) -> CodeManifest:
    """从 LLM 返回的 dict 解析 manifest，容错处理缺字段。"""
    if not isinstance(data, dict):
        return CodeManifest()
    files_raw = data.get("files") or data.get("code_files") or []
    if not isinstance(files_raw, list):
        files_raw = []
    files: List[CodeFileSpec] = []
    for f in files_raw:
        if not isinstance(f, dict):
            continue
        files.append(CodeFileSpec.from_dict(f))
    return CodeManifest(
        files=files,
        runner=str(data.get("runner", "python")),
        notes=str(data.get("notes", "")),
    )


def parse_manifest_from_string(raw_text: str) -> CodeManifest:
    """从 LLM 原始输出（可能带 ```json 围栏）解析 manifest。"""
    if not raw_text:
        return CodeManifest()
    # 去掉 markdown 围栏
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw_text)
    if fenced:
        raw_text = fenced.group(1)
    # 找顶层 JSON
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        return CodeManifest()
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return CodeManifest()
    return parse_manifest_from_dict(data)
