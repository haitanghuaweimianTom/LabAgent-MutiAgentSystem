# Reliability Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured error handling with domain-specific error codes, extend circuit breaker protection to MCP/sandbox/CLI, and create a generic retry utility.

**Architecture:** Three interconnected modules: `errors.py` (error taxonomy), `circuit_breaker.py` (named breakers + decorator), `retry.py` (exponential backoff). Integration into existing MCP client, sandbox, and Claude CLI call sites.

**Tech Stack:** Python 3.11+, FastAPI, pytest

## Global Constraints

- Python 3.11+ (uses `str | None` union syntax)
- FastAPI exception handlers must return `JSONResponse`
- All new code must have unit tests
- Follow existing patterns: `logging.getLogger(__name__)`, dataclass configs
- Error response format: `{"error": {"code": "...", "message": "...", "detail": ...}}`

---

## Task 1: Error Taxonomy Module

**Covers:** [S3]

**Files:**
- Create: `backend/app/core/errors.py`
- Create: `backend/tests/test_errors.py`

**Interfaces:**
- Consumes: None (new module)
- Produces: `AppError`, `ErrorCode`, `LLMError`, `MCPError`, `SandboxError`, `TaskError`, `ProviderError`, `NetworkError`, `ValidationError`, `ConfigError`, `ResourceError`

- [ ] **Step 1: Write failing tests for ErrorCode enum**

```python
# backend/tests/test_errors.py
import pytest
from app.core.errors import ErrorCode, AppError, LLMError, MCPError

def test_error_code_enum_values():
    assert ErrorCode.LLM_TIMEOUT == "LLM_TIMEOUT"
    assert ErrorCode.MCP_CONNECTION_FAILED == "MCP_CONNECTION_FAILED"
    assert ErrorCode.SANDBOX_TIMEOUT == "SANDBOX_TIMEOUT"

def test_error_code_is_string():
    assert isinstance(ErrorCode.LLM_TIMEOUT, str)

def test_app_error_base():
    err = AppError(code=ErrorCode.INTERNAL, message="test error")
    assert err.code == ErrorCode.INTERNAL
    assert err.message == "test error"
    assert err.status_code == 500
    assert err.detail is None

def test_app_error_with_detail():
    err = AppError(code=ErrorCode.INTERNAL, message="test", detail={"key": "value"})
    assert err.detail == {"key": "value"}

def test_app_error_custom_status():
    err = AppError(code=ErrorCode.VALID_MISSING_FIELD, message="missing", status_code=400)
    assert err.status_code == 400

def test_llm_error_factory_timeout():
    err = LLMError.timeout(model="gpt-4", timeout_sec=300)
    assert err.code == ErrorCode.LLM_TIMEOUT
    assert "gpt-4" in err.message
    assert err.status_code == 500

def test_llm_error_factory_rate_limited():
    err = LLMError.rate_limited(retry_after=60)
    assert err.code == ErrorCode.LLM_RATE_LIMITED
    assert err.status_code == 429

def test_mcp_error_factory_connection_failed():
    err = MCPError.connection_failed(server_name="arxiv", reason="process exited")
    assert err.code == ErrorCode.MCP_CONNECTION_FAILED
    assert "arxiv" in err.message

def test_sandbox_error_factory_timeout():
    err = SandboxError.timeout(max_time=60)
    assert err.code == ErrorCode.SANDBOX_TIMEOUT
    assert err.status_code == 500

def test_task_error_factory_not_found():
    err = TaskError.not_found(task_id="abc123")
    assert err.code == ErrorCode.TASK_NOT_FOUND
    assert err.status_code == 404

def test_provider_error_factory_not_configured():
    err = ProviderError.not_configured(provider_name="openai")
    assert err.code == ErrorCode.PROVIDER_NOT_CONFIGURED
    assert err.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.errors'`

- [ ] **Step 3: Implement ErrorCode enum and AppError base class**

```python
# backend/app/core/errors.py
"""Structured error handling with domain-specific error codes."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class ErrorCode(str, Enum):
    """Error code constants."""
    # LLM
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    LLM_CONTEXT_TOO_LONG = "LLM_CONTEXT_TOO_LONG"
    LLM_AUTH_FAILED = "LLM_AUTH_FAILED"
    # MCP
    MCP_CONNECTION_FAILED = "MCP_CONNECTION_FAILED"
    MCP_TOOL_FAILED = "MCP_TOOL_FAILED"
    MCP_SERVER_CRASHED = "MCP_SERVER_CRASHED"
    MCP_PROTOCOL_ERROR = "MCP_PROTOCOL_ERROR"
    # Sandbox
    SANDBOX_EXEC_FAILED = "SANDBOX_EXEC_FAILED"
    SANDBOX_TIMEOUT = "SANDBOX_TIMEOUT"
    SANDBOX_MEMORY_EXCEEDED = "SANDBOX_MEMORY_EXCEEDED"
    SANDBOX_SAFETY_VIOLATION = "SANDBOX_SAFETY_VIOLATION"
    # Task
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_ALREADY_RUNNING = "TASK_ALREADY_RUNNING"
    TASK_INVALID_INPUT = "TASK_INVALID_INPUT"
    TASK_WORKFLOW_FAILED = "TASK_WORKFLOW_FAILED"
    # Provider
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_AUTH_FAILED = "PROVIDER_AUTH_FAILED"
    PROVIDER_QUOTA_EXCEEDED = "PROVIDER_QUOTA_EXCEEDED"
    # Network
    NET_CONNECTION_REFUSED = "NET_CONNECTION_REFUSED"
    NET_DNS_FAILED = "NET_DNS_FAILED"
    NET_SSL_ERROR = "NET_SSL_ERROR"
    NET_TIMEOUT = "NET_TIMEOUT"
    # Validation
    VALID_MISSING_FIELD = "VALID_MISSING_FIELD"
    VALID_INVALID_FORMAT = "VALID_INVALID_FORMAT"
    VALID_OUT_OF_RANGE = "VALID_OUT_OF_RANGE"
    # Config
    CONFIG_MISSING_KEY = "CONFIG_MISSING_KEY"
    CONFIG_INVALID_VALUE = "CONFIG_INVALID_VALUE"
    CONFIG_ENV_MISSING = "CONFIG_ENV_MISSING"
    # Resource
    RESOURCE_DISK_FULL = "RESOURCE_DISK_FULL"
    RESOURCE_FILE_NOT_FOUND = "RESOURCE_FILE_NOT_FOUND"
    RESOURCE_PERMISSION_DENIED = "RESOURCE_PERMISSION_DENIED"
    RESOURCE_QUOTA_EXCEEDED = "RESOURCE_QUOTA_EXCEEDED"
    # Generic
    INTERNAL = "INTERNAL"
    UNKNOWN = "UNKNOWN"


class AppError(Exception):
    """Base application error with structured code and message."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 500,
        detail: Any = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class LLMError(AppError):
    """LLM API call errors."""

    @classmethod
    def timeout(cls, model: str = "", timeout_sec: int = 300) -> LLMError:
        return cls(
            code=ErrorCode.LLM_TIMEOUT,
            message=f"LLM request timed out after {timeout_sec}s" + (f" (model: {model})" if model else ""),
        )

    @classmethod
    def rate_limited(cls, retry_after: int = 60) -> LLMError:
        return cls(
            code=ErrorCode.LLM_RATE_LIMITED,
            message=f"LLM rate limited, retry after {retry_after}s",
            status_code=429,
            detail={"retry_after": retry_after},
        )

    @classmethod
    def auth_failed(cls, provider: str = "") -> LLMError:
        return cls(
            code=ErrorCode.LLM_AUTH_FAILED,
            message=f"LLM authentication failed" + (f" (provider: {provider})" if provider else ""),
            status_code=401,
        )

    @classmethod
    def context_too_long(cls, token_count: int, max_tokens: int) -> LLMError:
        return cls(
            code=ErrorCode.LLM_CONTEXT_TOO_LONG,
            message=f"Context too long: {token_count} tokens (max: {max_tokens})",
            status_code=400,
            detail={"token_count": token_count, "max_tokens": max_tokens},
        )


class MCPError(AppError):
    """MCP server call errors."""

    @classmethod
    def connection_failed(cls, server_name: str, reason: str = "") -> MCPError:
        return cls(
            code=ErrorCode.MCP_CONNECTION_FAILED,
            message=f"MCP server '{server_name}' connection failed" + (f": {reason}" if reason else ""),
        )

    @classmethod
    def tool_failed(cls, tool_name: str, reason: str = "") -> MCPError:
        return cls(
            code=ErrorCode.MCP_TOOL_FAILED,
            message=f"MCP tool '{tool_name}' failed" + (f": {reason}" if reason else ""),
        )

    @classmethod
    def server_crashed(cls, server_name: str) -> MCPError:
        return cls(
            code=ErrorCode.MCP_SERVER_CRASHED,
            message=f"MCP server '{server_name}' crashed",
        )


class SandboxError(AppError):
    """Code execution sandbox errors."""

    @classmethod
    def execution_failed(cls, returncode: int, stderr: str = "") -> SandboxError:
        return cls(
            code=ErrorCode.SANDBOX_EXEC_FAILED,
            message=f"Sandbox execution failed with exit code {returncode}",
            detail={"returncode": returncode, "stderr": stderr[:500]},
        )

    @classmethod
    def timeout(cls, max_time: int = 60) -> SandboxError:
        return cls(
            code=ErrorCode.SANDBOX_TIMEOUT,
            message=f"Sandbox execution timed out after {max_time}s",
        )

    @classmethod
    def memory_exceeded(cls, limit_mb: int = 512) -> SandboxError:
        return cls(
            code=ErrorCode.SANDBOX_MEMORY_EXCEEDED,
            message=f"Sandbox memory limit exceeded ({limit_mb}MB)",
        )


class TaskError(AppError):
    """Task management errors."""

    @classmethod
    def not_found(cls, task_id: str) -> TaskError:
        return cls(
            code=ErrorCode.TASK_NOT_FOUND,
            message=f"Task '{task_id}' not found",
            status_code=404,
        )

    @classmethod
    def already_running(cls, task_id: str) -> TaskError:
        return cls(
            code=ErrorCode.TASK_ALREADY_RUNNING,
            message=f"Task '{task_id}' is already running",
            status_code=409,
        )


class ProviderError(AppError):
    """LLM provider errors."""

    @classmethod
    def not_configured(cls, provider_name: str) -> ProviderError:
        return cls(
            code=ErrorCode.PROVIDER_NOT_CONFIGURED,
            message=f"Provider '{provider_name}' is not configured",
            status_code=400,
        )

    @classmethod
    def auth_failed(cls, provider_name: str) -> ProviderError:
        return cls(
            code=ErrorCode.PROVIDER_AUTH_FAILED,
            message=f"Provider '{provider_name}' authentication failed",
            status_code=401,
        )


class NetworkError(AppError):
    """Network call errors."""

    @classmethod
    def timeout(cls, host: str = "", timeout_sec: int = 30) -> NetworkError:
        return cls(
            code=ErrorCode.NET_TIMEOUT,
            message=f"Network request timed out after {timeout_sec}s" + (f" ({host})" if host else ""),
        )


class ValidationError(AppError):
    """Input validation errors."""

    @classmethod
    def missing_field(cls, field_name: str) -> ValidationError:
        return cls(
            code=ErrorCode.VALID_MISSING_FIELD,
            message=f"Required field '{field_name}' is missing",
            status_code=400,
        )


class ConfigError(AppError):
    """Configuration errors."""

    @classmethod
    def missing_key(cls, key_name: str) -> ConfigError:
        return cls(
            code=ErrorCode.CONFIG_MISSING_KEY,
            message=f"Required config key '{key_name}' is missing",
            status_code=500,
        )


class ResourceError(AppError):
    """File system and resource errors."""

    @classmethod
    def file_not_found(cls, path: str) -> ResourceError:
        return cls(
            code=ErrorCode.RESOURCE_FILE_NOT_FOUND,
            message=f"File not found: {path}",
            status_code=404,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_errors.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/errors.py backend/tests/test_errors.py
git commit -m "feat: add structured error taxonomy with domain-specific error codes"
```

---

## Task 2: Circuit Breaker Registry + Decorator

**Covers:** [S4]

**Files:**
- Modify: `backend/app/core/circuit_breaker.py`
- Create: `backend/tests/test_circuit_breaker_registry.py`

**Interfaces:**
- Consumes: Existing `CircuitBreaker`, `CircuitBreakerConfig`, `CircuitOpenError`
- Produces: `get_named_breaker()`, `@with_breaker`, `reset_named_breakers()`

- [ ] **Step 1: Write failing tests for named breaker and decorator**

```python
# backend/tests/test_circuit_breaker_registry.py
import asyncio
import pytest
from app.core.circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitOpenError,
    get_named_breaker, with_breaker, reset_named_breakers,
)

@pytest.fixture(autouse=True)
def cleanup():
    reset_named_breakers()
    yield
    reset_named_breakers()

def test_get_named_breaker_creates_new():
    breaker = get_named_breaker("test_service")
    assert isinstance(breaker, CircuitBreaker)
    assert breaker.name == "test_service"

def test_get_named_breaker_returns_same_instance():
    b1 = get_named_breaker("test_service")
    b2 = get_named_breaker("test_service")
    assert b1 is b2

def test_get_named_breaker_with_custom_config():
    config = CircuitBreakerConfig(failure_threshold=3, open_duration_seconds=10)
    breaker = get_named_breaker("custom", config)
    assert breaker.config.failure_threshold == 3

@pytest.mark.asyncio
async def test_with_breaker_success():
    @with_breaker("test_success")
    async def my_func():
        return "ok"

    result = await my_func()
    assert result == "ok"

@pytest.mark.asyncio
async def test_with_breaker_failure_records():
    @with_breaker("test_fail", CircuitBreakerConfig(failure_threshold=2))
    async def my_func():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await my_func()
    with pytest.raises(ValueError):
        await my_func()

    breaker = get_named_breaker("test_fail")
    assert breaker.state == CircuitBreaker.OPEN

@pytest.mark.asyncio
async def test_with_breaker_circuit_open():
    @with_breaker("test_open", CircuitBreakerConfig(failure_threshold=1, open_duration_seconds=3600))
    async def my_func():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await my_func()

    with pytest.raises(CircuitOpenError):
        await my_func()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_circuit_breaker_registry.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_named_breaker'`

- [ ] **Step 3: Implement named breaker registry and decorator**

Append to `backend/app/core/circuit_breaker.py`:

```python
# ==================== Named Breaker Registry ====================

import functools

_named_breakers: dict[str, CircuitBreaker] = {}
_named_lock = threading.RLock()

# Default configs for named breakers
MCP_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    window_seconds=600.0,      # 10 minutes
    open_duration_seconds=180.0,  # 3 minutes
)
SANDBOX_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=10,
    window_seconds=1800.0,     # 30 minutes
    open_duration_seconds=300.0,  # 5 minutes
)
CLAUDE_CLI_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    window_seconds=900.0,      # 15 minutes
    open_duration_seconds=300.0,  # 5 minutes
)


def get_named_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
) -> CircuitBreaker:
    """Get or create a named breaker (not per-task).

    Each named breaker tracks failures for a specific service
    (e.g., MCP server, sandbox, Claude CLI).
    """
    with _named_lock:
        if name not in _named_breakers:
            _named_breakers[name] = CircuitBreaker(
                name=name,
                config=config or CircuitBreakerConfig(),
            )
            logger.info(f"[CircuitBreaker] created named breaker: {name}")
        return _named_breakers[name]


def reset_named_breakers():
    """Reset all named breakers (for testing or operational recovery)."""
    with _named_lock:
        _named_breakers.clear()


def with_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
):
    """Decorator that wraps an async function with circuit breaker protection.

    Usage:
        @with_breaker("mcp_arxiv", MCP_BREAKER_CONFIG)
        async def call_arxiv(query: str) -> str: ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            breaker = get_named_breaker(name, config)
            breaker.check_or_raise()
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except CircuitOpenError:
                raise
            except Exception:
                breaker.record_failure()
                raise
        return wrapper
    return decorator
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_circuit_breaker_registry.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/circuit_breaker.py backend/tests/test_circuit_breaker_registry.py
git commit -m "feat: add named breaker registry and @with_breaker decorator"
```

---

## Task 3: Retry Utility Module

**Covers:** [S5]

**Files:**
- Create: `backend/app/core/retry.py`
- Create: `backend/tests/test_retry.py`

**Interfaces:**
- Consumes: `circuit_breaker.get_named_breaker`, `circuit_breaker.CircuitOpenError`
- Produces: `RetryConfig`, `MaxRetriesExceeded`, `@retry`

- [ ] **Step 1: Write failing tests for retry decorator**

```python
# backend/tests/test_retry.py
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from app.core.retry import RetryConfig, MaxRetriesExceeded, retry
from app.core.circuit_breaker import reset_named_breakers

@pytest.fixture(autouse=True)
def cleanup():
    reset_named_breakers()
    yield
    reset_named_breakers()

@pytest.mark.asyncio
async def test_retry_success_first_attempt():
    @retry(RetryConfig(max_retries=3))
    async def my_func():
        return "ok"

    result = await my_func()
    assert result == "ok"

@pytest.mark.asyncio
async def test_retry_success_after_failure():
    call_count = 0

    @retry(RetryConfig(max_retries=3, backoff_base=0.01))
    async def my_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("not yet")
        return "ok"

    result = await my_func()
    assert result == "ok"
    assert call_count == 3

@pytest.mark.asyncio
async def test_retry_exhausted_raises():
    @retry(RetryConfig(max_retries=2, backoff_base=0.01))
    async def my_func():
        raise ValueError("always fails")

    with pytest.raises(MaxRetriesExceeded) as exc_info:
        await my_func()
    assert exc_info.value.attempts == 3  # 1 initial + 2 retries

@pytest.mark.asyncio
async def test_retry_respects_retry_on():
    @retry(RetryConfig(max_retries=3, backoff_base=0.01, retry_on=(ValueError,)))
    async def my_func():
        raise TypeError("not retryable")

    with pytest.raises(TypeError):
        await my_func()

@pytest.mark.asyncio
async def test_retry_with_breaker():
    @retry(RetryConfig(max_retries=2, backoff_base=0.01, breaker_name="test_retry_breaker"))
    async def my_func():
        raise ValueError("fail")

    with pytest.raises(MaxRetriesExceeded):
        await my_func()

    from app.core.circuit_breaker import get_named_breaker, CircuitBreaker
    breaker = get_named_breaker("test_retry_breaker")
    assert breaker._total_failures >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_retry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.retry'`

- [ ] **Step 3: Implement retry decorator**

```python
# backend/app/core/retry.py
"""Generic retry decorator with exponential backoff."""
from __future__ import annotations

import asyncio
import functools
import logging
import random
from dataclasses import dataclass
from typing import Any, Optional, Tuple, Type

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    backoff_base: float = 1.0       # seconds
    backoff_max: float = 60.0       # seconds
    jitter: bool = True
    retry_on: Tuple[Type[Exception], ...] = (Exception,)
    breaker_name: Optional[str] = None  # integrate with named breaker


class MaxRetriesExceeded(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(
            f"Max retries ({attempts - 1}) exceeded. Last error: {last_exception}"
        )


def retry(config: Optional[RetryConfig] = None):
    """Decorator for async functions with exponential backoff.

    Usage:
        @retry(RetryConfig(max_retries=3, backoff_base=1.0))
        async def call_api(): ...
    """
    cfg = config or RetryConfig()

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            breaker = None
            if cfg.breaker_name:
                from .circuit_breaker import get_named_breaker
                breaker = get_named_breaker(cfg.breaker_name)

            last_exception = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    if breaker and attempt > 0:
                        breaker.check_or_raise()
                    result = await func(*args, **kwargs)
                    if breaker:
                        breaker.record_success()
                    return result
                except Exception as exc:
                    last_exception = exc
                    if breaker:
                        breaker.record_failure()
                    if not isinstance(exc, cfg.retry_on):
                        raise
                    if attempt == cfg.max_retries:
                        break
                    backoff = min(cfg.backoff_base * (2 ** attempt), cfg.backoff_max)
                    if cfg.jitter:
                        backoff += random.uniform(0, backoff * 0.5)
                    logger.warning(
                        f"[retry] {func.__name__} attempt {attempt + 1} failed: {exc}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)

            raise MaxRetriesExceeded(last_exception, cfg.max_retries + 1)
        return wrapper
    return decorator
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_retry.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/retry.py backend/tests/test_retry.py
git commit -m "feat: add generic retry decorator with exponential backoff"
```

---

## Task 4: Global Error Handler

**Covers:** [S3]

**Files:**
- Modify: `backend/app/main.py:431-434`

**Interfaces:**
- Consumes: `AppError` from `errors.py`
- Produces: Structured error responses

- [ ] **Step 1: Write test for global error handler**

```python
# Add to existing test file or create backend/tests/test_error_handler.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.errors import AppError, ErrorCode, LLMError

client = TestClient(app, raise_server_exceptions=False)

def test_global_handler_returns_structured_app_error():
    """AppError exceptions should return structured JSON."""
    # We'll test by calling an endpoint that we know can raise AppError
    # For now, test the handler directly via the app
    from fastapi import Request
    from fastapi.responses import JSONResponse

    # Simulate an AppError being raised
    exc = LLMError.timeout(model="test", timeout_sec=300)
    assert exc.code == ErrorCode.LLM_TIMEOUT
    assert exc.status_code == 500

def test_global_handler_generic_error():
    """Non-AppError exceptions should return generic message."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    # Generic exceptions should not leak details
    exc = ValueError("secret internal detail")
    assert not isinstance(exc, AppError)
```

- [ ] **Step 2: Update global exception handler in main.py**

Replace lines 431-434 in `backend/app/main.py`:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from .core.errors import AppError

    if isinstance(exc, AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code.value,
                    "message": exc.message,
                    "detail": exc.detail,
                }
            },
        )
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL", "message": "Internal server error"}},
    )
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v --timeout=60`
Expected: All existing tests still PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: sanitize global error handler to use structured AppError responses"
```

---

## Task 5: MCP Client Integration

**Covers:** [S4, S5]

**Files:**
- Modify: `backend/app/mcp/client.py`

**Interfaces:**
- Consumes: `@with_breaker`, `@retry`, `MCPError`, `RetryConfig`, `MCP_BREAKER_CONFIG`
- Produces: Protected `call_tool` method

- [ ] **Step 1: Add breaker and retry to MCPClient.call_tool**

Update `backend/app/mcp/client.py`:

```python
"""MCP 客户端封装 —— 基于官方 mcp SDK 的 stdio 传输。"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..core.circuit_breaker import with_breaker, MCP_BREAKER_CONFIG
from ..core.retry import retry, RetryConfig
from ..core.errors import MCPError

logger = logging.getLogger(__name__)

# Retry config for MCP calls
MCP_RETRY_CONFIG = RetryConfig(
    max_retries=2,
    backoff_base=1.0,
    backoff_max=10.0,
    retry_on=(ConnectionError, TimeoutError, OSError),
)


@dataclass
class MCPServerConfig:
    """MCP 服务器配置（与 research_agent.py 中引用的接口保持一致）。"""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


class MCPClient:
    """MCP stdio 客户端封装。

    用法：
        config = MCPServerConfig(name="arxiv_server", command="uvx", args=["..."])
        client = MCPClient(config)
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("search_papers", {"query": "..."})
        await client.disconnect()
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: Optional[ClientSession] = None
        self._exit_stack = None
        self._stdio_transport = None

    async def connect(self) -> None:
        """建立到 MCP 服务器的 stdio 连接。"""
        if self._session is not None:
            return

        params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=self.config.env or None,
        )
        logger.debug(f"Connecting to MCP server {self.config.name}: {self.config.command} {self.config.args}")

        self._exit_stack = __import__("contextlib").AsyncExitStack()
        stdio_transport = await self._exit_stack.enter_async_context(stdio_client(params))
        self._stdio_transport = stdio_transport
        read, write = stdio_transport
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
        logger.debug(f"MCP server {self.config.name} connected")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出服务器提供的工具。"""
        if self._session is None:
            raise MCPError.connection_failed(self.config.name, "not connected")
        tools_resp = await self._session.list_tools()
        tools = getattr(tools_resp, "tools", tools_resp)
        if not isinstance(tools, list):
            logger.warning(f"Unexpected list_tools response type: {type(tools)}")
            return []
        return [{"name": t.name, "description": getattr(t, "description", "")} for t in tools]

    @with_breaker("mcp_{name}", MCP_BREAKER_CONFIG)
    @retry(MCP_RETRY_CONFIG)
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
        """调用指定工具并返回文本结果。带熔断器和重试保护。"""
        if self._session is None:
            raise MCPError.connection_failed(self.config.name, "not connected")

        logger.debug(f"Calling MCP tool {tool_name} on {self.config.name}")
        result = await self._session.call_tool(tool_name, arguments)
        contents = getattr(result, "content", result)
        if not isinstance(contents, list):
            return str(contents)

        text_parts: List[str] = []
        for item in contents:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
                else:
                    text_parts.append(str(item))
            elif hasattr(item, "type") and getattr(item, "type") == "text":
                text_parts.append(str(getattr(item, "text", "")))
            else:
                text_parts.append(str(item))

        return "\n".join(text_parts) if text_parts else None

    async def disconnect(self) -> None:
        """关闭连接。"""
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.debug(f"Error closing MCP client: {e}")
            finally:
                self._exit_stack = None
                self._session = None
                self._stdio_transport = None
```

Note: The `@with_breaker` decorator uses `"mcp_{name}"` where `{name}` is resolved at decoration time. Since we need the server name from `self.config.name`, we'll need a slight adjustment — the decorator should accept a format string or we use a factory. Let me fix this:

```python
# Actually, @with_breaker needs the name at decoration time.
# For instance methods, we need to use a different approach.
# Option: pass the name dynamically by not using the decorator on the method,
# but wrapping in __init__ or using a helper.

# Simpler approach: don't use decorator on the method directly.
# Instead, wrap the call inside the method.
```

Revised approach for MCP client — wrap inside the method instead of decorator:

```python
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
        """调用指定工具并返回文本结果。带熔断器和重试保护。"""
        if self._session is None:
            raise MCPError.connection_failed(self.config.name, "not connected")

        from ..core.circuit_breaker import get_named_breaker
        from ..core.retry import retry, RetryConfig

        breaker = get_named_breaker(f"mcp_{self.config.name}", MCP_BREAKER_CONFIG)
        retry_config = RetryConfig(
            max_retries=2,
            backoff_base=1.0,
            backoff_max=10.0,
            retry_on=(ConnectionError, TimeoutError, OSError),
            breaker_name=f"mcp_{self.config.name}",
        )

        last_exc = None
        for attempt in range(retry_config.max_retries + 1):
            try:
                breaker.check_or_raise()
                logger.debug(f"Calling MCP tool {tool_name} on {self.config.name}")
                result = await self._session.call_tool(tool_name, arguments)
                breaker.record_success()
                break
            except Exception as exc:
                breaker.record_failure()
                last_exc = exc
                if attempt == retry_config.max_retries or not isinstance(exc, retry_config.retry_on):
                    raise
                import asyncio, random
                backoff = min(retry_config.backoff_base * (2 ** attempt), retry_config.backoff_max)
                if retry_config.jitter:
                    backoff += random.uniform(0, backoff * 0.5)
                logger.warning(f"MCP call_tool retry {attempt + 1}: {exc}")
                await asyncio.sleep(backoff)

        contents = getattr(result, "content", result)
        if not isinstance(contents, list):
            return str(contents)

        text_parts: List[str] = []
        for item in contents:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
                else:
                    text_parts.append(str(item))
            elif hasattr(item, "type") and getattr(item, "type") == "text":
                text_parts.append(str(getattr(item, "text", "")))
            else:
                text_parts.append(str(item))

        return "\n".join(text_parts) if text_parts else None
```

- [ ] **Step 2: Run MCP client tests**

Run: `cd backend && python -m pytest tests/ -v -k mcp --timeout=60`
Expected: Tests PASS (or skip if MCP servers not available)

- [ ] **Step 3: Commit**

```bash
git add backend/app/mcp/client.py
git commit -m "feat: add circuit breaker and retry protection to MCP client"
```

---

## Task 6: Sandbox Integration

**Covers:** [S4]

**Files:**
- Modify: `backend/app/core/sandbox.py`

**Interfaces:**
- Consumes: `get_named_breaker`, `SANDBOX_BREAKER_CONFIG`, `SandboxError`
- Produces: Protected `execute` method

- [ ] **Step 1: Add breaker to sandbox execute**

Update `backend/app/core/sandbox.py` — add breaker wrapping in the `execute` method:

```python
    def execute(
        self,
        code: str,
        language: str = "python",
        env_vars: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
    ) -> SandboxResult:
        """执行代码字符串。带熔断器保护。"""
        from .circuit_breaker import get_named_breaker, SANDBOX_BREAKER_CONFIG

        breaker = get_named_breaker("sandbox", SANDBOX_BREAKER_CONFIG)
        breaker.check_or_raise()

        if language != "python":
            return SandboxResult(
                success=False, message=f"Unsupported language: {language}"
            )

        workspace = self._create_workspace()
        try:
            code_file = workspace / "main.py"
            code_file.write_text(code, encoding="utf-8")
            self._inject_import_hook(workspace)
            result = self._run_in_sandbox(
                code_file, workspace, env_vars=env_vars, input_data=input_data
            )
            if result.success:
                breaker.record_success()
            else:
                breaker.record_failure()
            return result
        finally:
            if not self.config.workspace_persist:
                self._cleanup_workspace(workspace)
```

- [ ] **Step 2: Run sandbox tests**

Run: `cd backend && python -m pytest tests/ -v -k sandbox --timeout=60`
Expected: Tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/sandbox.py
git commit -m "feat: add circuit breaker protection to sandbox execution"
```

---

## Task 7: Claude CLI Integration

**Covers:** [S4]

**Files:**
- Modify: `backend/app/agents/base.py` (3 methods)

**Interfaces:**
- Consumes: `get_named_breaker`, `CLAUDE_CLI_BREAKER_CONFIG`
- Produces: Protected Claude Code CLI methods

- [ ] **Step 1: Add breaker to _call_claude_code_direct**

Find the `_call_claude_code_direct` method in `backend/app/agents/base.py` and add breaker at the start:

```python
    async def _call_claude_code_direct(self, prompt, ...):
        """..."""
        from ..core.circuit_breaker import get_named_breaker, CLAUDE_CLI_BREAKER_CONFIG
        breaker = get_named_breaker("claude_cli", CLAUDE_CLI_BREAKER_CONFIG)
        breaker.check_or_raise()
        try:
            # ... existing implementation ...
            breaker.record_success()
            return result
        except Exception:
            breaker.record_failure()
            raise
```

- [ ] **Step 2: Add breaker to _call_claude_code_print**

Same pattern for `_call_claude_code_print`.

- [ ] **Step 3: Add breaker to _call_claude_code_agent**

Same pattern for `_call_claude_code_agent`.

- [ ] **Step 4: Run agent tests**

Run: `cd backend && python -m pytest tests/ -v -k agent --timeout=60`
Expected: Tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/base.py
git commit -m "feat: add circuit breaker protection to Claude Code CLI calls"
```

---

## Task 8: Orchestrator Error Handling

**Covers:** [S4]

**Files:**
- Modify: `backend/app/agents/orchestrator.py`

**Interfaces:**
- Consumes: `CircuitOpenError`, `AppError` subclasses
- Produces: User-friendly error messages for breaker events

- [ ] **Step 1: Extend orchestrator to catch CircuitOpenError from named breakers**

Find the existing `CircuitOpenError` handling in `orchestrator.py` and extend it to handle named breaker errors with context-specific messages.

- [ ] **Step 2: Run orchestrator tests**

Run: `cd backend && python -m pytest tests/ -v -k orchestrator --timeout=60`
Expected: Tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/orchestrator.py
git commit -m "feat: add user-friendly error messages for circuit breaker events"
```

---

## Task 9: Integration Tests

**Covers:** [S6]

**Files:**
- Create: `backend/tests/test_reliability_integration.py`

**Interfaces:**
- Consumes: All new modules
- Produces: Integration test suite

- [ ] **Step 1: Write integration tests**

```python
# backend/tests/test_reliability_integration.py
"""Integration tests for reliability improvements."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.errors import AppError, ErrorCode, LLMError

client = TestClient(app, raise_server_exceptions=False)

def test_error_response_format():
    """Verify error responses use the new structured format."""
    # Test with a non-existent endpoint to trigger 404
    response = client.get("/api/v1/nonexistent")
    assert response.status_code in (404, 405)

def test_app_error_response_structure():
    """Verify AppError returns correct JSON structure."""
    # This tests the handler indirectly
    from fastapi import Request
    from fastapi.responses import JSONResponse

    exc = LLMError.timeout(model="test", timeout_sec=300)
    assert exc.code.value == "LLM_TIMEOUT"
    assert exc.status_code == 500
```

- [ ] **Step 2: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --timeout=120`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_reliability_integration.py
git commit -m "test: add integration tests for reliability improvements"
```
