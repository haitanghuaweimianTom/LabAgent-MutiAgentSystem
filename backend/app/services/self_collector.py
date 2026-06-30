"""v5.3.0 自主数据收集器（httpx 异步并发下载）

替代 preflight.self_collect_data 中的「只记录 URL」占位逻辑：
- httpx.AsyncClient 并发下载（Semaphore 控制并发）
- Content-Type 校验 + 扩展名白名单
- 大小限制 + SHA1 命名去重
- 元数据写 self_collected/_index.json
"""
import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.paths import get_project_data_subdir
from .data_directory import append_self_collected_index, SelfCollectedMeta

logger = logging.getLogger(__name__)

# 允许下载的 Content-Type
_ACCEPT_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/json",
    "application/ld+json",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/tab-separated-values",
    "application/xml",
    "text/xml",
    "application/parquet",
    "application/octet-stream",  # 兜底
}

# 拒绝下载的 Content-Type
_REJECT_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/javascript",
}

# 扩展名白名单（最终落盘用）
_EXT_BY_CONTENT_TYPE = {
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/json": ".json",
    "application/ld+json": ".json",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
    "text/tab-separated-values": ".tsv",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/parquet": ".parquet",
}


@dataclass
class DownloadResult:
    """单条 URL 下载结果"""
    url: str
    filename: Optional[str] = None
    size: int = 0
    http_status: int = 0
    content_type: str = ""
    source_query: str = ""
    downloaded_at: int = 0
    error: Optional[str] = None
    elapsed_ms: int = 0


def _guess_extension(content_type: str, url: str) -> str:
    """从 Content-Type 或 URL 猜扩展名"""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _EXT_BY_CONTENT_TYPE:
        return _EXT_BY_CONTENT_TYPE[ct]
    # 从 URL 路径猜
    path = url.split("?", 1)[0].split("#", 1)[0]
    m = re.search(r"\.(csv|json|xlsx?|txt|tsv|parquet|xml|pdf|zip|jsonl|ndjson)(\.gz)?$", path.lower())
    if m:
        return "." + m.group(1) + (m.group(2) or "")
    return ".bin"


def _sha1_short(content: bytes) -> str:
    return hashlib.sha1(content).hexdigest()[:12]


async def _fetch_one(
    client: Any,
    sem: asyncio.Semaphore,
    url: str,
    source_query: str,
    target_dir: Path,
    max_size_mb: int,
    timeout_sec: int,
) -> DownloadResult:
    """下载单个 URL，带去重 + 大小限制 + Content-Type 校验"""
    started = time.time()
    result = DownloadResult(
        url=url,
        source_query=source_query,
        downloaded_at=int(time.time() * 1000),
    )
    try:
        async with sem:
            resp = await client.get(url, timeout=timeout_sec)
            result.http_status = resp.status_code
            ct = resp.headers.get("content-type", "")
            result.content_type = ct

            if resp.status_code >= 400:
                result.error = f"http_{resp.status_code}"
                return result

            # Content-Type 拒绝列表
            ct_base = ct.split(";")[0].strip().lower()
            if ct_base in _REJECT_CONTENT_TYPES:
                result.error = f"rejected_content_type:{ct_base}"
                return result

            # 读取内容（带大小保护）
            max_bytes = max_size_mb * 1024 * 1024
            content = resp.content
            if len(content) > max_bytes:
                result.error = f"too_large:{len(content)}"
                return result

            # SHA1 命名去重
            sha = _sha1_short(content)
            ext = _guess_extension(ct, url)
            filename = f"{sha}{ext}"

            target_path = target_dir / filename
            # 如果文件已存在 → 视为已下载，不重复落盘
            if not target_path.exists():
                target_path.write_bytes(content)

            result.filename = filename
            result.size = len(content)
            result.elapsed_ms = int((time.time() - started) * 1000)
            return result
    except asyncio.TimeoutError:
        result.error = "timeout"
        return result
    except Exception as e:
        result.error = f"exception:{type(e).__name__}:{e}"
        return result


async def collect_urls(
    urls: List[str],
    project_name: Optional[str],
    source_query: str = "",
    concurrency: int = 4,
    timeout_sec: int = 30,
    max_size_mb: int = 50,
    use_httpx: bool = True,
) -> List[DownloadResult]:
    """异步并发下载一组 URL，返回结果列表。

    Args:
        urls: 待下载 URL 列表
        project_name: 项目名（None = 全局）
        source_query: 来源查询关键词（写 _index.json 用）
        concurrency: 最大并发数
        timeout_sec: 单个请求超时
        max_size_mb: 单文件最大大小（MB）
        use_httpx: True=httpx, False=urllib（用于测试 / 无 httpx 环境）

    Returns:
        DownloadResult 列表；filename 非空 = 成功
    """
    if not urls:
        return []

    target_dir = get_project_data_subdir(project_name, "self_collected")
    sem = asyncio.Semaphore(concurrency)

    async def _all():
        if use_httpx:
            try:
                import httpx
            except ImportError:
                logger.warning("[self_collector] httpx 未安装，回退到 urllib（同步）")
                return await _collect_with_urllib(
                    urls, source_query, target_dir, max_size_mb, timeout_sec
                )
            async with httpx.AsyncClient(
                timeout=timeout_sec,
                follow_redirects=True,
                headers={"User-Agent": "MathModel-MutiAgent/5.3 (+self-collector)"},
            ) as client:
                tasks = [
                    _fetch_one(client, sem, u, source_query, target_dir, max_size_mb, timeout_sec)
                    for u in urls
                ]
                return await asyncio.gather(*tasks)
        else:
            return await _collect_with_urllib(
                urls, source_query, target_dir, max_size_mb, timeout_sec
            )

    results = await _all()

    # 写 _index.json（追加）
    index_entries = []
    for r in results:
        meta = SelfCollectedMeta(
            url=r.url,
            filename=r.filename,
            size=r.size,
            downloaded_at=r.downloaded_at,
            content_type=r.content_type,
            source_query=r.source_query,
            http_status=r.http_status,
            error=r.error,
        )
        index_entries.append(meta.to_dict())
    if index_entries:
        append_self_collected_index(project_name, index_entries)

    succeeded = sum(1 for r in results if r.filename)
    failed = sum(1 for r in results if r.error)
    logger.info(
        f"[self_collector] 下载完成: total={len(results)}, "
        f"succeeded={succeeded}, failed={failed}"
    )
    return results


async def _collect_with_urllib(
    urls: List[str],
    source_query: str,
    target_dir: Path,
    max_size_mb: int,
    timeout_sec: int,
) -> List[DownloadResult]:
    """无 httpx 时的回退实现（urllib，同步）"""
    import urllib.request
    import urllib.error

    def _blocking_download(url: str) -> DownloadResult:
        result = DownloadResult(
            url=url,
            source_query=source_query,
            downloaded_at=int(time.time() * 1000),
        )
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MathModel-MutiAgent/5.3 (+self-collector)"},
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                result.http_status = resp.getcode()
                ct = resp.headers.get("Content-Type", "")
                result.content_type = ct
                if resp.getcode() >= 400:
                    result.error = f"http_{resp.getcode()}"
                    return result
                ct_base = ct.split(";")[0].strip().lower()
                if ct_base in _REJECT_CONTENT_TYPES:
                    result.error = f"rejected_content_type:{ct_base}"
                    return result
                content = resp.read(max_size_mb * 1024 * 1024 + 1)
                if len(content) > max_size_mb * 1024 * 1024:
                    result.error = f"too_large:{len(content)}"
                    return result
                sha = _sha1_short(content)
                ext = _guess_extension(ct, url)
                filename = f"{sha}{ext}"
                target_path = target_dir / filename
                if not target_path.exists():
                    target_path.write_bytes(content)
                result.filename = filename
                result.size = len(content)
                return result
        except Exception as e:
            result.error = f"exception:{type(e).__name__}:{e}"
            return result

    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _blocking_download, u) for u in urls]
    return await asyncio.gather(*tasks)


def extract_urls_from_search_result(result: Any) -> List[str]:
    """从 search_fn 返回结果中抽取 URL 列表（兼容 dict / list）。"""
    urls: List[str] = []
    if isinstance(result, dict):
        urls.extend(result.get("urls", []) or [])
        urls.extend(result.get("datasets", []) or [])
        for paper in result.get("papers", []) or []:
            if isinstance(paper, dict):
                u = paper.get("url") or paper.get("pdf_url")
                if u:
                    urls.append(u)
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                u = item.get("url") or item.get("pdf_url")
                if u:
                    urls.append(u)
            elif isinstance(item, str):
                urls.append(item)
    elif isinstance(result, str):
        urls.append(result)
    # 过滤空值
    return [u for u in urls if u and isinstance(u, str)]