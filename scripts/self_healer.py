"""
Self-Healing System - Auto-Detect & Fix Runtime Errors

Inspired by Sibyl's self-heal module. Automatically detects errors,
diagnoses root causes, and attempts repairs.

Components:
- ErrorCollector: Structured error capture
- ErrorRouter: Route errors to appropriate fixers
- CircuitBreaker: Prevent infinite repair loops
- RepairOrchestrator: Coordinate repair attempts
"""

from __future__ import annotations

import ast
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = [
    "ErrorSeverity",
    "ErrorCategory",
    "CollectedError",
    "ErrorCollector",
    "ErrorRouter",
    "CircuitBreaker",
    "SelfHealer",
]

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error categories for routing to appropriate fixers."""
    SYNTAX = "syntax"
    IMPORT = "import"
    RUNTIME = "runtime"
    TIMEOUT = "timeout"
    MEMORY = "memory"
    API = "api"
    LOGIC = "logic"
    DATA = "data"
    UNKNOWN = "unknown"


@dataclass
class CollectedError:
    """Structured error capture."""
    timestamp: float
    stage: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    traceback: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    fix_attempts: int = 0
    fixed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "traceback": self.traceback,
            "context": self.context,
            "fix_attempts": self.fix_attempts,
            "fixed": self.fixed,
        }


class ErrorCollector:
    """Collect and store errors from pipeline stages."""

    def __init__(self, workspace_dir: Path | str) -> None:
        self._dir = Path(workspace_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._errors_path = self._dir / "errors.jsonl"
        self._errors: list[CollectedError] = []

    def collect(
        self,
        stage: str,
        error: Exception | str,
        *,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: dict[str, Any] | None = None,
    ) -> CollectedError:
        """Collect an error from a pipeline stage."""
        # Classify error
        category = self._classify_error(error)
        message = str(error) if isinstance(error, Exception) else error
        tb = ""

        if isinstance(error, Exception):
            import traceback
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        collected = CollectedError(
            timestamp=time.time(),
            stage=stage,
            category=category,
            severity=severity,
            message=message[:1000],
            traceback=tb[:2000],
            context=context or {},
        )

        self._errors.append(collected)
        self._save_error(collected)

        return collected

    def _classify_error(self, error: Exception | str) -> ErrorCategory:
        """Classify error into category."""
        text = str(error).lower()

        if isinstance(error, SyntaxError):
            return ErrorCategory.SYNTAX

        if any(kw in text for kw in ["import", "module", "no module named"]):
            return ErrorCategory.IMPORT
        if any(kw in text for kw in ["timeout", "timed out"]):
            return ErrorCategory.TIMEOUT
        if any(kw in text for kw in ["memory", "oom", "out of memory"]):
            return ErrorCategory.MEMORY
        if any(kw in text for kw in ["api", "rate limit", "429", "529"]):
            return ErrorCategory.API
        if any(kw in text for kw in ["keyerror", "indexerror", "typeerror", "valueerror"]):
            return ErrorCategory.RUNTIME

        return ErrorCategory.UNKNOWN

    def _save_error(self, error: CollectedError) -> None:
        """Save error to disk."""
        with self._errors_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(error.to_dict(), ensure_ascii=False) + "\n")

    def get_errors(self, stage: str | None = None) -> list[CollectedError]:
        """Get all errors, optionally filtered by stage."""
        if stage is None:
            return list(self._errors)
        return [e for e in self._errors if e.stage == stage]

    def get_error_count(self) -> int:
        """Get total error count."""
        return len(self._errors)

    def get_critical_count(self) -> int:
        """Get critical error count."""
        return sum(1 for e in self._errors if e.severity == ErrorSeverity.CRITICAL)


class ErrorRouter:
    """Route errors to appropriate fixers based on category."""

    def __init__(self) -> None:
        self._fixers: dict[ErrorCategory, Callable] = {}

    def register_fixer(self, category: ErrorCategory, fixer: Callable) -> None:
        """Register a fixer function for an error category."""
        self._fixers[category] = fixer

    def get_fixer(self, error: CollectedError) -> Callable | None:
        """Get the appropriate fixer for an error."""
        return self._fixers.get(error.category)

    def has_fixer(self, error: CollectedError) -> bool:
        """Check if a fixer exists for this error category."""
        return error.category in self._fixers


class CircuitBreaker:
    """Prevent infinite repair loops with circuit breaker pattern."""

    def __init__(self, max_attempts: int = 3, cooldown_seconds: float = 60.0) -> None:
        self._max_attempts = max_attempts
        self._cooldown = cooldown_seconds
        self._attempts: dict[str, list[float]] = {}

    def record_attempt(self, error_key: str) -> bool:
        """Record an attempt. Returns True if circuit is closed (can proceed)."""
        now = time.time()
        if error_key not in self._attempts:
            self._attempts[error_key] = []

        # Clean old attempts outside cooldown window
        self._attempts[error_key] = [
            t for t in self._attempts[error_key]
            if now - t < self._cooldown
        ]

        # Check if we've exceeded max attempts
        if len(self._attempts[error_key]) >= self._max_attempts:
            return False  # Circuit open

        self._attempts[error_key].append(now)
        return True  # Circuit closed

    def is_open(self, error_key: str) -> bool:
        """Check if circuit is open (too many attempts)."""
        now = time.time()
        if error_key not in self._attempts:
            return False

        recent = [
            t for t in self._attempts[error_key]
            if now - t < self._cooldown
        ]
        return len(recent) >= self._max_attempts

    def reset(self, error_key: str) -> None:
        """Reset circuit for an error key."""
        self._attempts.pop(error_key, None)


class SelfHealer:
    """Self-healing orchestrator that coordinates error detection and repair.

    Features:
    - Error collection and classification
    - Automatic repair attempts
    - Circuit breaker to prevent infinite loops
    - Structured error logging
    """

    def __init__(
        self,
        workspace_dir: Path | str,
        *,
        max_repair_attempts: int = 2,
    ) -> None:
        self._workspace = Path(workspace_dir)
        self._max_attempts = max_repair_attempts
        self._collector = ErrorCollector(workspace_dir)
        self._router = ErrorRouter()
        self._circuit = CircuitBreaker(max_attempts=3, cooldown_seconds=120)

        # Register default fixers
        self._register_default_fixers()

    def _register_default_fixers(self) -> None:
        """Register built-in fixers for common error categories."""
        self._router.register_fixer(ErrorCategory.IMPORT, self._fix_import_error)
        self._router.register_fixer(ErrorCategory.SYNTAX, self._fix_syntax_error)
        self._router.register_fixer(ErrorCategory.TIMEOUT, self._fix_timeout_error)

    def handle_error(
        self,
        stage: str,
        error: Exception | str,
        *,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle an error: collect, diagnose, and attempt repair.

        Returns:
            {
                "collected": CollectedError,
                "can_fix": bool,
                "fixed": bool,
                "repair_suggestion": str,
                "circuit_open": bool,
            }
        """
        # 1. Collect error
        collected = self._collector.collect(stage, error, context=context)

        # 2. Check circuit breaker
        error_key = f"{stage}:{collected.category.value}"
        circuit_open = self._circuit.is_open(error_key)

        if circuit_open:
            logger.warning(f"Circuit breaker open for {error_key}, skipping repair")
            return {
                "collected": collected,
                "can_fix": False,
                "fixed": False,
                "repair_suggestion": "Circuit breaker open - manual intervention required",
                "circuit_open": True,
            }

        # 3. Check if fixer exists
        fixer = self._router.get_fixer(collected)
        can_fix = fixer is not None

        if not can_fix:
            return {
                "collected": collected,
                "can_fix": False,
                "fixed": False,
                "repair_suggestion": f"No fixer for category: {collected.category.value}",
                "circuit_open": False,
            }

        # 4. Record attempt
        self._circuit.record_attempt(error_key)

        # 5. Attempt repair
        try:
            suggestion = fixer(collected, code=code)
            return {
                "collected": collected,
                "can_fix": True,
                "fixed": False,
                "repair_suggestion": suggestion,
                "circuit_open": False,
            }
        except Exception as fix_error:
            logger.warning(f"Fix attempt failed: {fix_error}")
            return {
                "collected": collected,
                "can_fix": True,
                "fixed": False,
                "repair_suggestion": f"Fix failed: {fix_error}",
                "circuit_open": False,
            }

    def _fix_import_error(
        self, error: CollectedError, code: str | None = None
    ) -> str:
        """Suggest fix for import errors."""
        message = error.message.lower()

        # Extract module name
        match = re.search(r"no module named ['\"]?(\w+)", message)
        if match:
            module = match.group(1)
            return f"Install missing package: pip install {module}"

        return "Check import statements and ensure required packages are installed"

    def _fix_syntax_error(
        self, error: CollectedError, code: str | None = None
    ) -> str:
        """Suggest fix for syntax errors."""
        if code:
            try:
                ast.parse(code)
                return "Code is syntactically valid (error may be in runtime)"
            except SyntaxError as e:
                return f"Syntax error at line {e.lineno}: {e.msg}"

        return "Review code for syntax errors"

    def _fix_timeout_error(
        self, error: CollectedError, code: str | None = None
    ) -> str:
        """Suggest fix for timeout errors."""
        return (
            "Timeout detected. Suggestions:\n"
            "1. Increase timeout duration\n"
            "2. Optimize code for better performance\n"
            "3. Use smaller input data\n"
            "4. Add progress indicators"
        )

    def get_collector(self) -> ErrorCollector:
        """Get the error collector."""
        return self._collector

    def get_error_summary(self) -> dict[str, Any]:
        """Get summary of all collected errors."""
        errors = self._collector.get_errors()
        summary: dict[str, Any] = {
            "total": len(errors),
            "by_category": {},
            "by_severity": {},
            "by_stage": {},
            "fixed_count": sum(1 for e in errors if e.fixed),
        }

        for error in errors:
            cat = error.category.value
            sev = error.severity.value
            stage = error.stage

            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
            summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
            summary["by_stage"][stage] = summary["by_stage"].get(stage, 0) + 1

        return summary
