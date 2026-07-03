"""数据分析师Agent - 上传、分析、预处理数据，并撰写Python代码进行深度分析"""
import json
import logging
import re
import io
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)


@AgentFactory.register("data_agent")
class DataAgent(BaseAgent):
    name = "data_agent"
    label = "数据分析师"
    description = "上传、分析、预处理数据，并撰写Python代码进行深度分析"
    default_model = ""

    def __init__(self, data_dir: str = "./data", **kwargs):
        super().__init__(**kwargs)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_system_prompt(self) -> str:
        return """你是一个专业的数据分析师，负责分析数学建模问题的数据集。
职责：
1. 分析数据结构（行数、列数、类型）
2. 识别数值变量和分类变量
3. 检测缺失值和异常值
4. 撰写Python代码对数据进行深度分析，包括描述性统计、相关性分析、分布特征等
5. 将分析代码和结果返回给建模师和协调者使用

重要：
- 当有数据文件时，必须撰写完整的Python代码（使用pandas/numpy）进行分析
- 代码必须能在Python 3.9+环境运行
- 分析结果需要包含：描述性统计、缺失值检测、数据分布样例、相关性矩阵
- 返回格式必须为严格JSON，代码写在 `code` 字段中，分析结果写在 `analysis` 字段中

返回格式（严格JSON）：
{
    "analyses": [
        {
            "file_name": "文件名.csv",
            "shape": [行数, 列数],
            "columns": ["列1", "列2"],
            "code": "import pandas as pd\\ndf = pd.read_csv(...)\\nprint(df.describe())",
            "analysis": {
                "shape": [行数, 列数],
                "numerical_columns": ["列1", "列2"],
                "categorical_columns": ["列3"],
                "data_quality": {"missing_rate": 0.0, "duplicates": 0, "outliers": []},
                "descriptive_stats": {"均值": {}, "标准差": {}, ...},
                "sample_data": [[行1数据], [行2数据], ...],
                "correlations": {},
                "insights": ["洞察1", "洞察2", "洞察3"],
                "modeling_suggestions": ["建议1", "建议2"]
            }
        }
    ],
    "summary": "分析了N个文件"
}"""

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """分析数据文件（基础结构分析）"""
        path = Path(file_path)
        suffix = path.suffix.lower()

        try:
            if suffix == ".csv":
                return self._analyze_csv(path)
            elif suffix in [".xlsx", ".xls"]:
                return self._analyze_excel(path)
            elif suffix == ".json":
                return self._analyze_json(path)
            elif suffix == ".txt":
                return self._analyze_txt(path)
            else:
                return {"error": f"Unsupported file type: {suffix}"}
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return {"error": str(e)}

    def execute_python_analysis(self, code: str, file_path: str) -> Dict[str, Any]:
        """执行Python分析代码并捕获结果（通过沙箱安全执行）"""
        import json as _json
        import tempfile

        path = Path(file_path)
        suffix = path.suffix.lower()

        # 读取数据到DataFrame
        try:
            if suffix == ".csv":
                load_code = f"df = pd.read_csv(r'{file_path}', encoding='utf-8-sig')\n"
            elif suffix in [".xlsx", ".xls"]:
                load_code = f"df = pd.read_excel(r'{file_path}')\n"
            elif suffix == ".json":
                load_code = f"df = pd.read_json(r'{file_path}', encoding='utf-8-sig')\n"
            else:
                return {"error": f"Unsupported for code execution: {suffix}"}
        except Exception:
            return {"error": "Unsupported file type for code execution"}

        # 构建完整代码：加载数据 + 用户代码 + 结果序列化
        result_path = Path(tempfile.mktemp(suffix=".json"))
        full_code = (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import json\n"
            f"{load_code}"
            f"{code}\n"
            "\n"
            "# --- 结果序列化（沙箱安全） ---\n"
            "import traceback as _tb\n"
            "_result = {'python_output': ''}\n"
            "try:\n"
            "    _df = df if 'df' in dir() else None\n"
            f"    if _df is not None and hasattr(_df, 'shape'):\n"
            "        _result['shape'] = list(_df.shape)\n"
            "        _result['columns'] = list(_df.columns)\n"
            "        _result['dtypes'] = {c: str(dt) for c, dt in _df.dtypes.items()}\n"
            "        _num = _df.select_dtypes(include='number').columns.tolist()\n"
            "        if _num:\n"
            "            _result['descriptive_stats'] = _df[_num].describe().to_dict()\n"
            "        _result['missing'] = _df.isnull().sum().to_dict()\n"
            "        _result['missing_rate'] = float(_df.isnull().sum().sum() / (_df.shape[0] * _df.shape[1]))\n"
            "        _result['duplicates'] = int(_df.duplicated().sum())\n"
            "        _result['sample_data'] = _df.head(5).fillna('N/A').values.tolist()\n"
            "        _result['sample_columns'] = list(_df.columns)\n"
            "        if len(_num) >= 2:\n"
            "            _result['correlations'] = _df[_num].corr().round(3).to_dict()\n"
            "        _cat = _df.select_dtypes(include='object').columns.tolist()\n"
            "        if _cat:\n"
            "            _result['categorical_columns'] = _cat\n"
            "            _result['categorical_unique'] = {c: int(_df[c].nunique()) for c in _cat}\n"
            "        _result['numerical_columns'] = _num\n"
            "except Exception as _e:\n"
            "    _result['python_error'] = str(_e)\n"
            f"with open(r'{result_path}', 'w') as _f:\n"
            "    json.dump(_result, _f, default=str, ensure_ascii=False)\n"
        )

        # 写入临时文件并执行
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(full_code)
            code_file = Path(tmp.name)

        try:
            from ..core.sandbox import CodeSandbox
            sandbox = CodeSandbox()
            result = sandbox.execute_file(code_file)

            if result.success and result_path.exists():
                import json as _json_read
                data = _json_read.loads(result_path.read_text(encoding="utf-8"))
                data["python_output"] = data.get("python_output", "")[:2000]
                return data
            else:
                return {
                    "python_error": result.message or "沙箱执行失败",
                    "code": code[:500],
                    "returncode": result.returncode,
                }
        except Exception as e:
            return {"python_error": str(e), "code": code[:500]}
        finally:
            code_file.unlink(missing_ok=True)
            result_path.unlink(missing_ok=True)

    def build_analysis_code(self, file_path: str, analysis_type: str = "full") -> str:
        """构建Python分析代码模板"""
        import os
        # 安全转义路径，防止代码注入
        safe_path = os.path.realpath(file_path).replace("\\", "\\\\").replace("'", "\\'")
        path = Path(file_path)
        suffix = path.suffix.lower()
        return f"""
import pandas as pd
import numpy as np

# 读取数据
df = pd.read_csv(r'{safe_path}', encoding='utf-8-sig')

# 基本信息
print('=== 数据基本信息 ===')
print(f'形状: {{df.shape}}')
print(f'列名: {{list(df.columns)}}')
print(f'数据类型:\\n{{df.dtypes}}')

# 描述性统计
print('\\n=== 描述性统计 ===')
print(df.describe())

# 缺失值检测
print('\\n=== 缺失值 ===')
missing = df.isnull().sum()
print(missing[missing > 0] if missing.sum() > 0 else '无缺失值')

# 重复行
print(f'\\n重复行数: {{df.duplicated().sum()}}')

# 数值列相关性
num_cols = df.select_dtypes(include='number').columns.tolist()
if len(num_cols) >= 2:
    print('\\n=== 相关性矩阵 ===')
    print(df[num_cols].corr().round(3))

# 分类列分布（前5类）
cat_cols = df.select_dtypes(include='object').columns.tolist()
for col in cat_cols[:3]:
    print(f'\\n=== {{col}} 分布 ===')
    print(df[col].value_counts().head())

print('\\n分析完成')
"""

    def _analyze_csv(self, path: Path) -> Dict[str, Any]:
        import csv
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return {"error": "CSV文件为空"}
            columns = reader.fieldnames or []
            numerical = [c for c in columns if rows and self._is_numerical(rows[0].get(c, ""))]
            categorical = [c for c in columns if c not in numerical]
            return {
                "shape": [len(rows), len(columns)],
                "basic_info": {"numerical_columns": numerical, "categorical_columns": categorical},
                "data_quality": {"missing_rate": 0.0, "duplicates": 0},
                "insights": [f"数据集包含{len(rows)}行{len(columns)}列", f"数值变量{len(numerical)}个", f"分类变量{len(categorical)}个"],
                "modeling_suggestions": ["建议使用描述性统计分析", "可考虑回归或分类模型"],
                "file_name": path.name,
                "file_size": path.stat().st_size,
            }

    def _analyze_excel(self, path: Path) -> Dict[str, Any]:
        try:
            import pandas as pd
            df = pd.read_excel(path)
            return {
                "shape": list(df.shape),
                "basic_info": {
                    "numerical_columns": [c for c in df.select_dtypes(include="number").columns],
                    "categorical_columns": [c for c in df.select_dtypes(include="object").columns],
                },
                "data_quality": {
                    "missing_rate": float(df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100),
                    "duplicates": int(df.duplicated().sum()),
                },
                "insights": [
                    f"数据集包含{df.shape[0]}行{df.shape[1]}列",
                    f"缺失率：{df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100:.1f}%",
                    f"重复行：{df.duplicated().sum()}行",
                ],
                "modeling_suggestions": ["根据数据类型选择合适的模型"],
                "file_name": path.name,
                "file_size": path.stat().st_size,
            }
        except ImportError:
            return {"error": "需要安装 pandas 和 openpyxl: pip install pandas openpyxl"}

    def _analyze_json(self, path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"shape": [len(data), len(data[0]) if data else 0], "type": "JSON array"}
        return {"shape": [1, len(data)], "type": "JSON object"}

    def _analyze_txt(self, path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return {"shape": [len(lines), 1], "type": "text file", "preview": "".join(lines[:5])}

    def _is_numerical(self, value: str) -> bool:
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        action = task_input.get("action", "analyze_data")
        data_files = context.get("data_files", [])

        if action == "analyze_data" and data_files:
            results = []
            for f in data_files:
                result = self.analyze_file(f)
                # 生成并执行Python分析代码
                code = self.build_analysis_code(f)
                py_result = self.execute_python_analysis(code, f)

                # 合并结果
                merged = {**result}
                if "python_error" not in py_result:
                    merged["python_analysis"] = {
                        k: v for k, v in py_result.items() if k not in ["python_output"]
                    }
                    if "insights" not in merged:
                        merged["insights"] = []
                    # 从分析结果提取洞察
                    if "shape" in py_result:
                        merged["insights"].insert(0, f"数据：{py_result['shape'][0]}行 × {py_result['shape'][1]}列")
                    if "descriptive_stats" in py_result:
                        stats = py_result["descriptive_stats"]
                        if "mean" in stats:
                            means = {c: round(v, 3) for c, v in stats["mean"].items() if c in py_result.get("numerical_columns", [])}
                            if means:
                                top_mean = max(means.items(), key=lambda x: x[1])
                                merged["insights"].append(f"均值最高列：{top_mean[0]} = {top_mean[1]}")
                    if "correlations" in py_result:
                        merged["insights"].append("已计算数值列相关性矩阵")
                    if "missing_rate" in py_result:
                        mr = py_result["missing_rate"]
                        if mr > 0:
                            merged["insights"].append(f"⚠ 数据缺失率：{mr*100:.1f}%")
                        else:
                            merged["insights"].append("✓ 数据无缺失值")
                    # 生成可用的分析代码
                    merged["code"] = code
                    merged["python_output"] = py_result.get("python_output", "")

                results.append(merged)

            # 通知协调者和建模师
            room = context.get("chat_room")
            if room:
                room.post("data_agent", f"📊 数据分析完成！分析了 {len(results)} 个文件。", "broadcast")
                for r in results:
                    room.post("data_agent", f"  - {r.get('file_name', '未知')}: {r.get('shape', '?')}", "broadcast")

            return {"analyses": results, "summary": f"分析了{len(results)}个数据文件"}
        return {"analyses": [], "summary": "暂无数据文件"}
