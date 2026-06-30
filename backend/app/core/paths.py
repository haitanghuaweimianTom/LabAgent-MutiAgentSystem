"""核心路径管理 - 统一项目路径，避免硬编码

所有路径均相对于 backend/ 目录计算，
支持通过环境变量 PROJECT_ROOT 覆盖。
"""
import os
import shutil
from pathlib import Path
from typing import Optional, List

# backend/app/core/paths.py → backend/app/ → backend/ → 项目根目录
# _BACKEND_DIR = backend/app/ (Path(__file__).parent.parent)
# _BACKEND_ROOT = backend/ (Path(__file__).parent.parent.parent)
_BACKEND_DIR = Path(__file__).parent.parent          # backend/app/
_BACKEND_ROOT = _BACKEND_DIR.parent                    # backend/

# math_modeling_multi_agent/ (项目根目录)
_PROJECT_ROOT = Path(os.environ.get(
    "PROJECT_ROOT",
    str(_BACKEND_ROOT.parent),
))

# 数据目录（backend/data/uploads）
DATA_DIR: Path = _BACKEND_ROOT / "data" / "uploads"

# 任务持久化目录
TASK_DATA_DIR: Path = _BACKEND_ROOT / "data" / "tasks"

# 全局输出目录（统一收拢到 outputs/_global，避免根目录同时存在 output/ 与 outputs/）
GLOBAL_PROJECT_NAME: str = "_global"
OUTPUT_DIR: Path = _PROJECT_ROOT / "outputs" / GLOBAL_PROJECT_NAME

# LaTeX模板目录（项目根下的 config/）
LATEX_TEMPLATE_DIR: Path = _PROJECT_ROOT / "config" / "latex_templates"


def get_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_task_data_dir() -> Path:
    TASK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return TASK_DATA_DIR


def get_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


# ===== 项目感知路径（v3.1 新增）=====

def get_project_base_dir(project_name: Optional[str]) -> Path:
    """获取项目根目录。无项目时返回全局项目根。"""
    if project_name:
        return _PROJECT_ROOT / "outputs" / project_name
    return _PROJECT_ROOT


def get_project_data_dir(project_name: Optional[str]) -> Path:
    """获取项目数据目录。无项目时回退到全局 uploads。

    v5.3.0: 返回的是"复合目录"，子目录由 get_project_data_subdir 决定。
    为了向后兼容，本函数仍返回 data 根目录（不做强制拆分），但 migrate_legacy_data_dir()
    会启动时一次性把旧文件移到 user_uploads/ 子目录。
    """
    if project_name:
        d = _PROJECT_ROOT / "outputs" / project_name / "data"
    else:
        d = DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_data_subdir(project_name: Optional[str], source: str) -> Path:
    """获取项目数据的子目录（按来源分）。

    Args:
        project_name: 项目名（None 时回退到全局 uploads）
        source: 'user_upload' 或 'self_collected'

    Returns:
        outputs/<name>/data/<source>/ 子目录（自动创建）

    向后兼容：如果 source='user_upload' 且旧文件在 data/ 根下，可通过
    migrate_legacy_data_dir() 在启动时一次性迁移。
    """
    base = get_project_data_dir(project_name)
    if source not in ("user_upload", "self_collected"):
        raise ValueError(f"invalid source: {source!r}; expected 'user_upload' or 'self_collected'")
    sub = base / source
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def get_project_output_dir(project_name: Optional[str]) -> Path:
    """获取项目输出目录。无项目时回退到全局 outputs/_global/。"""
    if project_name:
        d = _PROJECT_ROOT / "outputs" / project_name / "output"
    else:
        d = OUTPUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# ===== 数据迁移（v5.3.0）=====

# 迁移标记文件名（存在即表示已迁移）
_MIGRATION_MARKER = ".migrated_v530"

# 这些子目录名是"合法的"（迁移时跳过）
_DATA_SUBDIRS = {"user_uploads", "self_collected"}


def migrate_legacy_data_dir(verbose: bool = False) -> dict:
    """把 outputs/<name>/data/ 根下的旧文件移到 user_uploads/ 子目录。

    幂等：用 .migrated_v530 标记文件防重复迁移。

    Returns:
        {"projects_scanned": int, "files_moved": int, "skipped": int}
    """
    stats = {"projects_scanned": 0, "files_moved": 0, "skipped": 0}
    outputs_root = _PROJECT_ROOT / "outputs"
    if not outputs_root.exists():
        return stats

    for proj_dir in outputs_root.iterdir():
        if not proj_dir.is_dir() or proj_dir.name == GLOBAL_PROJECT_NAME:
            continue
        legacy_data = proj_dir / "data"
        if not legacy_data.exists() or not legacy_data.is_dir():
            continue

        stats["projects_scanned"] += 1

        # 已迁移过 → 跳过
        if (legacy_data / _MIGRATION_MARKER).exists():
            stats["skipped"] += 1
            continue

        target = legacy_data / "user_uploads"
        target.mkdir(parents=True, exist_ok=True)

        # 移动根目录下的文件 + 未知子目录到 user_uploads/
        for item in list(legacy_data.iterdir()):
            if item.name == _MIGRATION_MARKER:
                continue
            if item.name in _DATA_SUBDIRS:
                continue  # 已经是新结构 → 不动
            dest = target / item.name
            try:
                if item.is_file():
                    if dest.exists():
                        # 已存在同名文件 → 跳过（不要覆盖用户数据）
                        if verbose:
                            logger.info(f"migrate: skip existing {item}")
                        continue
                    shutil.move(str(item), str(dest))
                    stats["files_moved"] += 1
                elif item.is_dir():
                    # 未知子目录（如 self_collected_urls.txt 旧位置）→ 移走
                    if dest.exists():
                        continue
                    shutil.move(str(item), str(dest))
                    stats["files_moved"] += 1
            except Exception as e:
                # 单个文件失败不阻塞整个迁移
                if verbose:
                    logger.warning(f"migrate: failed to move {item}: {e}")

        # 写标记
        (legacy_data / _MIGRATION_MARKER).touch()
        if verbose:
            logger.info(
                f"migrate: project={proj_dir.name}, moved={stats['files_moved']}"
            )

    return stats


def ensure_dirs() -> None:
    """启动时确保所有必要目录存在"""
    get_data_dir()
    get_task_data_dir()
    get_output_dir()


# 加上 logger（兼容 verbose 输出）
import logging
logger = logging.getLogger(__name__)