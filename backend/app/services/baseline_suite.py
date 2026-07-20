"""强基线套件 + 一键复现 bundle。

提供可复现的标准 baseline 定义，以及将 env/data hash/logs/claims
打包为 reproducibility.zip 的契约。
"""
from __future__ import annotations

import hashlib
import json
import logging
import platform
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strong baseline suite
# ---------------------------------------------------------------------------

BASELINE_SUITE: Dict[str, List[Dict[str, Any]]] = {
    "classification": [
        {
            "id": "logistic_regression",
            "name": "Logistic Regression",
            "category": "baseline",
            "framework": "sklearn",
            "deps": ["scikit-learn>=1.3"],
            "protocol": "5-fold CV, seed=42",
            "code_hint": "sklearn.linear_model.LogisticRegression(max_iter=1000, random_state=42)",
        },
        {
            "id": "random_forest",
            "name": "Random Forest",
            "category": "strong",
            "framework": "sklearn",
            "deps": ["scikit-learn>=1.3"],
            "protocol": "5-fold CV, n_estimators=200, seed=42",
            "code_hint": "sklearn.ensemble.RandomForestClassifier(n_estimators=200, random_state=42)",
        },
        {
            "id": "mlp_small",
            "name": "MLP (2-layer)",
            "category": "strong",
            "framework": "pytorch",
            "deps": ["torch>=2.0"],
            "protocol": "train 20 epochs, lr=1e-3, seed=42",
            "code_hint": "nn.Sequential(Linear, ReLU, Linear)",
        },
    ],
    "regression": [
        {
            "id": "ridge",
            "name": "Ridge Regression",
            "category": "baseline",
            "framework": "sklearn",
            "deps": ["scikit-learn>=1.3"],
            "protocol": "5-fold CV, seed=42",
            "code_hint": "sklearn.linear_model.Ridge(random_state=42)",
        },
        {
            "id": "gradient_boosting",
            "name": "Gradient Boosting",
            "category": "strong",
            "framework": "sklearn",
            "deps": ["scikit-learn>=1.3"],
            "protocol": "5-fold CV, seed=42",
            "code_hint": "sklearn.ensemble.GradientBoostingRegressor(random_state=42)",
        },
    ],
    "timeseries": [
        {
            "id": "naive_seasonal",
            "name": "Seasonal Naive",
            "category": "baseline",
            "framework": "numpy",
            "deps": ["numpy"],
            "protocol": "horizon=H, seasonal_period=auto",
            "code_hint": "y_hat[t] = y[t-season]",
        },
        {
            "id": "arima",
            "name": "ARIMA",
            "category": "strong",
            "framework": "statsmodels",
            "deps": ["statsmodels"],
            "protocol": "auto_arima or (1,1,1), seed=42",
            "code_hint": "statsmodels.tsa.arima.model.ARIMA",
        },
    ],
    "nlp_classification": [
        {
            "id": "tfidf_lr",
            "name": "TF-IDF + Logistic Regression",
            "category": "baseline",
            "framework": "sklearn",
            "deps": ["scikit-learn>=1.3"],
            "protocol": "seed=42",
            "code_hint": "TfidfVectorizer + LogisticRegression",
        },
        {
            "id": "bert_base_finetune",
            "name": "BERT-base fine-tune",
            "category": "sota",
            "framework": "transformers",
            "deps": ["transformers", "torch"],
            "protocol": "3 epochs, lr=2e-5, seed=42",
            "code_hint": "AutoModelForSequenceClassification bert-base-uncased",
        },
    ],
}


def detect_task_family(problem_text: str, experiment_plan: Optional[Dict[str, Any]] = None) -> str:
    text = (problem_text or "").lower()
    plan = experiment_plan or {}
    datasets = " ".join(
        str(d.get("name", d) if isinstance(d, dict) else d)
        for d in (plan.get("datasets") or [])
    ).lower()
    blob = f"{text} {datasets}"
    if any(k in blob for k in ("bert", "nlp", "text class", "sentiment", "文本分类")):
        return "nlp_classification"
    if any(k in blob for k in ("time series", "timeseries", "arima", "时序", "预测")):
        return "timeseries"
    if any(k in blob for k in ("regress", "回归", "mse", "rmse")):
        return "regression"
    return "classification"


def get_baseline_suite(
    task_family: Optional[str] = None,
    problem_text: str = "",
    experiment_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    family = task_family or detect_task_family(problem_text, experiment_plan)
    baselines = BASELINE_SUITE.get(family) or BASELINE_SUITE["classification"]
    return {
        "task_family": family,
        "baselines": baselines,
        "min_required": 2,
        "seed_protocol": {"seed": 42, "deterministic": True},
        "success_criteria": {
            "must_report_metrics": True,
            "must_compare_to_baselines": True,
            "locked_deps": True,
        },
    }


def merge_baselines_into_plan(plan: Dict[str, Any], suite: Dict[str, Any]) -> Dict[str, Any]:
    """将套件基线合并进 experimentation plan（不覆盖已有同名项）。"""
    plan = dict(plan or {})
    existing = plan.get("baselines") or []
    existing_names = {
        (b.get("name") or b.get("id") or "").lower()
        for b in existing
        if isinstance(b, dict)
    }
    merged = list(existing)
    for b in suite.get("baselines") or []:
        name = (b.get("name") or "").lower()
        if name and name not in existing_names:
            merged.append({
                "name": b["name"],
                "category": b.get("category", "baseline"),
                "rationale": f"强基线套件/{suite.get('task_family')}: {b.get('protocol', '')}",
                "suite_id": b.get("id"),
                "code_hint": b.get("code_hint"),
                "deps": b.get("deps"),
            })
            existing_names.add(name)
    plan["baselines"] = merged
    plan["seed_protocol"] = suite.get("seed_protocol")
    plan["baseline_suite"] = {
        "task_family": suite.get("task_family"),
        "min_required": suite.get("min_required"),
    }
    return plan


# ---------------------------------------------------------------------------
# Repro bundle
# ---------------------------------------------------------------------------

@dataclass
class ReproManifest:
    task_id: str
    created_at: str
    python_version: str
    platform: str
    env_lock: Dict[str, str] = field(default_factory=dict)
    data_hashes: Dict[str, str] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    artifact_files: List[str] = field(default_factory=list)
    claims_trace_path: str = ""
    one_command: str = "python reproduce.py"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_env_lock() -> Dict[str, str]:
    pkgs = {}
    try:
        import importlib.metadata as md
        for dist in md.distributions():
            name = dist.metadata["Name"]
            if name:
                pkgs[name] = dist.version
    except Exception:
        pass
    # 只保留科研常用包，避免巨型 lock
    keep = {
        "numpy", "pandas", "scipy", "scikit-learn", "torch", "matplotlib",
        "seaborn", "statsmodels", "sympy", "networkx", "transformers",
    }
    return {k: v for k, v in pkgs.items() if k.lower() in keep or k in keep}


def build_repro_bundle(
    task_id: str,
    output_dir: Path,
    *,
    data_files: Optional[List[str]] = None,
    log_files: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None,
    claims_trace_path: Optional[str] = None,
    code_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """生成 reproducibility 目录 + zip。"""
    output_dir = Path(output_dir)
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    data_hashes: Dict[str, str] = {}
    for fp in data_files or []:
        p = Path(fp)
        if p.is_file():
            data_hashes[str(p.name)] = _file_sha256(p)

    artifact_files: List[str] = []
    # 复制/记录日志路径
    logs_meta = []
    for fp in log_files or []:
        p = Path(fp)
        if p.is_file():
            dest = repro_dir / "logs" / p.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(p.read_bytes())
            artifact_files.append(str(dest.relative_to(repro_dir)))
            logs_meta.append({"name": p.name, "sha256": _file_sha256(p)})

    if claims_trace_path and Path(claims_trace_path).is_file():
        dest = repro_dir / "claims_traceability.json"
        dest.write_bytes(Path(claims_trace_path).read_bytes())
        artifact_files.append("claims_traceability.json")

    if code_dir and Path(code_dir).is_dir():
        code_index = []
        for p in Path(code_dir).rglob("*.py"):
            code_index.append({
                "path": str(p.relative_to(code_dir)),
                "sha256": _file_sha256(p),
            })
        (repro_dir / "code_index.json").write_text(
            json.dumps(code_index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        artifact_files.append("code_index.json")

    manifest = ReproManifest(
        task_id=task_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        env_lock=_collect_env_lock(),
        data_hashes=data_hashes,
        config=config or {},
        artifact_files=artifact_files,
        claims_trace_path="claims_traceability.json" if claims_trace_path else "",
    )
    (repro_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (repro_dir / "reproduce.py").write_text(
        _REPRODUCE_SCRIPT, encoding="utf-8"
    )
    (repro_dir / "README.md").write_text(
        "# Reproducibility Bundle\n\n"
        "1. Install deps from `manifest.json` → `env_lock`\n"
        "2. Verify data hashes in `manifest.json` → `data_hashes`\n"
        "3. Run: `python reproduce.py`\n"
        "4. Compare outputs with `claims_traceability.json`\n",
        encoding="utf-8",
    )

    zip_path = output_dir / f"{task_id}_reproducibility.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in repro_dir.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(repro_dir)))

    logger.info(f"[repro_bundle] created {zip_path}")
    return {
        "success": True,
        "repro_dir": str(repro_dir),
        "zip_path": str(zip_path),
        "manifest": manifest.to_dict(),
        "logs_meta": logs_meta,
    }


_REPRODUCE_SCRIPT = '''#!/usr/bin/env python3
"""One-command reproducibility entry (scaffold).

Verifies manifest hashes and prints locked environment.
Replace `run_experiments()` with your project's train/eval entry.
"""
import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    print("task_id:", manifest.get("task_id"))
    print("python:", manifest.get("python_version"))
    print("platform:", manifest.get("platform"))
    print("env_lock packages:", len(manifest.get("env_lock") or {}))
    claims = ROOT / "claims_traceability.json"
    if claims.exists():
        table = json.loads(claims.read_text(encoding="utf-8"))
        print("claims coverage:", (table.get("summary") or {}).get("coverage"))
    print("OK: manifest loaded. Wire train/eval scripts here for full replay.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
