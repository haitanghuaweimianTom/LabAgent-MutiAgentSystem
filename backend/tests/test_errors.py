"""Error Taxonomy 模块测试。

验证：
1. ErrorCode 枚举包含所有错误码
2. AppError 基类结构正确
3. 所有域子类行为正确
4. Factory classmethods 生成正确的错误实例
5. 异常链和 detail 传递
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.errors import (
    AppError,
    ErrorCode,
    ConfigError,
    LLMError,
    MCPError,
    NetworkError,
    ProviderError,
    ResourceError,
    SandboxError,
    TaskError,
    ValidationError,
)


# ==================== 1. ErrorCode 枚举 ====================

class TestErrorCode:
    def test_has_required_codes(self):
        required = [
            "LLM_TIMEOUT",
            "LLM_RATE_LIMITED",
            "LLM_AUTH_FAILED",
            "LLM_INVALID_RESPONSE",
            "MCP_CONNECTION_FAILED",
            "MCP_TOOL_ERROR",
            "MCP_TIMEOUT",
            "SANDBOX_TIMEOUT",
            "SANDBOX_EXEC_FAILED",
            "SANDBOX_RESOURCE_EXCEEDED",
            "TASK_FAILED",
            "TASK_CANCELLED",
            "TASK_DEPENDENCY_FAILED",
            "PROVIDER_UNAVAILABLE",
            "PROVIDER_QUOTA_EXCEEDED",
            "NETWORK_TIMEOUT",
            "NETWORK_DNS_FAILED",
            "NETWORK_CONNECTION_REFUSED",
            "VALIDATION_FAILED",
            "VALIDATION_TYPE_ERROR",
            "CONFIG_MISSING",
            "CONFIG_INVALID",
            "RESOURCE_EXCEEDED",
            "RESOURCE_NOT_FOUND",
            "INTERNAL_ERROR",
        ]
        for code_name in required:
            assert hasattr(ErrorCode, code_name), f"Missing ErrorCode.{code_name}"

    def test_code_values_are_strings(self):
        for member in ErrorCode:
            assert isinstance(member.value, str), f"{member.name} value is not str"

    def test_code_values_are_unique(self):
        values = [m.value for m in ErrorCode]
        assert len(values) == len(set(values)), "Duplicate ErrorCode values found"

    def test_code_members_count(self):
        assert len(ErrorCode) >= 25, "Expected at least 25 error codes"


# ==================== 2. AppError 基类 ====================

class TestAppError:
    def test_basic_construction(self):
        err = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="something broke",
            status_code=500,
        )
        assert err.code == ErrorCode.INTERNAL_ERROR
        assert err.message == "something broke"
        assert err.status_code == 500
        assert err.detail is None

    def test_with_detail(self):
        err = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="failed",
            status_code=500,
            detail={"trace": "abc"},
        )
        assert err.detail == {"trace": "abc"}

    def test_is_exception(self):
        err = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="x",
            status_code=500,
        )
        assert isinstance(err, Exception)
        assert str(err) == "x"

    def test_to_dict(self):
        err = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="oops",
            status_code=500,
            detail={"k": "v"},
        )
        d = err.to_dict()
        assert d["code"] == "INTERNAL_ERROR"
        assert d["message"] == "oops"
        assert d["status_code"] == 500
        assert d["detail"] == {"k": "v"}

    def test_to_dict_without_detail(self):
        err = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="oops",
            status_code=500,
        )
        d = err.to_dict()
        assert "detail" not in d or d.get("detail") is None

    def test_can_be_raised_and_caught(self):
        with pytest.raises(AppError):
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message="boom",
                status_code=500,
            )

    def test_preserves_exception_chain(self):
        original = ValueError("root cause")
        try:
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message="wrapped",
                status_code=500,
            ) from original
        except AppError as e:
            assert e.__cause__ is original

    def test_repr(self):
        err = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="test",
            status_code=500,
        )
        r = repr(err)
        assert "AppError" in r
        assert "INTERNAL_ERROR" in r


# ==================== 3. LLMError ====================

class TestLLMError:
    def test_base(self):
        err = LLMError(
            code=ErrorCode.LLM_TIMEOUT,
            message="LLM timed out",
            status_code=504,
        )
        assert isinstance(err, AppError)
        assert err.code == ErrorCode.LLM_TIMEOUT
        assert err.status_code == 504

    def test_timeout_factory(self):
        err = LLMError.timeout(model="gpt-4", timeout_sec=30)
        assert err.code == ErrorCode.LLM_TIMEOUT
        assert "gpt-4" in err.message
        assert "30" in err.message
        assert err.status_code == 504
        assert isinstance(err, LLMError)

    def test_rate_limited_factory(self):
        err = LLMError.rate_limited(model="claude-3")
        assert err.code == ErrorCode.LLM_RATE_LIMITED
        assert "claude-3" in err.message
        assert err.status_code == 429

    def test_auth_failed_factory(self):
        err = LLMError.auth_failed(model="gpt-4")
        assert err.code == ErrorCode.LLM_AUTH_FAILED
        assert err.status_code == 401

    def test_invalid_response_factory(self):
        err = LLMError.invalid_response(model="gpt-4", reason="malformed JSON")
        assert err.code == ErrorCode.LLM_INVALID_RESPONSE
        assert "malformed JSON" in err.message


# ==================== 4. MCPError ====================

class TestMCPError:
    def test_base(self):
        err = MCPError(
            code=ErrorCode.MCP_CONNECTION_FAILED,
            message="connection lost",
            status_code=502,
        )
        assert isinstance(err, AppError)
        assert err.code == ErrorCode.MCP_CONNECTION_FAILED

    def test_connection_failed_factory(self):
        err = MCPError.connection_failed(server="tool-server")
        assert err.code == ErrorCode.MCP_CONNECTION_FAILED
        assert "tool-server" in err.message
        assert err.status_code == 502

    def test_tool_error_factory(self):
        err = MCPError.tool_error(tool="python_execute", reason="syntax error")
        assert err.code == ErrorCode.MCP_TOOL_ERROR
        assert "python_execute" in err.message

    def test_timeout_factory(self):
        err = MCPError.timeout(server="tool-server", timeout_sec=60)
        assert err.code == ErrorCode.MCP_TIMEOUT
        assert "60" in err.message


# ==================== 5. SandboxError ====================

class TestSandboxError:
    def test_base(self):
        err = SandboxError(
            code=ErrorCode.SANDBOX_TIMEOUT,
            message="sandbox timed out",
            status_code=504,
        )
        assert isinstance(err, AppError)

    def test_timeout_factory(self):
        err = SandboxError.timeout(task_id="t1", timeout_sec=120)
        assert err.code == ErrorCode.SANDBOX_TIMEOUT
        assert "t1" in err.message
        assert err.status_code == 504

    def test_exec_failed_factory(self):
        err = SandboxError.exec_failed(task_id="t2", reason="segfault")
        assert err.code == ErrorCode.SANDBOX_EXEC_FAILED
        assert err.status_code == 500

    def test_resource_exceeded_factory(self):
        err = SandboxError.resource_exceeded(task_id="t3", resource="memory")
        assert err.code == ErrorCode.SANDBOX_RESOURCE_EXCEEDED
        assert "memory" in err.message
        assert err.status_code == 413


# ==================== 6. TaskError ====================

class TestTaskError:
    def test_base(self):
        err = TaskError(
            code=ErrorCode.TASK_FAILED,
            message="task failed",
            status_code=500,
        )
        assert isinstance(err, AppError)

    def test_failed_factory(self):
        err = TaskError.failed(task_id="t4", reason="dependency timeout")
        assert err.code == ErrorCode.TASK_FAILED
        assert "t4" in err.message

    def test_cancelled_factory(self):
        err = TaskError.cancelled(task_id="t5")
        assert err.code == ErrorCode.TASK_CANCELLED
        assert err.status_code == 499

    def test_dependency_failed_factory(self):
        err = TaskError.dependency_failed(task_id="t6", dep_id="t5")
        assert err.code == ErrorCode.TASK_DEPENDENCY_FAILED
        assert "t6" in err.message
        assert "t5" in err.message


# ==================== 7. ProviderError ====================

class TestProviderError:
    def test_base(self):
        err = ProviderError(
            code=ErrorCode.PROVIDER_UNAVAILABLE,
            message="provider down",
            status_code=503,
        )
        assert isinstance(err, AppError)

    def test_unavailable_factory(self):
        err = ProviderError.unavailable(provider="anthropic")
        assert err.code == ErrorCode.PROVIDER_UNAVAILABLE
        assert "anthropic" in err.message
        assert err.status_code == 503

    def test_quota_exceeded_factory(self):
        err = ProviderError.quota_exceeded(provider="openai")
        assert err.code == ErrorCode.PROVIDER_QUOTA_EXCEEDED
        assert err.status_code == 429


# ==================== 8. NetworkError ====================

class TestNetworkError:
    def test_base(self):
        err = NetworkError(
            code=ErrorCode.NETWORK_TIMEOUT,
            message="network timeout",
            status_code=504,
        )
        assert isinstance(err, AppError)

    def test_timeout_factory(self):
        err = NetworkError.timeout(url="https://api.example.com")
        assert err.code == ErrorCode.NETWORK_TIMEOUT
        assert "api.example.com" in err.message

    def test_dns_failed_factory(self):
        err = NetworkError.dns_failed(host="example.com")
        assert err.code == ErrorCode.NETWORK_DNS_FAILED

    def test_connection_refused_factory(self):
        err = NetworkError.connection_refused(host="localhost", port=8080)
        assert err.code == ErrorCode.NETWORK_CONNECTION_REFUSED
        assert "8080" in err.message


# ==================== 9. ValidationError ====================

class TestValidationError:
    def test_base(self):
        err = ValidationError(
            code=ErrorCode.VALIDATION_FAILED,
            message="invalid input",
            status_code=422,
        )
        assert isinstance(err, AppError)

    def test_failed_factory(self):
        err = ValidationError.failed(field="name", reason="required")
        assert err.code == ErrorCode.VALIDATION_FAILED
        assert "name" in err.message

    def test_type_error_factory(self):
        err = ValidationError.type_error(field="age", expected="int", got="str")
        assert err.code == ErrorCode.VALIDATION_TYPE_ERROR
        assert "int" in err.message


# ==================== 10. ConfigError ====================

class TestConfigError:
    def test_base(self):
        err = ConfigError(
            code=ErrorCode.CONFIG_MISSING,
            message="config missing",
            status_code=500,
        )
        assert isinstance(err, AppError)

    def test_missing_factory(self):
        err = ConfigError.missing(key="API_KEY")
        assert err.code == ErrorCode.CONFIG_MISSING
        assert "API_KEY" in err.message

    def test_invalid_factory(self):
        err = ConfigError.invalid(key="PORT", reason="must be int")
        assert err.code == ErrorCode.CONFIG_INVALID


# ==================== 11. ResourceError ====================

class TestResourceError:
    def test_base(self):
        err = ResourceError(
            code=ErrorCode.RESOURCE_EXCEEDED,
            message="disk full",
            status_code=507,
        )
        assert isinstance(err, AppError)

    def test_exceeded_factory(self):
        err = ResourceError.exceeded(resource="disk", limit="100GB")
        assert err.code == ErrorCode.RESOURCE_EXCEEDED
        assert "disk" in err.message

    def test_not_found_factory(self):
        err = ResourceError.not_found(resource="file", name="data.csv")
        assert err.code == ErrorCode.RESOURCE_NOT_FOUND
        assert err.status_code == 404


# ==================== 12. Inheritance hierarchy ====================

class TestInheritance:
    ALL_SUBCLASSES = [
        LLMError, MCPError, SandboxError, TaskError,
        ProviderError, NetworkError, ValidationError,
        ConfigError, ResourceError,
    ]

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_subclass_is_app_error(self, cls):
        assert issubclass(cls, AppError)

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_subclass_is_exception(self, cls):
        assert issubclass(cls, Exception)

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_subclass_can_be_caught_as_app_error(self, cls):
        with pytest.raises(AppError):
            raise cls(
                code=ErrorCode.INTERNAL_ERROR,
                message="test",
                status_code=500,
            )
