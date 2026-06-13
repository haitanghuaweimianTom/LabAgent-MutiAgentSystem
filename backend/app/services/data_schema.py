"""数据 schema 提取服务 —— 为 SolverAgent 提供结构化数据上下文"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class DataSchemaExtractor:
    """从数据文件中提取 schema：列名、类型、取值范围、缺失值、示例行"""

    SUPPORTED_EXTS = {".csv", ".xlsx", ".xls", ".parquet", ".json"}

    def extract(self, file_path: str | Path) -> Optional[Dict[str, Any]]:
        path = Path(file_path)
        if path.suffix.lower() not in self.SUPPORTED_EXTS:
            return None

        try:
            df = self._read_file(path)
            if df is None:
                return None

            columns = []
            for col in df.columns:
                series = df[col]
                dtype = str(series.dtype)
                sample_values = self._safe_sample(series)
                numeric_summary = None
                if pd.api.types.is_numeric_dtype(series):
                    numeric_summary = {
                        "min": self._to_json_safe(series.min()),
                        "max": self._to_json_safe(series.max()),
                        "mean": self._to_json_safe(series.mean()) if not series.empty else None,
                        "std": self._to_json_safe(series.std()) if not series.empty else None,
                    }

                columns.append({
                    "name": str(col),
                    "dtype": dtype,
                    "nullable": bool(series.isnull().any()),
                    "null_count": int(series.isnull().sum()),
                    "unique_count": int(series.nunique()),
                    "sample_values": sample_values,
                    "numeric_summary": numeric_summary,
                })

            return {
                "file_name": path.name,
                "file_path": str(path),
                "shape": [int(df.shape[0]), int(df.shape[1])],
                "columns": columns,
                "row_count": int(df.shape[0]),
                "column_count": int(df.shape[1]),
                "sample_rows": self._to_json_safe(df.head(5).to_dict(orient="records")),
            }
        except Exception as e:
            logger.warning(f"数据 schema 提取失败 {file_path}: {e}")
            return None

    def extract_multiple(self, file_paths: List[str | Path]) -> List[Dict[str, Any]]:
        results = []
        for fp in file_paths:
            schema = self.extract(fp)
            if schema:
                results.append(schema)
        return results

    def format_for_prompt(self, schemas: List[Dict[str, Any]]) -> str:
        """格式化为可注入 prompt 的文本"""
        if not schemas:
            return ""
        lines = ["## 数据文件 Schema（读取前必读）"]
        for s in schemas:
            lines.append(f"\n### {s['file_name']} ({s['row_count']}行 × {s['column_count']}列)")
            lines.append("| 列名 | 类型 | 可空 | 唯一值 | 示例值 | 数值范围 |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for col in s["columns"]:
                samples = ", ".join(str(v) for v in col["sample_values"])[:60]
                numeric = ""
                if col.get("numeric_summary"):
                    ns = col["numeric_summary"]
                    numeric = f"min={ns.get('min')}, max={ns.get('max')}"
                lines.append(
                    f"| {col['name']} | {col['dtype']} | {'是' if col['nullable'] else '否'} | "
                    f"{col['unique_count']} | {samples} | {numeric} |"
                )
            if s.get("sample_rows"):
                lines.append("\n前5行示例:")
                lines.append("```json")
                lines.append(json.dumps(s["sample_rows"], ensure_ascii=False, indent=2))
                lines.append("```")
        return "\n".join(lines)

    @staticmethod
    def _read_file(path: Path) -> Optional[pd.DataFrame]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        if suffix == ".parquet":
            return pd.read_parquet(path)
        if suffix == ".json":
            return pd.read_json(path)
        return None

    @staticmethod
    def _safe_sample(series: pd.Series, n: int = 3) -> List[Any]:
        try:
            non_null = series.dropna().astype(str).head(n)
            return [v for v in non_null.tolist()]
        except Exception:
            return []

    @staticmethod
    def _to_json_safe(value: Any) -> Any:
        import numpy as np
        if isinstance(value, (np.integer, np.floating)):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, float) and (np.isnan(value) if isinstance(value, float) else False):
            return None
        return value


_schema_extractor: Optional[DataSchemaExtractor] = None


def get_schema_extractor() -> DataSchemaExtractor:
    global _schema_extractor
    if _schema_extractor is None:
        _schema_extractor = DataSchemaExtractor()
    return _schema_extractor
