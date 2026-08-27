"""Tests for Self-Healer Module."""
import json
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from self_healer import (
    ErrorSeverity,
    ErrorCategory,
    CollectedError,
    ErrorCollector,
    ErrorRouter,
    CircuitBreaker,
    SelfHealer,
)


class TestErrorSeverity:
    def test_severity_levels(self):
        assert ErrorSeverity.LOW == "low"
        assert ErrorSeverity.MEDIUM == "medium"
        assert ErrorSeverity.HIGH == "high"
        assert ErrorSeverity.CRITICAL == "critical"


class TestErrorCategory:
    def test_categories(self):
        assert ErrorCategory.SYNTAX == "syntax"
        assert ErrorCategory.IMPORT == "import"
        assert ErrorCategory.RUNTIME == "runtime"
        assert ErrorCategory.TIMEOUT == "timeout"
        assert ErrorCategory.MEMORY == "memory"
        assert ErrorCategory.API == "api"
        assert ErrorCategory.LOGIC == "logic"
        assert ErrorCategory.DATA == "data"
        assert ErrorCategory.UNKNOWN == "unknown"


class TestCollectedError:
    def test_creation(self):
        error = CollectedError(
            timestamp=1234567890.0,
            stage="step1",
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.MEDIUM,
            message="Test error",
        )
        assert error.stage == "step1"
        assert error.category == ErrorCategory.RUNTIME
        assert error.severity == ErrorSeverity.MEDIUM

    def test_to_dict(self):
        error = CollectedError(
            timestamp=1234567890.0,
            stage="step1",
            category=ErrorCategory.SYNTAX,
            severity=ErrorSeverity.HIGH,
            message="Syntax error",
        )
        d = error.to_dict()
        assert d["stage"] == "step1"
        assert d["category"] == "syntax"
        assert d["severity"] == "high"


class TestErrorCollector:
    def test_collect_exception(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        try:
            raise ValueError("Test error")
        except ValueError as e:
            error = collector.collect("step1", e)
        assert error.stage == "step1"
        assert error.category == ErrorCategory.UNKNOWN
        assert "Test error" in error.message

    def test_collect_string(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        error = collector.collect("step1", "Import failed")
        assert error.stage == "step1"
        assert error.message == "Import failed"

    def test_collect_import_error(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        error = collector.collect("step1", "No module named numpy")
        assert error.category == ErrorCategory.IMPORT

    def test_collect_timeout_error(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        error = collector.collect("step1", "Operation timed out")
        assert error.category == ErrorCategory.TIMEOUT

    def test_collect_syntax_error(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        error = collector.collect("step1", SyntaxError("invalid syntax"))
        assert error.category == ErrorCategory.SYNTAX

    def test_save_to_disk(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        collector.collect("step1", "Test error")
        errors_path = tmp_path / "errors" / "errors.jsonl"
        assert errors_path.exists()
        lines = errors_path.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_get_errors(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        collector.collect("step1", "Error 1")
        collector.collect("step2", "Error 2")
        errors = collector.get_errors()
        assert len(errors) == 2

    def test_get_errors_by_stage(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        collector.collect("step1", "Error 1")
        collector.collect("step1", "Error 2")
        collector.collect("step2", "Error 3")
        errors = collector.get_errors(stage="step1")
        assert len(errors) == 2

    def test_get_error_count(self, tmp_path):
        collector = ErrorCollector(tmp_path / "errors")
        assert collector.get_error_count() == 0
        collector.collect("step1", "Error")
        assert collector.get_error_count() == 1


class TestCircuitBreaker:
    def test_allows_attempts(self):
        cb = CircuitBreaker(max_attempts=3)
        assert cb.record_attempt("error1") is True
        assert cb.record_attempt("error1") is True
        assert cb.record_attempt("error1") is True

    def test_opens_after_max(self):
        cb = CircuitBreaker(max_attempts=2)
        cb.record_attempt("error1")
        cb.record_attempt("error1")
        assert cb.is_open("error1") is True

    def test_reset(self):
        cb = CircuitBreaker(max_attempts=2)
        cb.record_attempt("error1")
        cb.record_attempt("error1")
        cb.reset("error1")
        assert cb.is_open("error1") is False

    def test_different_errors_independent(self):
        cb = CircuitBreaker(max_attempts=2)
        cb.record_attempt("error1")
        cb.record_attempt("error1")
        assert cb.is_open("error1") is True
        assert cb.is_open("error2") is False


class TestSelfHealer:
    def test_handle_import_error(self, tmp_path):
        healer = SelfHealer(tmp_path)
        result = healer.handle_error("step1", "No module named numpy")
        assert result["can_fix"] is True
        assert "pip install numpy" in result["repair_suggestion"]

    def test_handle_syntax_error(self, tmp_path):
        healer = SelfHealer(tmp_path)
        result = healer.handle_error("step1", SyntaxError("invalid syntax"))
        assert result["can_fix"] is True

    def test_handle_timeout_error(self, tmp_path):
        healer = SelfHealer(tmp_path)
        result = healer.handle_error("step1", "Operation timed out")
        assert result["can_fix"] is True
        assert "Timeout" in result["repair_suggestion"]

    def test_circuit_breaker_prevents_loop(self, tmp_path):
        healer = SelfHealer(tmp_path)
        for _ in range(5):
            healer.handle_error("step1", "No module named test")
        result = healer.handle_error("step1", "No module named test")
        assert result["circuit_open"] is True

    def test_error_summary(self, tmp_path):
        healer = SelfHealer(tmp_path)
        healer.handle_error("step1", "Error 1")
        healer.handle_error("step2", "Error 2")
        summary = healer.get_error_summary()
        assert summary["total"] == 2
        assert "step1" in summary["by_stage"]
        assert "step2" in summary["by_stage"]

    def test_get_collector(self, tmp_path):
        healer = SelfHealer(tmp_path)
        collector = healer.get_collector()
        assert isinstance(collector, ErrorCollector)
