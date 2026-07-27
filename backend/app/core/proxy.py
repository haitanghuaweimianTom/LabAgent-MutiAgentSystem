"""系统代理自动检测 + 智能回退（跨平台，开箱即用）。

设计目标（用户诉求）：不同电脑都能用；挂了代理就自动用上。
关键约束：本机 LLM 是国产 provider（ARK/Kimi 等），**绝不能**走代理——
所以这里**绝不全局写 HTTPS_PROXY 环境变量**，而是只对"取数据"的 httpx 客户端
按需注入代理。

检测顺序（手动覆盖 > 环境变量 > 系统设置）：
- 手动覆盖：用户在前端填的代理 URL（存 backend/data/proxy_settings.json）
- 环境变量：HTTP_PROXY / HTTPS_PROXY / ALL_PROXY（含大小写）
- Linux：gsettings（GNOME）+ kioslaverc（KDE）
- macOS：scutil --proxy
- Windows：urllib.request.getproxies()（读注册表）

智能回退（``smart_get``）：每个请求先直连；仅在**连接级失败**时才走代理重试。
直连可达时完全不碰代理 → 对 GitHub/hf-mirror/Kaggle 等本就直连可达的源零回归；
只有被墙的站点（如官方 huggingface.co）直连失败才会用代理救场。

socks 代理：httpx 0.28 + socksio 支持 socks5://；requests + PySocks 同理。
检测到 socks 但缺库时跳过（不崩溃）。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.request import getproxies as _urllib_getproxies

import httpx

logger = logging.getLogger(__name__)

# 代理设置存储（手动覆盖 + 全局开关）
_SETTINGS_FILE = (
    Path(__file__).parent.parent.parent.parent / "backend" / "data" / "proxy_settings.json"
)

# 检测缓存（避免每次采集都 spawn gsettings/scutil 子进程）
_cache: Dict[str, Any] = {"proxy": None, "source": None, "ts": 0.0}
_CACHE_TTL = 30.0  # 秒


def _load() -> Dict[str, Any]:
    if not _SETTINGS_FILE.exists():
        return {}
    try:
        d = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception as e:
        logger.debug(f"读取 proxy_settings.json 失败: {e}")
        return {}


def _save(d: Dict[str, Any]) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _socks_supported() -> bool:
    try:
        import socksio  # noqa: F401
        return True
    except ImportError:
        return False


def _detect_env() -> Tuple[Optional[str], str]:
    for v in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.environ.get(v, "").strip()
        if val:
            return val, f"env:{v}"
    return None, ""


def _detect_gnome() -> Tuple[Optional[str], str]:
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.system.proxy", "mode"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return None, ""
        mode = r.stdout.strip()
        if mode not in ("'manual'", "manual"):
            return None, ""
        # 优先 https，回退 http
        for scheme in ("https", "http"):
            h = subprocess.run(
                ["gsettings", "get", f"org.gnome.system.proxy.{scheme}", "host"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip().strip("'")
            p = subprocess.run(
                ["gsettings", "get", f"org.gnome.system.proxy.{scheme}", "port"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            if h and p and h != "''" and p not in ("0", ""):
                return f"http://{h}:{p}", f"gsettings:{scheme}"
    except Exception as e:
        logger.debug(f"gsettings 代理检测失败: {e}")
    return None, ""


def _detect_kde() -> Tuple[Optional[str], str]:
    try:
        kio = Path.home() / ".config" / "kioslaverc"
        if not kio.exists():
            return None, ""
        cfg: Dict[str, str] = {}
        section = ""
        for line in kio.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                continue
            if "=" in line and section == "Proxy Settings":
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
        # ProxyType=1 手动
        if cfg.get("ProxyType") == "1":
            for key in ("httpsProxy", "httpProxy"):
                val = cfg.get(key, "").strip()
                if val:
                    # 形如 http://127.0.0.1 7890 或 http://127.0.0.1:7890
                    val = val.replace(" ", ":").replace("//:", "//")
                    return val, f"kde:{key}"
    except Exception as e:
        logger.debug(f"KDE 代理检测失败: {e}")
    return None, ""


def _detect_macos() -> Tuple[Optional[str], str]:
    try:
        r = subprocess.run(["scutil", "--proxy"], capture_output=True, text=True, timeout=3)
        d: Dict[str, str] = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                d[k.strip()] = v.strip()
        if d.get("HTTPSEnable") == "1" and d.get("HTTPProxy"):
            return f"http://{d['HTTPProxy']}:{d.get('HTTPPort', '8080')}", "scutil:https"
        if d.get("HTTPEnable") == "1" and d.get("HTTPProxy"):
            return f"http://{d['HTTPProxy']}:{d.get('HTTPPort', '8080')}", "scutil:http"
    except Exception as e:
        logger.debug(f"scutil 代理检测失败: {e}")
    return None, ""


def _detect_windows() -> Tuple[Optional[str], str]:
    try:
        px = _urllib_getproxies()
        for s in ("https", "http"):
            if px.get(s):
                return px[s], f"registry:{s}"
    except Exception as e:
        logger.debug(f"Windows 代理检测失败: {e}")
    return None, ""


def _platform_detectors():
    if sys.platform == "darwin":
        return (_detect_macos, _detect_gnome, _detect_kde)
    if sys.platform == "win32":
        return (_detect_windows,)
    return (_detect_gnome, _detect_kde)


def detect_system_proxy(force: bool = False) -> Optional[str]:
    """检测系统代理 URL。缓存 _CACHE_TTL 秒。返回形如 ``http://127.0.0.1:7890`` 或 None。"""
    now = time.time()
    if not force and _cache.get("ts") and now - _cache["ts"] < _CACHE_TTL:
        return _cache.get("proxy")

    cfg = _load()
    # 1. 手动覆盖优先（用户明确指定）
    if cfg.get("manual_enabled") and (cfg.get("manual_proxy") or "").strip():
        p = cfg["manual_proxy"].strip()
        _cache.update(proxy=p, source="manual", ts=now)
        return p
    # 2. 全局开关关闭 → 不用代理
    if not cfg.get("use_proxy", True):
        _cache.update(proxy=None, source="disabled", ts=now)
        return None
    # 3. 环境变量
    p, src = _detect_env()
    # 4. 平台系统设置
    if not p:
        for det in _platform_detectors():
            p, src = det()
            if p:
                break
    # 5. socks 代理需 socksio
    if p and p.lower().startswith("socks") and not _socks_supported():
        logger.warning(f"检测到 socks 代理 {p} 但未安装 socksio（httpx[socks]），已忽略")
        p, src = None, "socks_no_support"
    _cache.update(proxy=p, source=src or "none", ts=now)
    if p:
        logger.info(f"[proxy] 检测到系统代理: {p} (来源: {src})")
    return p


def get_proxy_status() -> Dict[str, Any]:
    """前端展示用：检测到的代理 + 来源 + 各开关状态。"""
    p = detect_system_proxy(force=True)
    cfg = _load()
    return {
        "detected": p,
        "source": _cache.get("source"),
        "use_proxy": cfg.get("use_proxy", True),
        "manual_proxy": cfg.get("manual_proxy", ""),
        "manual_enabled": cfg.get("manual_enabled", False),
        "socks_supported": _socks_supported(),
        "updated_at": cfg.get("updated_at"),
    }


def set_proxy_settings(
    manual_proxy: Optional[str] = None,
    manual_enabled: Optional[bool] = None,
    use_proxy: Optional[bool] = None,
) -> Dict[str, Any]:
    """更新代理设置（任一字段 None 表示不改）。"""
    cfg = _load()
    if manual_proxy is not None:
        cfg["manual_proxy"] = manual_proxy.strip()
    if manual_enabled is not None:
        cfg["manual_enabled"] = bool(manual_enabled)
    if use_proxy is not None:
        cfg["use_proxy"] = bool(use_proxy)
    from datetime import datetime
    cfg["updated_at"] = datetime.now().isoformat()
    _save(cfg)
    _cache.update(proxy=None, ts=0.0)  # 失效缓存
    return get_proxy_status()


def clear_manual_proxy() -> Dict[str, Any]:
    return set_proxy_settings(manual_proxy="", manual_enabled=False)


async def test_proxy(proxy_url: Optional[str] = None) -> Dict[str, Any]:
    """测试代理连通性：能否通过该代理访问外部站点。

    对照直连 + 通过代理访问一个稳定 URL，让用户判断代理是否真的有效。
    """
    px = proxy_url or detect_system_proxy(force=True)
    if not px:
        return {"ok": False, "message": "未检测到代理（直连模式）；如需代理请在前端手动填写"}

    # 1. 直连对照（看目标直连是否已通——若已通则代理并非必需）
    direct_status: Optional[int] = None
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            dr = await c.get("https://api.github.com/rate_limit")
            direct_status = dr.status_code
    except Exception:
        direct_status = None

    # 2. 通过代理访问
    try:
        async with httpx.AsyncClient(proxy=px, timeout=12.0) as c:
            r = await c.get("https://api.github.com/rate_limit")
        ok = r.status_code == 200
        return {
            "ok": ok,
            "proxy": px,
            "via_proxy_status": r.status_code,
            "direct_status": direct_status,
            "message": (
                f"代理可用（通过代理 HTTP {r.status_code}）" if ok
                else f"代理响应异常（通过代理 HTTP {r.status_code}，直连 {direct_status}）"
            ),
        }
    except Exception as e:
        return {
            "ok": False,
            "proxy": px,
            "direct_status": direct_status,
            "message": f"代理不可用: {type(e).__name__}: {e}",
        }


# ---------------------------------------------------------------------------
# 智能回退取数：直连优先，连接级失败才走代理
# ---------------------------------------------------------------------------

# 连接级异常：只有这类异常才值得回退到代理（超时/网络不可达/DNS 失败等）
_CONN_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError)


async def smart_get(
    url: str,
    *,
    timeout: float = 20.0,
    follow_redirects: bool = True,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    allow_proxy: bool = True,
) -> httpx.Response:
    """先直连，连接级失败再走代理重试。

    直连可达时完全不碰代理 → 对直连可达的源零回归；
    仅当目标被墙、直连连接失败时才回退到检测到的代理。
    """
    direct_exc: Optional[Exception] = None
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=follow_redirects
        ) as c:
            return await c.get(url, headers=headers, params=params)
    except _CONN_ERRORS as e:
        direct_exc = e
    except Exception:
        raise

    if not allow_proxy:
        raise direct_exc  # type: ignore[misc]

    px = detect_system_proxy()
    if not px:
        raise direct_exc  # type: ignore[misc]

    logger.info(f"[proxy] 直连 {url} 失败，回退代理 {px}")
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=follow_redirects, proxy=px
    ) as c:
        try:
            return await c.get(url, headers=headers, params=params)
        except Exception:
            # 代理也失败 → 抛直连的原始错误（更贴近用户预期）
            raise direct_exc  # type: ignore[misc]


def make_proxied_client(**kwargs: Any) -> httpx.AsyncClient:
    """构造一个已注入代理的 httpx 客户端（无代理时等价于普通客户端）。

    用于需要复用同一客户端发多请求的场景。多数情况下优先用 ``smart_get``。
    """
    px = detect_system_proxy()
    if px:
        kwargs.setdefault("proxy", px)
    return httpx.AsyncClient(**kwargs)


@asynccontextmanager
async def proxy_env_if_needed(host: str, timeout: float = 4.0):
    """供依赖环境变量代理的库（如 Kaggle SDK / requests）使用。

    先快速探测 host 是否直连可达：可达则不动环境变量（零回归）；
    不可达才临时写入 HTTP(S)_PROXY 环境变量，退出后还原。
    """
    px = detect_system_proxy()
    if not px:
        yield
        return
    # 快速直连探测
    direct_ok = False
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.head(f"https://{host}", follow_redirects=True)
            direct_ok = r.status_code < 500
    except Exception:
        direct_ok = False

    if direct_ok:
        yield
        return

    # socks 代理需 PySocks（requests 才能用）；缺则放弃，避免崩溃
    if px.lower().startswith("socks"):
        try:
            import socks  # noqa: F401
        except ImportError:
            logger.warning(f"[proxy] {host} 直连不可达且 socks 代理 {px} 缺 PySocks，无法走代理")
            yield
            return

    logger.info(f"[proxy] {host} 直连不可达，临时走代理 {px}")
    saved: Dict[str, Optional[str]] = {}
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        saved[v] = os.environ.get(v)
        os.environ[v] = px
    try:
        yield
    finally:
        for v, val in saved.items():
            if val is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = val

async def maybe_set_proxy_env_for(host: str, timeout: float = 4.0):
    """供同步、依赖 env 代理的库（如 Kaggle SDK / requests）使用。

    若 host 直连可达 → 返回 None（不设 env，零回归）；
    若直连不可达且检测到代理 → 临时写入 HTTP(S)_PROXY env，返回一个恢复函数，
    调用之即可还原环境变量。用 ``__aenter__`` 之外的轻量写法，避免大段代码缩进。
    """
    px = detect_system_proxy()
    if not px:
        return None
    direct_ok = False
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.head(f"https://{host}", follow_redirects=True)
            direct_ok = r.status_code < 500
    except Exception:
        direct_ok = False
    if direct_ok:
        return None
    if px.lower().startswith("socks"):
        try:
            import socks  # noqa: F401
        except ImportError:
            logger.warning(f"[proxy] {host} 直连不可达且 socks 代理 {px} 缺 PySocks，无法走代理")
            return None
    logger.info(f"[proxy] {host} 直连不可达，临时走代理 {px}")
    saved: Dict[str, Optional[str]] = {}
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        saved[v] = os.environ.get(v)
        os.environ[v] = px

    def _restore() -> None:
        for v, val in saved.items():
            if val is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = val

    return _restore
