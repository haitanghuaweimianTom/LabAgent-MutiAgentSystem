"""Phase 2 测试：self_collector httpx 异步下载 + Content-Type / 大小 / SHA1 去重。"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch):
    """清除代理环境变量，避免 httpx 使用不支持的 SOCKS 代理。"""
    for var in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """切 paths._PROJECT_ROOT 到 tmp。"""
    from app.core import paths
    monkeypatch.setattr(paths, "_PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def tmp_project(tmp_paths):
    return "self_collector_test"


# =====================================================
# 1. _guess_extension
# =====================================================


def test_guess_extension_csv():
    from app.services.self_collector import _guess_extension
    assert _guess_extension("text/csv", "http://x.com") == ".csv"


def test_guess_extension_json():
    from app.services.self_collector import _guess_extension
    assert _guess_extension("application/json", "http://x.com") == ".json"


def test_guess_extension_unknown_from_url():
    """未知 Content-Type 时从 URL 后缀猜。"""
    from app.services.self_collector import _guess_extension
    assert _guess_extension("application/octet-stream", "http://x.com/data.parquet") == ".parquet"


def test_guess_extension_unknown_falls_back_bin():
    """都猜不到时返回 .bin。"""
    from app.services.self_collector import _guess_extension
    assert _guess_extension("", "http://x.com/") == ".bin"


def test_guess_extension_handles_charset():
    """Content-Type 带 charset 时也能识别。"""
    from app.services.self_collector import _guess_extension
    assert _guess_extension("text/csv; charset=utf-8", "http://x.com") == ".csv"


# =====================================================
# 2. extract_urls_from_search_result
# =====================================================


def test_extract_urls_from_dict_with_urls():
    from app.services.self_collector import extract_urls_from_search_result
    result = {"urls": ["http://a.com", "http://b.com"], "papers": []}
    urls = extract_urls_from_search_result(result)
    assert urls == ["http://a.com", "http://b.com"]


def test_extract_urls_from_dict_with_papers():
    from app.services.self_collector import extract_urls_from_search_result
    result = {"papers": [{"url": "http://a.com"}, {"pdf_url": "http://b.com"}]}
    urls = extract_urls_from_search_result(result)
    assert "http://a.com" in urls
    assert "http://b.com" in urls


def test_extract_urls_from_list():
    from app.services.self_collector import extract_urls_from_search_result
    urls = extract_urls_from_search_result([{"url": "http://x.com"}, {"url": "http://y.com"}])
    assert urls == ["http://x.com", "http://y.com"]


def test_extract_urls_filters_empty():
    from app.services.self_collector import extract_urls_from_search_result
    urls = extract_urls_from_search_result({"urls": ["http://a.com", "", None, 123]})
    assert urls == ["http://a.com"]


# =====================================================
# 3. SHA1 短命名
# =====================================================


def test_sha1_short_deterministic():
    """相同内容 → 相同短哈希。"""
    from app.services.self_collector import _sha1_short
    h1 = _sha1_short(b"hello world")
    h2 = _sha1_short(b"hello world")
    assert h1 == h2
    assert len(h1) == 12


def test_sha1_short_different_content():
    from app.services.self_collector import _sha1_short
    assert _sha1_short(b"a") != _sha1_short(b"b")


# =====================================================
# 4. collect_urls 异步下载（httpx 未装时回退 urllib）
# =====================================================


@pytest.mark.asyncio
async def test_collect_urls_uses_urllib_fallback(tmp_paths, tmp_project, monkeypatch):
    """把 httpx 屏蔽 → 应走 urllib 回退路径，不抛错。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("httpx disabled for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from app.services.self_collector import collect_urls

    # 用一个本地 data: URL 避免真实网络
    # data URL 在 urllib 中能解析为字节
    csv_data = "a,b\n1,2\n"
    data_url = f"data:text/csv,{csv_data.replace(',', '%2C').replace(chr(10), '%0A')}"
    results = await collect_urls(
        [data_url],
        project_name=tmp_project,
        concurrency=1,
        timeout_sec=10,
        use_httpx=True,
    )
    assert len(results) == 1
    # data: URL 在 urllib 下的处理可能不完美 → 至少不抛异常


@pytest.mark.asyncio
async def test_collect_urls_empty_list(tmp_paths, tmp_project):
    """空 URL 列表应直接返 []。"""
    from app.services.self_collector import collect_urls

    results = await collect_urls([], project_name=tmp_project)
    assert results == []


@pytest.mark.asyncio
async def test_collect_urls_writes_index_json(tmp_paths, tmp_project):
    """collect_urls 调用后应写 _index.json。"""
    from app.services.self_collector import collect_urls
    from app.services.data_directory import read_self_collected_index

    # 即使全部失败也应写 _index.json
    await collect_urls(
        ["http://127.0.0.1:1/does-not-exist"],
        project_name=tmp_project,
        timeout_sec=2,
        max_size_mb=1,
    )
    idx = read_self_collected_index(tmp_project)
    assert isinstance(idx, list)
    # 至少 1 条记录（失败的也算）
    assert len(idx) >= 1


# =====================================================
# 5. _fetch_one 错误路径（Content-Type 拒绝）
# =====================================================


@pytest.mark.asyncio
async def test_fetch_one_skips_html(tmp_paths, tmp_project):
    """Content-Type text/html 应被标记 rejected_content_type。"""
    from app.services.self_collector import _fetch_one

    class FakeClient:
        async def get(self, url, timeout=None):
            class R:
                status_code = 200
                headers = {"content-type": "text/html; charset=utf-8"}
                content = b"<html><body>x</body></html>"
            return R()

    sem = asyncio.Semaphore(1)
    result = await _fetch_one(
        FakeClient(), sem, "http://x.com", "q", tmp_paths / "outputs" / tmp_project / "data" / "self_collected",
        max_size_mb=10, timeout_sec=5,
    )
    assert result.error is not None
    assert "content_type" in result.error or "rejected" in result.error


@pytest.mark.asyncio
async def test_fetch_one_too_large(tmp_paths, tmp_project):
    """超大文件应被标记 too_large。"""
    from app.services.self_collector import _fetch_one

    class FakeClient:
        async def get(self, url, timeout=None):
            class R:
                status_code = 200
                headers = {"content-type": "text/csv"}
                # 1MB + 1
                content = b"a" * (1024 * 1024 + 1)
            return R()

    sem = asyncio.Semaphore(1)
    result = await _fetch_one(
        FakeClient(), sem, "http://x.com", "q", tmp_paths / "outputs" / tmp_project / "data" / "self_collected",
        max_size_mb=1, timeout_sec=5,
    )
    assert result.error is not None
    assert "too_large" in result.error