"""Claims ↔ Logs 追溯表。

将论文中的关键声明（key_claims / 数值）与求解结果、实验日志、provenance
记录关联，生成可审计的 claims_traceability.json。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


@dataclass
class ClaimTraceRow:
    claim_id: str
    claim_text: str
    chapter: str = ""
    claim_source: str = "writer"  # writer | latex | experiment
    evidence_type: str = "unlinked"  # solve | experiment_log | provenance | none
    evidence_path: str = ""
    evidence_value: Optional[float] = None
    matched_number: Optional[float] = None
    status: str = "unverified"  # verified | mismatch | missing_evidence | unverified
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimsTraceabilityTable:
    task_id: str
    created_at: str
    rows: List[ClaimTraceRow] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "rows": [r.to_dict() for r in self.rows],
            "summary": self.summary,
        }


def _extract_numbers(text: str) -> List[float]:
    vals: List[float] = []
    for m in _NUM_RE.findall(text or ""):
        try:
            vals.append(float(m))
        except ValueError:
            continue
    return vals


def _flatten_solve_numbers(obj: Any, prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            out.update(_flatten_solve_numbers(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            path = f"{prefix}[{i}]"
            out.update(_flatten_solve_numbers(v, path))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out[prefix] = float(obj)
    return out


def _nearest_match(target: float, candidates: Dict[str, float], rel_tol: float = 0.05):
    best_path, best_val, best_rel = None, None, None
    for path, val in candidates.items():
        if val == 0 and target == 0:
            return path, val, 0.0
        denom = max(abs(target), abs(val), 1e-12)
        rel = abs(target - val) / denom
        if best_rel is None or rel < best_rel:
            best_path, best_val, best_rel = path, val, rel
    if best_rel is not None and best_rel <= rel_tol:
        return best_path, best_val, best_rel
    return None, None, best_rel


def build_claims_traceability(
    task_id: str,
    *,
    key_claims: Optional[List[Dict[str, Any]]] = None,
    solve_results: Optional[Dict[str, Any]] = None,
    experiment_output: Optional[Dict[str, Any]] = None,
    provenance_records: Optional[List[Dict[str, Any]]] = None,
    fact_check_issues: Optional[List[Dict[str, Any]]] = None,
    rel_tol: float = 0.05,
) -> ClaimsTraceabilityTable:
    """构建 claims↔logs 追溯表。"""
    now = datetime.now(timezone.utc).isoformat()
    table = ClaimsTraceabilityTable(task_id=task_id, created_at=now)

    solve_nums = _flatten_solve_numbers(solve_results or {})
    # 实验聚合结果里的 metrics
    if experiment_output:
        agg = experiment_output.get("aggregated") or experiment_output.get("metrics") or {}
        if isinstance(agg, dict):
            solve_nums.update(_flatten_solve_numbers(agg, "experiment"))
        elif hasattr(agg, "to_dict"):
            solve_nums.update(_flatten_solve_numbers(agg.to_dict(), "experiment"))

    provenance_paths = []
    for rec in provenance_records or []:
        if isinstance(rec, dict):
            provenance_paths.append(rec.get("code_path") or rec.get("file_path") or "")

    claims = list(key_claims or [])
    if not claims and solve_nums:
        # 无显式 claim 时，用求解数值生成可追溯行
        for i, (path, val) in enumerate(list(solve_nums.items())[:50]):
            claims.append({
                "claim": f"结果 {path} = {val}",
                "chapter": "results",
                "evidence": path,
            })

    for i, claim in enumerate(claims):
        text = claim.get("claim") or claim.get("text") or str(claim)
        chapter = claim.get("chapter") or ""
        nums = _extract_numbers(text)
        row = ClaimTraceRow(
            claim_id=f"claim_{i+1:03d}",
            claim_text=text[:500],
            chapter=chapter,
            claim_source=claim.get("source", "writer"),
        )

        if not nums:
            # 尝试用 claim.evidence 字符串匹配 provenance
            ev = claim.get("evidence") or ""
            if ev and ev != "summary" and any(ev in p for p in provenance_paths):
                row.evidence_type = "provenance"
                row.evidence_path = next((p for p in provenance_paths if ev in p), ev)
                row.status = "verified"
                row.notes = "关联到执行 provenance"
            else:
                row.status = "unverified"
                row.notes = "声明中无可匹配数值"
            table.rows.append(row)
            continue

        target = nums[0]
        path, val, rel = _nearest_match(target, solve_nums, rel_tol=rel_tol)
        row.matched_number = target
        if path is not None:
            row.evidence_type = "solve" if not path.startswith("experiment") else "experiment_log"
            row.evidence_path = path
            row.evidence_value = val
            row.status = "verified"
            row.notes = f"相对误差={rel:.4f}" if rel is not None else ""
        else:
            row.status = "missing_evidence"
            row.notes = f"未在求解/实验日志中找到接近 {target} 的值"
        table.rows.append(row)

    # 合并 fact_check 问题为 mismatch 行
    for j, issue in enumerate(fact_check_issues or []):
        if not isinstance(issue, dict):
            continue
        table.rows.append(ClaimTraceRow(
            claim_id=f"fact_{j+1:03d}",
            claim_text=issue.get("message") or issue.get("context") or "fact_check issue",
            claim_source="fact_checker",
            evidence_type="solve",
            evidence_path=str(issue.get("solve_path") or ""),
            evidence_value=issue.get("solve_value"),
            matched_number=issue.get("latex_value"),
            status="mismatch",
            notes=issue.get("message") or "",
        ))

    verified = sum(1 for r in table.rows if r.status == "verified")
    mismatch = sum(1 for r in table.rows if r.status == "mismatch")
    missing = sum(1 for r in table.rows if r.status == "missing_evidence")
    table.summary = {
        "total": len(table.rows),
        "verified": verified,
        "mismatch": mismatch,
        "missing_evidence": missing,
        "unverified": len(table.rows) - verified - mismatch - missing,
        "coverage": round(verified / len(table.rows), 3) if table.rows else 0.0,
        "passed": mismatch == 0 and (verified > 0 or not table.rows),
    }
    return table


def save_claims_traceability(
    table: ClaimsTraceabilityTable,
    output_dir: Path,
    filename: str = "claims_traceability.json",
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(table.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[claims_traceability] saved {path} coverage={table.summary.get('coverage')}")
    return path
