"""核心路径管理 - 统一项目路径，避免硬编码

所有路径均相对于 backend/ 目录计算，
支持通过环境变量 PROJECT_ROOT 覆盖。
"""
import os
from pathlib import Path

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

# 输出目录（项目根下的 output/）
OUTPUT_DIR: Path = _PROJECT_ROOT / "output"

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


def ensure_dirs() -> None:
    """启动时确保所有必要目录存在"""
    get_data_dir()
    get_task_data_dir()
    get_output_dir()
