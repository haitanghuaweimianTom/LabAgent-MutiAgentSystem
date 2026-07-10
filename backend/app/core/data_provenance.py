"""数据血缘追踪 — Hash记录 + 执行日志 + 可复现包

所有输入数据计算SHA-256 Hash，实验日志、代码版本、运行环境记录，
打包生成Reproducibility Package。
"""

import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DataRecord:
    """数据记录"""
    file_path: str
    sha256: str
    size_bytes: int
    recorded_at: str
    source: str = ""  # "user_upload" | "self_collected" | "generated"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRecord:
    """执行记录"""
    code_path: str
    code_sha256: str
    executed_at: str
    duration_seconds: float
    success: bool
    python_version: str
    platform: str
    dependencies: Dict[str, str] = field(default_factory=dict)  # {包名: 版本}
    stdout_hash: str = ""
    stderr_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvenanceBundle:
    """数据血缘包"""
    task_id: str
    project_name: str
    created_at: str
    data_records: List[DataRecord] = field(default_factory=list)
    execution_records: List[ExecutionRecord] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def compute_file_hash(file_path: str) -> str:
    """计算文件SHA-256 Hash"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_content_hash(content: bytes) -> str:
    """计算内容SHA-256 Hash"""
    return hashlib.sha256(content).hexdigest()


def record_data_file(
    file_path: str,
    source: str = "user_upload",
    metadata: Optional[Dict[str, Any]] = None,
) -> DataRecord:
    """记录数据文件的Hash和元数据"""
    path = Path(file_path)
    sha256 = compute_file_hash(file_path)
    size = path.stat().st_size

    record = DataRecord(
        file_path=str(path.absolute()),
        sha256=sha256,
        size_bytes=size,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        metadata=metadata or {},
    )

    logger.info(f"[Provenance] 记录数据文件: {path.name} → {sha256[:16]}...")
    return record


def record_execution(
    code_path: str,
    success: bool,
    duration: float,
    stdout: str = "",
    stderr: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> ExecutionRecord:
    """记录代码执行"""
    code_sha256 = compute_file_hash(code_path) if os.path.exists(code_path) else ""

    # 收集依赖版本
    deps = {}
    try:
        import pkg_resources
        for pkg in ["numpy", "pandas", "scikit-learn", "torch", "tensorflow",
                     "matplotlib", "scipy", "xgboost", "lightgbm"]:
            try:
                deps[pkg] = pkg_resources.get_distribution(pkg).version
            except Exception:
                pass
    except ImportError:
        pass

    record = ExecutionRecord(
        code_path=code_path,
        code_sha256=code_sha256,
        executed_at=datetime.now(timezone.utc).isoformat(),
        duration_seconds=duration,
        success=success,
        python_version=sys.version.split()[0],
        platform=sys.platform,
        dependencies=deps,
        stdout_hash=compute_content_hash(stdout.encode()) if stdout else "",
        stderr_hash=compute_content_hash(stderr.encode()) if stderr else "",
        metadata=metadata or {},
    )

    logger.info(f"[Provenance] 记录执行: {Path(code_path).name} → {'成功' if success else '失败'}")
    return record


def build_provenance_bundle(
    task_id: str,
    project_name: str,
    data_records: List[DataRecord],
    execution_records: List[ExecutionRecord],
    metadata: Optional[Dict[str, Any]] = None,
) -> ProvenanceBundle:
    """构建数据血缘包"""
    return ProvenanceBundle(
        task_id=task_id,
        project_name=project_name,
        created_at=datetime.now(timezone.utc).isoformat(),
        data_records=data_records,
        execution_records=execution_records,
        metadata=metadata or {},
    )


def save_provenance(
    bundle: ProvenanceBundle,
    output_dir: str,
) -> str:
    """保存数据血缘包到文件

    Returns:
        保存的文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "provenance.json")

    data = {
        "task_id": bundle.task_id,
        "project_name": bundle.project_name,
        "created_at": bundle.created_at,
        "data_records": [asdict(r) for r in bundle.data_records],
        "execution_records": [asdict(r) for r in bundle.execution_records],
        "metadata": bundle.metadata,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"[Provenance] 血缘包已保存: {output_path}")
    return output_path
