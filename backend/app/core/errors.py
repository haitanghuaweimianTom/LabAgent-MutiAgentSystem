"""Structured error taxonomy for the multi-agent system.

Provides domain-specific error classes with error codes, HTTP status codes,
and factory classmethods for common failure scenarios.

Usage:
    raise LLMError.timeout(model="gpt-4", timeout_sec=30)
    raise SandboxError.exec_failed(task_id="t1", reason="segfault")
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """Machine-readable error codes for programmatic handling."""

    # LLM errors
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_AUTH_FAILED = "LLM_AUTH_FAILED"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"

    # MCP errors
    MCP_CONNECTION_FAILED = "MCP_CONNECTION_FAILED"
    MCP_TOOL_ERROR = "MCP_TOOL_ERROR"
    MCP_TIMEOUT = "MCP_TIMEOUT"

    # Sandbox errors
    SANDBOX_TIMEOUT = "SANDBOX_TIMEOUT"
    SANDBOX_EXEC_FAILED = "SANDBOX_EXEC_FAILED"
    SANDBOX_RESOURCE_EXCEEDED = "SANDBOX_RESOURCE_EXCEEDED"

    # Task errors
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_DEPENDENCY_FAILED = "TASK_DEPENDENCY_FAILED"

    # Provider errors
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_QUOTA_EXCEEDED = "PROVIDER_QUOTA_EXCEEDED"

    # Network errors
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    NETWORK_DNS_FAILED = "NETWORK_DNS_FAILED"
    NETWORK_CONNECTION_REFUSED = "NETWORK_CONNECTION_REFUSED"

    # Validation errors
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_TYPE_ERROR = "VALIDATION_TYPE_ERROR"

    # Config errors
    CONFIG_MISSING = "CONFIG_MISSING"
    CONFIG_INVALID = "CONFIG_INVALID"

    # Resource errors
    RESOURCE_EXCEEDED = "RESOURCE_EXCEEDED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"

    # Catch-all
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for all application errors.

    Attributes:
        code: Machine-readable error code.
        message: Human-readable error description.
        status_code: HTTP status code for API responses.
        detail: Optional structured error details.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int,
        detail: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize error for JSON API responses."""
        result: Dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "status_code": self.status_code,
        }
        if self.detail is not None:
            result["detail"] = self.detail
        return result

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"code={self.code.value!r}, "
            f"message={self.message!r}, "
            f"status_code={self.status_code})"
        )


# ==================== Domain Subclasses ====================


class LLMError(AppError):
    """LLM call failures: timeouts, rate limits, auth, malformed responses."""

    @classmethod
    def timeout(cls, model: str, timeout_sec: int) -> LLMError:
        return cls(
            code=ErrorCode.LLM_TIMEOUT,
            message=f"LLM call to {model} timed out after {timeout_sec}s",
            status_code=504,
        )

    @classmethod
    def rate_limited(cls, model: str) -> LLMError:
        return cls(
            code=ErrorCode.LLM_RATE_LIMITED,
            message=f"LLM rate limited: {model}",
            status_code=429,
        )

    @classmethod
    def auth_failed(cls, model: str) -> LLMError:
        return cls(
            code=ErrorCode.LLM_AUTH_FAILED,
            message=f"LLM authentication failed for {model}",
            status_code=401,
        )

    @classmethod
    def invalid_response(cls, model: str, reason: str) -> LLMError:
        return cls(
            code=ErrorCode.LLM_INVALID_RESPONSE,
            message=f"LLM returned invalid response from {model}: {reason}",
            status_code=502,
        )


class MCPError(AppError):
    """MCP server connection and tool invocation failures."""

    @classmethod
    def connection_failed(cls, server: str) -> MCPError:
        return cls(
            code=ErrorCode.MCP_CONNECTION_FAILED,
            message=f"MCP connection failed: {server}",
            status_code=502,
        )

    @classmethod
    def tool_error(cls, tool: str, reason: str) -> MCPError:
        return cls(
            code=ErrorCode.MCP_TOOL_ERROR,
            message=f"MCP tool '{tool}' failed: {reason}",
            status_code=500,
        )

    @classmethod
    def timeout(cls, server: str, timeout_sec: int) -> MCPError:
        return cls(
            code=ErrorCode.MCP_TIMEOUT,
            message=f"MCP server '{server}' timed out after {timeout_sec}s",
            status_code=504,
        )


class SandboxError(AppError):
    """Code sandbox execution failures."""

    @classmethod
    def timeout(cls, task_id: str, timeout_sec: int) -> SandboxError:
        return cls(
            code=ErrorCode.SANDBOX_TIMEOUT,
            message=f"Sandbox timed out for task {task_id} after {timeout_sec}s",
            status_code=504,
        )

    @classmethod
    def exec_failed(cls, task_id: str, reason: str) -> SandboxError:
        return cls(
            code=ErrorCode.SANDBOX_EXEC_FAILED,
            message=f"Sandbox execution failed for task {task_id}: {reason}",
            status_code=500,
        )

    @classmethod
    def resource_exceeded(cls, task_id: str, resource: str) -> SandboxError:
        return cls(
            code=ErrorCode.SANDBOX_RESOURCE_EXCEEDED,
            message=f"Sandbox resource '{resource}' exceeded for task {task_id}",
            status_code=413,
        )


class TaskError(AppError):
    """Task lifecycle failures."""

    @classmethod
    def failed(cls, task_id: str, reason: str) -> TaskError:
        return cls(
            code=ErrorCode.TASK_FAILED,
            message=f"Task {task_id} failed: {reason}",
            status_code=500,
        )

    @classmethod
    def cancelled(cls, task_id: str) -> TaskError:
        return cls(
            code=ErrorCode.TASK_CANCELLED,
            message=f"Task {task_id} was cancelled",
            status_code=499,
        )

    @classmethod
    def dependency_failed(cls, task_id: str, dep_id: str) -> TaskError:
        return cls(
            code=ErrorCode.TASK_DEPENDENCY_FAILED,
            message=f"Task {task_id} failed: dependency {dep_id} failed",
            status_code=500,
        )


class ProviderError(AppError):
    """LLM provider availability and quota failures."""

    @classmethod
    def unavailable(cls, provider: str) -> ProviderError:
        return cls(
            code=ErrorCode.PROVIDER_UNAVAILABLE,
            message=f"Provider '{provider}' is unavailable",
            status_code=503,
        )

    @classmethod
    def quota_exceeded(cls, provider: str) -> ProviderError:
        return cls(
            code=ErrorCode.PROVIDER_QUOTA_EXCEEDED,
            message=f"Provider '{provider}' quota exceeded",
            status_code=429,
        )


class NetworkError(AppError):
    """Network-level failures."""

    @classmethod
    def timeout(cls, url: str) -> NetworkError:
        return cls(
            code=ErrorCode.NETWORK_TIMEOUT,
            message=f"Network timeout connecting to {url}",
            status_code=504,
        )

    @classmethod
    def dns_failed(cls, host: str) -> NetworkError:
        return cls(
            code=ErrorCode.NETWORK_DNS_FAILED,
            message=f"DNS resolution failed for {host}",
            status_code=502,
        )

    @classmethod
    def connection_refused(cls, host: str, port: int) -> NetworkError:
        return cls(
            code=ErrorCode.NETWORK_CONNECTION_REFUSED,
            message=f"Connection refused: {host}:{port}",
            status_code=502,
        )


class ValidationError(AppError):
    """Input validation failures."""

    @classmethod
    def failed(cls, field: str, reason: str) -> ValidationError:
        return cls(
            code=ErrorCode.VALIDATION_FAILED,
            message=f"Validation failed for '{field}': {reason}",
            status_code=422,
        )

    @classmethod
    def type_error(cls, field: str, expected: str, got: str) -> ValidationError:
        return cls(
            code=ErrorCode.VALIDATION_TYPE_ERROR,
            message=f"Type error for '{field}': expected {expected}, got {got}",
            status_code=422,
        )


class ConfigError(AppError):
    """Configuration errors."""

    @classmethod
    def missing(cls, key: str) -> ConfigError:
        return cls(
            code=ErrorCode.CONFIG_MISSING,
            message=f"Missing required configuration: {key}",
            status_code=500,
        )

    @classmethod
    def invalid(cls, key: str, reason: str) -> ConfigError:
        return cls(
            code=ErrorCode.CONFIG_INVALID,
            message=f"Invalid configuration for '{key}': {reason}",
            status_code=500,
        )


class ResourceError(AppError):
    """Resource limit and not-found errors."""

    @classmethod
    def exceeded(cls, resource: str, limit: str) -> ResourceError:
        return cls(
            code=ErrorCode.RESOURCE_EXCEEDED,
            message=f"Resource '{resource}' exceeded limit: {limit}",
            status_code=507,
        )

    @classmethod
    def not_found(cls, resource: str, name: str) -> ResourceError:
        return cls(
            code=ErrorCode.RESOURCE_NOT_FOUND,
            message=f"{resource} not found: {name}",
            status_code=404,
        )
