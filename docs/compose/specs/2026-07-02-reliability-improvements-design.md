# Reliability Improvements Design

## [S1] Problem

Two reliability gaps in the backend:

1. **Error handling:** Global exception handler at `main.py:431` leaks raw `str(exc)` to clients. No structured error codes — errors propagate as raw strings. No consistent error format across routers.

2. **Circuit breaker scope:** Currently only covers `BaseAgent.call_llm` (`base.py:1521-1544`). MCP tool calls, Claude Code CLI subprocess calls, and sandbox code execution have no failure protection — repeated failures waste resources and API credits.

## [S2] Solution Overview

Three interconnected improvements:

1. **Error taxonomy** — Structured error codes with domain-specific subclasses
2. **Circuit breaker registry** — Named breakers extending beyond per-task LLM protection
3. **Retry utility** — Generic async retry decorator with exponential backoff and breaker integration

## [S3] Error Taxonomy

### File: `backend/app/core/errors.py`

**Base class:**
```python
class AppError(Exception):
    code: ErrorCode       # enum value like "LLM_TIMEOUT"
    message: str          # human-readable description
    status_code: int      # HTTP status (default 500)
    detail: Any           # optional structured data
```

**Domain subclasses:**
| Subclass | Domain | Example codes |
|----------|--------|---------------|
| `LLMError` | LLM API calls | `LLM_TIMEOUT`, `LLM_RATE_LIMITED`, `LLM_AUTH_FAILED` |
| `MCPError` | MCP server calls | `MCP_CONNECTION_FAILED`, `MCP_TOOL_FAILED`, `MCP_SERVER_CRASHED` |
| `SandboxError` | Code execution | `SANDBOX_TIMEOUT`, `SANDBOX_MEMORY_EXCEEDED`, `SANDBOX_SAFETY_VIOLATION` |
| `TaskError` | Task management | `TASK_NOT_FOUND`, `TASK_ALREADY_RUNNING`, `TASK_WORKFLOW_FAILED` |
| `ProviderError` | LLM providers | `PROVIDER_NOT_CONFIGURED`, `PROVIDER_UNAVAILABLE`, `PROVIDER_QUOTA_EXCEEDED` |
| `NetworkError` | Network calls | `NET_CONNECTION_REFUSED`, `NET_TIMEOUT`, `NET_DNS_FAILED` |
| `ValidationError` | Input validation | `VALID_MISSING_FIELD`, `VALID_INVALID_FORMAT`, `VALID_OUT_OF_RANGE` |
| `ConfigError` | Configuration | `CONFIG_MISSING_KEY`, `CONFIG_INVALID_VALUE`, `CONFIG_ENV_MISSING` |
| `ResourceError` | File/system | `RESOURCE_DISK_FULL`, `RESOURCE_FILE_NOT_FOUND`, `RESOURCE_PERMISSION_DENIED` |

**ErrorCode enum:** All codes as `str, Enum` values (e.g., `LLM_TIMEOUT = "LLM_TIMEOUT"`).

**Factory classmethods:** Each subclass provides convenience constructors:
```python
LLMError.timeout(model="gpt-4", timeout_sec=300)
MCPError.connection_failed(server_name="arxiv", reason="process exited")
SandboxError.timeout(max_time=60)
```

### Global handler changes (`main.py`)

Replace current handler at line 431:
```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if isinstance(exc, AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code.value, "message": exc.message, "detail": exc.detail}}
        )
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL", "message": "Internal server error"}}
    )
```

### Router/agent changes

Replace `HTTPException` with specific `AppError` subclasses where appropriate:
- `tasks.py`: `TaskError.not_found()`, `TaskError.already_running()`
- `providers.py`: `ProviderError.not_configured()`, `ProviderError.auth_failed()`
- `base.py`: `LLMError.timeout()`, `LLMError.auth_failed()`

## [S4] Circuit Breaker Registry

### File: `backend/app/core/circuit_breaker.py`

**New function:**
```python
_named_breakers: dict[str, CircuitBreaker] = {}

def get_named_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create a named breaker (not per-task)."""
    # Thread-safe, same pattern as get_breaker()
```

**Named breaker instances:**
| Name pattern | Scope | Default config |
|--------------|-------|----------------|
| `mcp_{server_name}` | Per MCP server | 5 failures / 10 min window / 3 min cooldown |
| `sandbox` | Global sandbox | 10 failures / 30 min window / 5 min cooldown |
| `claude_cli` | Claude Code subprocess | 5 failures / 15 min window / 5 min cooldown |

**`@with_breaker` decorator:**
```python
def with_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """Decorator that wraps async function with circuit breaker."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            breaker = get_named_breaker(name, config)
            breaker.check_or_raise()
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception:
                breaker.record_failure()
                raise
        return wrapper
    return decorator
```

### Integration points

1. **MCP client** (`mcp/client.py:73`):
   ```python
   @with_breaker("mcp_{self.config.name}")
   async def call_tool(self, tool_name, arguments): ...
   ```

2. **Sandbox** (`core/sandbox.py:125`):
   ```python
   @with_breaker("sandbox")
   def execute(self, code, language, ...): ...
   ```

3. **Claude Code CLI** (`agents/base.py`):
   - `_call_claude_code_direct` → `@with_breaker("claude_cli")`
   - `_call_claude_code_print` → `@with_breaker("claude_cli")`
   - `_call_claude_code_agent` → `@with_breaker("claude_cli")`

4. **Existing LLM breaker** — unchanged, remains per-task via `get_breaker(task_id)`.

### Orchestrator integration

Extend `orchestrator.py` error handling to catch `CircuitOpenError` from named breakers and broadcast user-friendly messages:
- MCP breaker open → "MCP 服务 {name} 暂时不可用，正在使用备用方案..."
- Sandbox breaker open → "代码执行服务暂时不可用，请稍后重试"
- Claude CLI breaker open → "Claude CLI 服务暂时不可用"

## [S5] Retry Utility

### File: `backend/app/core/retry.py`

```python
@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_base: float = 1.0       # seconds
    backoff_max: float = 60.0       # seconds
    jitter: bool = True
    retry_on: tuple = (Exception,)  # exception types to retry
    breaker_name: Optional[str] = None  # integrate with named breaker

def retry(config: Optional[RetryConfig] = None):
    """Decorator for async functions with exponential backoff."""
```

**Behavior:**
- Exponential backoff: `min(backoff_base * 2^attempt, backoff_max)`
- Jitter: uniform random [0, 0.5 * backoff] added to each wait
- On each retry: log warning with attempt number and exception
- If `breaker_name` set: failures counted toward that breaker
- After max retries: raise last exception (or `MaxRetriesExceeded` wrapping it)

### Integration points

1. **MCP client** — `call_tool` gets `@retry(RetryConfig(max_retries=2, breaker_name="mcp_{server}"))`
2. **LLM adapter** (`llm/adapters/base.py`) — replace hand-coded retry with `@retry`
3. **Research agent MCP calls** — add retry with backoff
4. **Claude Code CLI** — existing retry logic can be replaced with `@retry`

## [S6] Testing

- **Unit tests** for `AppError` hierarchy, `ErrorCode` enum, factory methods
- **Unit tests** for `@with_breaker` decorator (success, failure, circuit open)
- **Unit tests** for `@retry` decorator (exponential backoff, jitter, max retries, breaker integration)
- **Integration tests** for MCP client with breaker
- **Integration tests** for global error handler returning structured JSON

## [S7] Migration

- Existing `HTTPException` raises in routers → migrate to `AppError` subclasses incrementally
- Existing hand-coded retries → replace with `@retry` decorator
- No breaking changes to API response format for non-error responses
- Error responses change from `{"detail": "..."}` to `{"error": {"code": "...", "message": "..."}}`

## [S8] Out of Scope

- API endpoint rate limiting (separate feature)
- Health check improvements (separate feature)
- Graceful shutdown (separate feature)
- Structured/logging with request IDs (separate feature)
