"""项目真实数据资产发现 — 让求解器强制使用真实采集/上传数据。

背景：求解器（solver_agent）生成的代码曾用 ``np.random`` 模拟数据而非读取
系统采集/用户上传的真数据，导致回测、IC、绩效等结果失真且与论文正文不一致。
根因双重断裂：① prompt 只给数据 schema 不给可复制即用的读数代码；② 沙箱
执行时数据文件不在 LLM 代码可访问范围。

本模块提供统一入口，扫描项目数据目录（采集 + 上传），返回带绝对路径、
行数、列名的数据资产清单，供：
- solver prompt 注入 ``load_dataset()`` 用法（见 [[paper-quality-hardening]]）
- sandbox 写入 ``utils.py`` 数据加载器 + 挂载数据目录到 allowed_paths
- code_audit 判断「是否存在真实数据」以决定是否拦截合成数据

符合 [[no-local-binding-policy]]：路径全部由 get_project_data_dir 解析，
不绑定特定机器。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .paths import get_project_data_dir, _PROJECT_ROOT

# 支持读取的数据扩展名
_DATA_EXTS = (".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".json")

# 应排除的非数据文件名（索引/元数据/迁移标记等）
_EXCLUDE_NAMES = {"_index.json", ".migrated_v530"}


@dataclass
class DataAsset:
    """单个真实数据文件资产。"""
    name: str            # 文件名（如 hs300.csv）
    abs_path: str        # 绝对路径（solver 代码 / sandbox 用）
    rel_path: str        # 相对 _PROJECT_ROOT 的路径（prompt 展示 + LaTeX 用）
    ext: str             # 扩展名（决定读取方式）
    size_bytes: int = 0
    purpose: str = ""    # 数据用途说明（来自 _index.json.source_query / 上传备注）


@dataclass
class DataAssets:
    """项目全部可用真实数据资产。"""
    assets: List[DataAsset] = field(default_factory=list)
    data_dir: Optional[str] = None  # 数据所在目录绝对路径

    @property
    def empty(self) -> bool:
        return len(self.assets) == 0

    def primary(self) -> Optional[DataAsset]:
        """主数据文件（首个表格类文件），供单文件场景使用。"""
        for a in self.assets:
            if a.ext in (".csv", ".tsv", ".parquet", ".xlsx", ".xls", ".json"):
                return a
        return self.assets[0] if self.assets else None


def discover_data_assets(project_name: Optional[str]) -> DataAssets:
    """扫描项目数据目录，发现可用真实数据文件。

    扫描 outputs/<project>/data/ 下全部子目录（user_upload / self_collected 等），
    兼容旧版 data 根目录。返回 DataAssets（无数据时空清单，非异常）。
    """
    assets = DataAssets()
    if not project_name:
        return assets

    data_root = get_project_data_dir(project_name)
    assets.data_dir = str(data_root)
    if not data_root.exists():
        return assets

    # 读取各子目录的 _index.json，建立 文件名 -> 用途说明 的映射
    # （source_query 记录了该数据文件是为什么搜集的，供 LLM 判断该用哪个）
    purpose_map = _load_purpose_map(data_root)

    seen: set = set()
    for path in sorted(data_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _DATA_EXTS:
            continue
        if path.name in _EXCLUDE_NAMES:
            continue
        abs_p = str(path.resolve())
        if abs_p in seen:
            continue
        seen.add(abs_p)
        try:
            rel = str(path.relative_to(_PROJECT_ROOT))
        except ValueError:
            rel = str(path)
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        assets.assets.append(DataAsset(
            name=path.name,
            abs_path=abs_p,
            rel_path=rel,
            ext=path.suffix.lower(),
            size_bytes=size,
            purpose=purpose_map.get(path.name, ""),
        ))
    return assets


def _load_purpose_map(data_root: Path) -> Dict[str, str]:
    """读取 data_root 下各子目录的 _index.json，返回 {文件名: 用途说明}。

    _index.json 由 self_collector 写入，每项含 filename + source_query（搜集意图）。
    user_uploads 通常无 _index.json，其用途靠文件名语义（由 LLM 判断）。
    """
    import json

    purpose: Dict[str, str] = {}
    for idx_file in data_root.rglob("_index.json"):
        try:
            data = json.loads(idx_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            fname = item.get("filename") or item.get("name")
            query = item.get("source_query") or item.get("description") or ""
            if fname and query:
                # source_query 可能很长（含搜集计划全文），截断到 200 字
                purpose[str(fname)] = str(query).strip()[:200]
    return purpose


def read_snippet_for(asset: DataAsset) -> str:
    """返回该数据文件可直接复制使用的 pandas 读取代码。"""
    p = asset.abs_path
    if asset.ext == ".csv":
        return f'pd.read_csv(r"{p}")'
    if asset.ext == ".tsv":
        return f'pd.read_csv(r"{p}", sep="\\t")'
    if asset.ext in (".xlsx", ".xls"):
        return f'pd.read_excel(r"{p}")'
    if asset.ext == ".parquet":
        return f'pd.read_parquet(r"{p}")'
    if asset.ext == ".json":
        return f'pd.read_json(r"{p}")'
    return f'pd.read_csv(r"{p}")'


_UTILS_PY_HEAD = '''"""系统提供的数据加载器 — 自动读取项目真实采集/上传数据。

由 sandbox 在执行求解器代码前注入此文件。求解器代码请调用：
    from utils import load_dataset, list_datasets
    df = load_dataset()          # 加载主数据集（首个表格文件）
    print(list_datasets())       # 列出全部可用数据文件

禁止用 np.random / 模拟几何布朗运动等合成数据替代——若存在真实数据，
代码审计会拦截合成数据。
"""
from __future__ import annotations
import os
from typing import Dict, List, Optional

import pandas as pd

'''

_UTILS_PY_BODY = '''# 由 sandbox 注入的真实数据清单：name -> abs_path
_DATASETS: Dict[str, str] = {datasets_repr}

_ORDER: List[str] = [x for x in _DATASETS.keys()]


def list_datasets() -> List[str]:
    """返回全部可用数据文件名。"""
    return list(_ORDER)


def load_dataset(name: Optional[str] = None):
    """加载真实数据文件。

    Args:
        name: 文件名（来自 list_datasets()）。None = 加载主数据集（首个表格）。
    """
    if not _DATASETS:
        raise RuntimeError(
            "无可用真实数据文件（load_dataset 为空）。请确认数据采集/上传已完成，"
            "或在任务中显式指定数据文件。"
        )
    if name is None:
        name = _ORDER[0]
    if name not in _DATASETS:
        raise KeyError(
            f"未知数据文件 {name!r}。可用：" + str(list_datasets()) + "。"
        )
    path = _DATASETS[name]
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".tsv"):
        _sep = "\\t" if ext == ".tsv" else ","
        # v8.4.6: 中文 CSV 常用 GBK/GB18030，单一 utf-8 会 UnicodeDecodeError。
        # 按编码候选链依次尝试，首个成功即返回。
        _encs = ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin-1")
        _last = None
        for _enc in _encs:
            try:
                return pd.read_csv(path, encoding=_enc, sep=_sep)
            except UnicodeDecodeError as _e:
                _last = _e
                continue
        raise _last
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".parquet":
        return pd.read_parquet(path)
    if ext == ".json":
        return pd.read_json(path)
    return pd.read_csv(path)
'''


def build_utils_py(assets: DataAssets) -> str:
    """生成注入 sandbox workspace 的 utils.py 内容（含真实数据清单）。"""
    datasets = {a.name: a.abs_path for a in assets.assets}
    # 仅 body 含 {datasets_repr} 占位符，head/body 的其它花括号是 Python 字面量，不参与 format
    body = _UTILS_PY_BODY.replace("{datasets_repr}", repr(datasets))
    return _UTILS_PY_HEAD + body


def build_prompt_block(assets: DataAssets) -> str:
    """生成注入 solver prompt 的「真实数据加载器」说明块。"""
    if assets.empty:
        return ""
    lines = [
        "## 真实数据加载器（系统提供，必须使用）",
        f"数据目录：{assets.data_dir}",
        f"可用数据文件（共 {len(assets.assets)} 个，附用途说明）：",
    ]
    for a in assets.assets:
        size_kb = a.size_bytes / 1024
        line = f"- `{a.name}`（{a.ext}，{size_kb:.0f} KB）"
        if a.purpose:
            line += f"  → 用途：{a.purpose}"
        lines.append(line)
    lines += [
        "",
        "【硬约束】你的代码必须通过系统数据加载器读取真实数据，禁止用 np.random / "
        "模拟几何布朗运动等合成数据。根据每个文件的「用途说明」选择该用的数据：",
        "```python",
        "from utils import load_dataset, list_datasets",
        "print(list_datasets())   # 查看可用文件",
        "df = load_dataset()       # 加载主数据集；多文件按用途指定 load_dataset('sh000300_沪深300_daily.csv')",
        "```",
        "若代码检测到合成数据而项目已有真实数据，将被代码审计拦截并要求重写。",
        f"单文件直接读取示例（如不使用加载器）：`{read_snippet_for(assets.primary())}`",
    ]
    return "\n".join(lines)


# 支持读取的 CSV 编码候选（按顺序尝试）。中国数学建模赛题 CSV 常用 GBK/GB18030，
# 而 utf-8 解码会 UnicodeDecodeError → 数据分析静默失败、solver load_dataset 崩溃。
# 本函数按 utf-8-sig → gbk → gb18030 → latin-1 依次 fallback，首个成功即返回。
_CSV_ENCODINGS_TRY = ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin-1")


def read_csv_safe(path, **kwargs):
    """读取 CSV，自动尝试多种编码（utf-8/gbk/gb18030/latin-1）。

    供 sandbox 注入的 utils.py 与 data_schema / data_agent 共用，避免中文 CSV
    在单一 utf-8 编码下崩溃。**kwargs 透传给 pd.read_csv（如 nrows、sep）。
    """
    import pandas as pd
    last_err = None
    for enc in _CSV_ENCODINGS_TRY:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError as e:
            last_err = e
            continue
        except Exception:
            # 非编码错误（如列数不匹配）直接用默认 utf-8 重抛
            raise
    # 全部编码失败 → 抛最后一个 UnicodeDecodeError
    raise last_err


def read_csv_safe_code(path_var: str) -> str:
    """生成在 utils.py 内联使用的 CSV 读取代码（含编码 fallback 链）。

    Args:
        path_var: Python 表达式字符串，求值为文件路径（如 ``path`` 或 ``r"/x/y.csv"``）。

    Returns:
        可直接嵌入 utils.py 的 Python 源码片段，逻辑等价于 read_csv_safe。
    """
    return (
        "    _encs = ('utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'latin-1')\n"
        "    _last = None\n"
        f"    for _enc in _encs:\n"
        "        try:\n"
        f"            return pd.read_csv({path_var}, encoding=_enc)\n"
        "        except UnicodeDecodeError as _e:\n"
        "            _last = _e\n"
        "            continue\n"
        "    raise _last\n"
    )
