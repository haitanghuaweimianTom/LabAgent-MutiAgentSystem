# 健康检查 + 结构化日志 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `/health` endpoint with real dependency checks and add structured JSON logging with correlation IDs for production observability.

**Architecture:** Two new core modules — `health.py` (async health checks for Redis, disk, LLM providers) and `structured_logging.py` (JSON formatter + correlation ID middleware). The existing `/health` endpoint in `main.py` delegates to the new health module. A FastAPI middleware injects correlation IDs into every request.

**Tech Stack:** Python stdlib `logging` + `json` for structured output, `httpx` for LLM provider checks, `shutil` for disk checks, `asyncio` for concurrent health probes. No new dependencies.

---

## Global Constraints

- Python 3.9+ (project requirement)
- No new pip dependencies — use only what's already in requirements.txt
- All new code in `backend/app/core/`
- Tests in `backend/tests/`
- Follow existing patterns: `logging.getLogger(__name__)`, Pydantic models for data

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/core/health.py` | Health check logic — async probes for Redis, disk, LLM providers |
| Create | `backend/app/core/structured_logging.py` | JSON log formatter + correlation ID context var |
| Create | `backend/app/core/logging_middleware.py` | FastAPI middleware for correlation ID injection + request logging |
| Modify | `backend/app/main.py:36-37` | Replace `basicConfig` with structured logging setup |
| Modify | `backend/app/main.py:90-139` | Add logging middleware to lifespan |
| Modify | `backend/app/main.py:172-174` | Replace stub `/health` with real health checks |
| Create | `backend/tests/test_health.py` | Unit tests for health check module |
| Create | `backend/tests/test_structured_logging.py` | Unit tests for JSON formatter + correlation ID |

---

## Task 1: Structured Logging Foundation

**Files:**
- Create: `backend/app/core/structured_logging.py`
- Create: `backend/tests/test_structured_logging.py`

**Interfaces:**
- Produces: `setup_structured_logging()`, `correlation_id_var` (contextvars.ContextVar), `JsonFormatter`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_structured_logging.py
import json
import logging
from backend.app.core.structured_logging import JsonFormatter, correlation_id_var, setup_structured_logging


class TestJsonFormatter:
    def test_formats_log_record_as_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello world", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert data["logger"] == "test"
        assert "timestamp" in data

    def test_includes_correlation_id_when_set(self):
        correlation_id_var.set("req-123")
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["correlation_id"] == "req-123"
        correlation_id_var.set(None)

    def test_excludes_correlation_id_when_none(self):
        correlation_id_var.set(None)
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "correlation_id" not in data


class TestSetupStructuredLogging:
    def test_configures_root_logger(self):
        setup_structured_logging(level=logging.DEBUG)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -m pytest backend/tests/test_structured_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.core.structured_logging'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/structured_logging.py
"""结构化日志 — JSON 格式 + correlation ID 追踪。

correlation_id_var 是一个 contextvars.ContextVar，每个请求自动注入唯一 ID。
JsonFormatter 将所有日志输出为 JSON，便于 ELK/Loki 等日志聚合系统解析。
"""
from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

# 每个请求的 correlation ID，自动在异步上下文中传播
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class JsonFormatter(logging.Formatter):
    """将 LogRecord 格式化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        cid = correlation_id_var.get()
        if cid:
            log_entry["correlation_id"] = cid

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, ensure_ascii=False)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """配置根 logger 使用 JSON 格式输出到 stderr。"""
    root = logging.getLogger()
    root.setLevel(level)

    # 清除已有 handler 防止重复
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -m pytest backend/tests/test_structured_logging.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/structured_logging.py backend/tests/test_structured_logging.py
git commit -m "feat: add structured JSON logging with correlation ID"
```

---

## Task 2: Request Logging Middleware

**Files:**
- Create: `backend/app/core/logging_middleware.py`
- Modify: `backend/app/main.py` (add middleware)

**Interfaces:**
- Consumes: `correlation_id_var` from `structured_logging.py`
- Produces: `RequestLoggingMiddleware` class for FastAPI

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_logging_middleware.py
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.core.logging_middleware import RequestLoggingMiddleware
from backend.app.core.structured_logging import correlation_id_var


def test_middleware_injects_correlation_id():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/test")
    async def endpoint():
        return {"cid": correlation_id_var.get()}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    cid = resp.json()["cid"]
    assert cid is not None
    assert len(cid) > 0


def test_middleware_uses_provided_correlation_id():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/test")
    async def endpoint():
        return {"cid": correlation_id_var.get()}

    client = TestClient(app)
    custom_id = "my-custom-id-123"
    resp = client.get("/test", headers={"X-Correlation-ID": custom_id})
    assert resp.json()["cid"] == custom_id


def test_middleware_returns_correlation_id_in_response_header():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/test")
    async def endpoint():
        return "ok"

    client = TestClient(app)
    resp = client.get("/test")
    assert "X-Correlation-ID" in resp.headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -m pytest backend/tests/test_logging_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/logging_middleware.py
"""请求日志中间件 — 注入 correlation ID 并记录请求/响应。"""
from __future__ import annotations

import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .structured_logging import correlation_id_var

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 correlation ID，记录耗时和状态码。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        # 从请求头获取或生成 correlation ID
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:12]
        correlation_id_var.set(cid)

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                f"{request.method} {request.url.path} -> 500 ({elapsed_ms:.0f}ms)"
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({elapsed_ms:.0f}ms)"
        )

        # 将 correlation ID 放入响应头
        response.headers["X-Correlation-ID"] = cid
        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -m pytest backend/tests/test_logging_middleware.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Integrate into main.py**

In `backend/app/main.py`, add import and middleware registration:

```python
# Add after line 15 (after existing imports):
from .core.logging_middleware import RequestLoggingMiddleware

# Add after line 151 (after CORSMiddleware):
app.add_middleware(RequestLoggingMiddleware)
```

- [ ] **Step 6: Replace logging.basicConfig with structured logging**

In `backend/app/main.py`, replace lines 36-37:

```python
# OLD:
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# NEW:
from .core.structured_logging import setup_structured_logging
setup_structured_logging(level=logging.INFO)
logger = logging.getLogger(__name__)
```

- [ ] **Step 7: Run all tests to verify no regressions**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -m pytest backend/tests/ -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/logging_middleware.py backend/tests/test_logging_middleware.py backend/app/main.py
git commit -m "feat: add request logging middleware with correlation IDs"
```

---

## Task 3: Health Check Module

**Files:**
- Create: `backend/app/core/health.py`
- Create: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `async def check_health() -> HealthReport`, `HealthReport` dataclass

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_health.py
import asyncio
from unittest.mock import patch, AsyncMock
from backend.app.core.health import check_health, HealthReport, ComponentHealth


class TestComponentHealth:
    def test_healthy_component(self):
        h = ComponentHealth(name="test", status="healthy", message="ok", latency_ms=1.0)
        assert h.status == "healthy"

    def test_to_dict(self):
        h = ComponentHealth(name="test", status="healthy", message="ok", latency_ms=1.0)
        d = h.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "healthy"


class TestCheckHealth:
    def test_returns_health_report(self):
        report = asyncio.get_event_loop().run_until_complete(check_health())
        assert isinstance(report, HealthReport)
        assert report.status in ("healthy", "degraded", "unhealthy")
        assert len(report.components) > 0

    def test_disk_check_always_present(self):
        report = asyncio.get_event_loop().run_until_complete(check_health())
        names = [c.name for c in report.components]
        assert "disk" in names

    def test_uptime_is_positive(self):
        report = asyncio.get_event_loop().run_until_complete(check_health())
        assert report.uptime_seconds >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -m pytest backend/tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/health.py
"""健康检查模块 — 异步探测 Redis、磁盘、LLM Provider 可用性。

用法:
    report = await check_health()
    if report.status != "healthy":
        logger.warning(f"Health degraded: {report}")
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# 应用启动时间（模块级）
_app_start_time: float = time.time()


@dataclass
class ComponentHealth:
    name: str
    status: str  # "healthy" | "degraded" | "unhealthy"
    message: str
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "latency_ms": round(self.latency_ms, 1),
        }


@dataclass
class HealthReport:
    status: str  # "healthy" | "degraded" | "unhealthy"
    components: List[ComponentHealth] = field(default_factory=list)
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "components": [c.to_dict() for c in self.components],
        }


async def _check_disk() -> ComponentHealth:
    """检查磁盘空间（根分区剩余 < 1GB 为 degraded，< 100MB 为 unhealthy）。"""
    start = time.perf_counter()
    try:
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024 ** 3)
        latency = (time.perf_counter() - start) * 1000

        if free_gb < 0.1:
            status, msg = "unhealthy", f"磁盘空间不足: {free_gb:.2f} GB"
        elif free_gb < 1.0:
            status, msg = "degraded", f"磁盘空间偏低: {free_gb:.2f} GB"
        else:
            status, msg = "healthy", f"磁盘空间充足: {free_gb:.2f} GB"

        return ComponentHealth(name="disk", status=status, message=msg, latency_ms=latency)
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(name="disk", status="unhealthy", message=str(e), latency_ms=latency)


async def _check_redis() -> ComponentHealth:
    """检查 Redis 连接。"""
    start = time.perf_counter()
    try:
        import redis.asyncio as aioredis
        from ..config import get_settings
        settings = get_settings()
        # 从环境变量或默认值获取 Redis URL
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

        client = aioredis.from_url(redis_url, socket_connect_timeout=3)
        await client.ping()
        await client.aclose()

        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(name="redis", status="healthy", message="连接正常", latency_ms=latency)
    except ImportError:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(name="redis", status="degraded", message="redis 未安装，跳过检查", latency_ms=latency)
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(name="redis", status="unhealthy", message=f"连接失败: {e}", latency_ms=latency)


async def _check_llm_providers() -> ComponentHealth:
    """检查默认 LLM Provider 的 API Key 是否已配置。"""
    start = time.perf_counter()
    try:
        from ..config import get_settings
        settings = get_settings()

        providers_configured = []
        if settings.anthropic_api_key:
            providers_configured.append("anthropic")
        if settings.openai_api_key:
            providers_configured.append("openai")
        if settings.gemini_api_key:
            providers_configured.append("gemini")
        if settings.ollama_base_url:
            providers_configured.append("ollama")

        latency = (time.perf_counter() - start) * 1000

        if not providers_configured:
            return ComponentHealth(
                name="llm_providers",
                status="degraded",
                message="未配置任何 LLM Provider API Key",
                latency_ms=latency,
            )

        return ComponentHealth(
            name="llm_providers",
            status="healthy",
            message=f"已配置: {', '.join(providers_configured)}",
            latency_ms=latency,
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(name="llm_providers", status="unhealthy", message=str(e), latency_ms=latency)


async def _check_tasks() -> ComponentHealth:
    """检查任务系统状态。"""
    start = time.perf_counter()
    try:
        from ..core.task_persistence import list_all_tasks
        tasks = list_all_tasks()
        active = [t for t in tasks if t.get("status") in ("running", "in_progress")]
        latency = (time.perf_counter() - start) * 1000

        return ComponentHealth(
            name="tasks",
            status="healthy",
            message=f"总计 {len(tasks)} 个任务, {len(active)} 个运行中",
            latency_ms=latency,
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(name="tasks", status="unhealthy", message=str(e), latency_ms=latency)


async def check_health() -> HealthReport:
    """执行所有健康检查，返回汇总报告。"""
    checks = await asyncio.gather(
        _check_disk(),
        _check_redis(),
        _check_llm_providers(),
        _check_tasks(),
        return_exceptions=True,
    )

    components: List[ComponentHealth] = []
    for result in checks:
        if isinstance(result, Exception):
            components.append(ComponentHealth(
                name="unknown", status="unhealthy", message=str(result)
            ))
        else:
            components.append(result)

    # 汇总状态：任一 unhealthy → 整体 unhealthy；任一 degraded → 整体 degraded
    statuses = [c.status for c in components]
    if "unhealthy" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthReport(
        status=overall,
        components=components,
        uptime_seconds=time.time() - _app_start_time,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -m pytest backend/tests/test_health.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/health.py backend/tests/test_health.py
git commit -m "feat: add async health check module for Redis, disk, LLM providers"
```

---

## Task 4: Replace Stub /health Endpoint

**Files:**
- Modify: `backend/app/main.py:172-174`

**Interfaces:**
- Consumes: `check_health()` from `health.py`

- [ ] **Step 1: Update /health endpoint**

In `backend/app/main.py`, replace lines 172-174:

```python
# OLD:
@app.get("/health")
async def health():
    return {"status": "healthy"}

# NEW:
@app.get("/health")
async def health():
    from .core.health import check_health
    report = await check_health()
    status_code = 200 if report.status == "healthy" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=report.to_dict(), status_code=status_code)
```

- [ ] **Step 2: Run health check manually**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -c "import asyncio; from backend.app.core.health import check_health; r = asyncio.get_event_loop().run_until_complete(check_health()); print(r.to_dict())"`
Expected: JSON output with disk, redis, llm_providers, tasks components

- [ ] **Step 3: Run all tests**

Run: `cd /home/tomgame/projects/MathModel-MutiAgentSystem && python -m pytest backend/tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: replace stub /health endpoint with real dependency checks"
```

---

## Task 5: Integration Verification

- [ ] **Step 1: Start the server and test health endpoint**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/health | python -m json.tool
```

Expected output:
```json
{
    "status": "healthy",
    "uptime_seconds": 3.1,
    "components": [
        {"name": "disk", "status": "healthy", "message": "磁盘空间充足: XX.XX GB", "latency_ms": 0.X},
        {"name": "redis", "status": "unhealthy|degraded|healthy", ...},
        {"name": "llm_providers", "status": "...", ...},
        {"name": "tasks", "status": "healthy", ...}
    ]
}
```

- [ ] **Step 2: Test correlation ID in logs**

```bash
curl -s -H "X-Correlation-ID: test-abc-123" http://localhost:8000/health
```

Check server stderr for log line containing `"correlation_id": "test-abc-123"`.

- [ ] **Step 3: Kill server and clean up**

```bash
kill %1 2>/dev/null; true
```

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: health check and logging integration fixes"
```
