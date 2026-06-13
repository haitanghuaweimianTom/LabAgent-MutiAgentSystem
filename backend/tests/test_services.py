"""数据 schema 和结果验证服务测试"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.data_schema import DataSchemaExtractor
from app.services.result_validator import ResultValidator


def test_data_schema_extractor_csv(tmp_path: Path):
    """验证 CSV schema 提取"""
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["x", "y", "z"],
        "C": [1.1, 2.2, 3.3],
    })
    csv_path = tmp_path / "test.csv"
    df.to_csv(csv_path, index=False)

    extractor = DataSchemaExtractor()
    schema = extractor.extract(csv_path)
    assert schema is not None
    assert schema["row_count"] == 3
    assert schema["column_count"] == 3
    assert len(schema["columns"]) == 3
    assert schema["columns"][2]["dtype"].startswith("float")


def test_result_validator_detects_nan():
    """验证能检测 NaN"""
    validator = ResultValidator()
    report = validator.validate({"value": float("nan")})
    assert not report["valid"]
    assert any("NaN" in i["message"] for i in report["issues"])


def test_result_validator_detects_negative_thickness():
    """验证能检测负数厚度"""
    validator = ResultValidator()
    report = validator.validate({"thickness_um": -5.0})
    assert not report["valid"]
    assert any("负数" in i["message"] for i in report["issues"])


def test_result_validator_detects_r2_out_of_range():
    """验证 R2 范围检查"""
    validator = ResultValidator()
    report = validator.validate({"R2": 1.5}, {"model": {"model_name": "线性回归"}})
    assert not report["valid"]
    assert any("R²" in i["message"] for i in report["issues"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
