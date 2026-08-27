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

import httpx
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


def _normalize_url(url: str) -> str:
    """标准化 URL：arXiv /abs/ → /pdf/"""
    import re
    # arXiv: /abs/NNNN.NNNNN → /pdf/NNNN.NNNNN
    m = re.match(r'(https?://arxiv\.org/abs/)(\d+\.\d+(?:v\d+)?)', url)
    if m:
        return f"https://arxiv.org/pdf/{m.group(2)}.pdf"
    return url

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


def _apply_response(
    resp: Any,
    result: DownloadResult,
    url: str,
    max_size_mb: int,
    target_dir: Path,
) -> None:
    """把 httpx 响应写入 result（状态/类型校验/去重落盘）。直连与代理回退共用。"""
    result.http_status = resp.status_code
    ct = resp.headers.get("content-type", "")
    result.content_type = ct
    if resp.status_code >= 400:
        result.error = f"http_{resp.status_code}"
        return
    # Content-Type 拒绝列表
    ct_base = ct.split(";")[0].strip().lower()
    if ct_base in _REJECT_CONTENT_TYPES:
        result.error = f"rejected_content_type:{ct_base}"
        return
    # 读取内容（带大小保护）
    max_bytes = max_size_mb * 1024 * 1024
    content = resp.content
    if len(content) > max_bytes:
        result.error = f"too_large:{len(content)}"
        return
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


async def _fetch_one(
    client: Any,
    sem: asyncio.Semaphore,
    url: str,
    source_query: str,
    target_dir: Path,
    max_size_mb: int,
    timeout_sec: int,
    proxied_client: Any = None,
) -> DownloadResult:
    """下载单个 URL，带去重 + 大小限制 + Content-Type 校验。

    直连连接级失败时，若有 proxied_client 则走代理重试（智能回退）。
    """
    url = _normalize_url(url)
    started = time.time()
    result = DownloadResult(
        url=url,
        source_query=source_query,
        downloaded_at=int(time.time() * 1000),
    )
    try:
        async with sem:
            resp = await client.get(url, timeout=timeout_sec)
        _apply_response(resp, result, url, max_size_mb, target_dir)
        result.elapsed_ms = int((time.time() - started) * 1000)
        return result
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as e:
        if proxied_client is None:
            result.error = f"exception:{type(e).__name__}:{e}"
            result.elapsed_ms = int((time.time() - started) * 1000)
            return result
        # 直连连接级失败 → 代理回退
        try:
            async with sem:
                resp = await proxied_client.get(url, timeout=timeout_sec)
            _apply_response(resp, result, url, max_size_mb, target_dir)
        except Exception:
            result.error = f"exception:{type(e).__name__}:{e}"
        result.elapsed_ms = int((time.time() - started) * 1000)
        return result
    except asyncio.TimeoutError:
        result.error = "timeout"
        result.elapsed_ms = int((time.time() - started) * 1000)
        return result
    except Exception as e:
        result.error = f"exception:{type(e).__name__}:{e}"
        result.elapsed_ms = int((time.time() - started) * 1000)
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
            client_kwargs = dict(
                timeout=httpx.Timeout(timeout_sec, connect=8.0, pool=5.0),
                follow_redirects=True,
                headers={"User-Agent": "MathModel-MutiAgent/5.3 (+self-collector)"},
            )
            from ..core.proxy import detect_system_proxy
            _px = detect_system_proxy()
            async with httpx.AsyncClient(**client_kwargs) as client:
                # 代理回退客户端：直连连接级失败时按 URL 逐个走代理
                proxied = (
                    httpx.AsyncClient(**client_kwargs, proxy=_px) if _px else None
                )
                try:
                    tasks = [
                        _fetch_one(client, sem, u, source_query, target_dir,
                                   max_size_mb, timeout_sec, proxied_client=proxied)
                        for u in urls
                    ]
                    return await asyncio.gather(*tasks)
                finally:
                    if proxied is not None:
                        await proxied.aclose()
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


# ──────────────────────────────────────────────────────────────────────
# 金融行情数据采集（akshare，新浪源为主，免 API key）
# 通用网页搜索几乎搜不到可直接下载的 A 股 CSV 直链（多为需 JS 渲染的行情页），
# 故对金融选题用 akshare 直接拉真实历史行情。符合 [[no-local-binding-policy]]：
# akshare 是纯 SDK 调用，不绑定特定机器。
# ──────────────────────────────────────────────────────────────────────

# 常见指数关键词 → akshare 新浪源代码（stock_zh_index_daily）
# v8.4.6: 扩充关键词覆盖（原仅 13 条，遗漏常见叫法如"大盘"、"沪深三百"等）。
_INDEX_KEYWORDS: List[tuple] = [
    ("沪深300", "sh000300"), ("沪深300指数", "sh000300"), ("csi300", "sh000300"),
    ("沪深三百", "sh000300"), ("hs300", "sh000300"),
    ("上证指数", "sh000001"), ("上证综指", "sh000001"), ("上证综合", "sh000001"),
    ("上证综", "sh000001"), ("大盘", "sh000001"), ("沪指", "sh000001"),
    ("深证成指", "sz399001"), ("深证成份", "sz399001"), ("深成指", "sz399001"),
    ("中证500", "sh000905"), ("中证500指数", "sh000905"), ("中证五百", "sh000905"),
    ("csi500", "sh000905"),
    ("创业板指", "sz399006"), ("创业板指数", "sz399006"), ("创业板", "sz399006"),
    ("科创50", "sh000688"), ("科创板", "sh000688"),
    ("上证50", "sh000016"), ("上证50指数", "sh000016"), ("sse50", "sh000016"),
    ("中证1000", "sh000852"), ("中证1000指数", "sh000852"),
    ("恒生指数", "hkHSI"), ("恒指", "hkHSI"), ("hang seng", "hkHSI"),
    ("道琼斯", "usDJI"), ("道指", "usDJI"), ("dow jones", "usDJI"),
    ("标普500", "usSPX"), ("标普500指数", "usSPX"), ("s&p500", "usSPX"), ("spx", "usSPX"),
    ("纳斯达克", "usIXIC"), ("纳指", "usIXIC"), ("nasdaq", "usIXIC"),
    ("日经225", "usN225"), ("日经指数", "usN225"), ("nikkei", "usN225"),
    ("富时a50", "usFTSEA50"), ("ftse a50", "usFTSEA50"),
]


def _detect_financial_symbols(problem_text: str) -> List[Dict[str, str]]:
    """从题目文本识别要采集的指数/标的。

    返回 [{"code": "sh000300", "name": "沪深300", "kind": "index"}, ...]。
    指数用 stock_zh_index_daily（新浪源，稳定）。

    v8.4.6: 新增个股检测——题目中出现 6 位数字股票代码（如 600519 贵州茅台）时，
    用 ak.stock_zh_a_hist 采集（东财源，可能限流，采集失败不影响指数采集结果）。
    沪市 6/9 开头、深市 0/3 开头、北交所 8/4 开头。
    """
    if not problem_text:
        return []
    text = problem_text
    hits: List[Dict[str, str]] = []
    seen = set()
    for kw, code in _INDEX_KEYWORDS:
        if kw.lower() in text.lower() and code not in seen:
            hits.append({"code": code, "name": kw, "kind": "index"})
            seen.add(code)

    # v8.4.6: 个股代码检测（6 位数字，沪 6/9、深 0/3、北 8/4 开头）
    import re as _re
    for m in _re.finditer(r"(?<![0-9])([69][0-9]{5}|[03][0-9]{5}|[84][0-9]{5})(?![0-9])", text):
        stock_code = m.group(1)
        if stock_code in seen:
            continue
        seen.add(stock_code)
        hits.append({"code": stock_code, "name": stock_code, "kind": "stock"})

    return hits


async def collect_financial_data(
    problem_text: str,
    project_name: Optional[str],
    source_query: str = "",
) -> Tuple[List[DownloadResult], List[str]]:
    """对金融选题，用 akshare 拉真实历史行情落盘。

    返回 (results, file_rel_paths)：results 供日志，file_rel_paths 供 data_files 使用。
    无 akshare / 无识别标的 / 拉取失败时返回 ([], [])，不抛异常（交由上层兜底）。
    """
    symbols = _detect_financial_symbols(problem_text)
    if not symbols:
        logger.info("[self_collector] 金融采集：题目未识别到已知指数标的，跳过")
        return ([], [])

    try:
        import akshare as ak
    except ImportError:
        logger.warning("[self_collector] akshare 未安装，金融数据采集跳过")
        return ([], [])

    target_dir = get_project_data_subdir(project_name, "self_collected")
    results: List[DownloadResult] = []
    rel_paths: List[str] = []
    from datetime import datetime, timezone

    for sym in symbols:
        code, name = sym["code"], sym["name"]
        kind = sym.get("kind", "index")
        # v8.4.6: 个股用 stock_zh_a_hist（东财源），指数用 stock_zh_index_daily（新浪源）
        ak_func_name = "stock_zh_a_hist" if kind == "stock" else "stock_zh_index_daily"
        res = DownloadResult(
            url=f"akshare://{ak_func_name}/{code}",
            source_query=source_query or f"金融行情:{name}",
            downloaded_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        try:
            import asyncio
            # akshare 是同步库，放 executor 避免阻塞事件循环
            loop = asyncio.get_event_loop()
            if kind == "stock":
                # 个股：东财源 stock_zh_a_hist，需指定 period + 日期范围
                from datetime import datetime as _dt, timedelta as _td
                _end = _dt.now()
                _start = _end - _td(days=365 * 5)  # 近 5 年日线
                df = await loop.run_in_executor(
                    None,
                    lambda c=code, s=_start, e=_end: ak.stock_zh_a_hist(
                        symbol=c, period="daily",
                        start_date=s.strftime("%Y%m%d"),
                        end_date=e.strftime("%Y%m%d"),
                        adjust="qfq",  # 前复权，回测常用
                    ),
                )
            else:
                df = await loop.run_in_executor(
                    None,
                    lambda c=code: ak.stock_zh_index_daily(symbol=c),
                )
            if df is None or len(df) == 0:
                res.error = "empty_dataframe"
                results.append(res)
                continue

            # 落 CSV（akshare 返回 date 为 datetime.date，统一转字符串）
            csv_path = target_dir / f"{code}_{name}_daily.csv"
            df_to_save = df.copy()
            if "date" in df_to_save.columns:
                df_to_save["date"] = df_to_save["date"].astype(str)
            df_to_save.to_csv(csv_path, index=False, encoding="utf-8")

            res.filename = csv_path.name
            res.size = csv_path.stat().st_size
            res.content_type = "text/csv"
            res.http_status = 200
            results.append(res)

            from ..core.paths import _PROJECT_ROOT
            try:
                rel = str(csv_path.relative_to(_PROJECT_ROOT))
            except ValueError:
                rel = str(csv_path)
            rel_paths.append(rel)
            logger.info(
                f"[self_collector] 金融采集成功：{name}({code}) → {csv_path.name} "
                f"({len(df)} 行, {res.size}B)"
            )
        except Exception as e:
            res.error = f"exception:{type(e).__name__}:{e}"
            results.append(res)
            logger.warning(f"[self_collector] 金融采集失败 {name}({code}): {e}")

    # 写 _index.json
    if results:
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
        append_self_collected_index(project_name, index_entries)

    ok = sum(1 for r in results if r.filename)
    logger.info(f"[self_collector] 金融采集完成: {ok}/{len(results)} 成功")
    return (results, rel_paths)


# ──────────────────────────────────────────────────────────────────────
# 通用数据集采集：内置直链表 + GitHub Code Search + Kaggle
# 覆盖非金融模板（CCF-A 论文、ML、课程作业等）的数据搜集需求。
# 金融选题走 collect_financial_data（akshare），此处是通用补充。
# ──────────────────────────────────────────────────────────────────────

# 内置常用数据集直链表（免 key，按关键词命中即下载）
# 优先 GitHub raw（稳定直链），其次 UCI ML Repository
_DATASET_CATALOG: List[Dict[str, str]] = [
    # 经典 ML 数据集
    {"name": "iris", "keywords": "iris 鸢尾花 分类", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv"},
    {"name": "titanic", "keywords": "titanic 泰坦尼克 乘客 生还", "url": "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv"},
    {"name": "tips", "keywords": "tips 小费 餐厅 回归", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv"},
    {"name": "planets", "keywords": "planet 行星 系外", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/planets.csv"},
    {"name": "diamonds", "keywords": "diamond 钻石 价格 回归", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/diamonds.csv"},
    {"name": "mpg", "keywords": "mpg 汽车 油耗 燃料", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/mpg.csv"},
    {"name": "penguins", "keywords": "penguin 企鹅 分类", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/penguins.csv"},
    {"name": "brain", "keywords": "brain 脑 容量 智商", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/brain.csv"},
    {"name": "anscombe", "keywords": "anscombe 安斯库姆", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/anscombe.csv"},
    {"name": "exercise", "keywords": "exercise 运动 心率", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/exercise.csv"},
    {"name": "geyser", "keywords": "geyser 间歇泉 老忠实", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/geyser.csv"},
    {"name": "uci_iris", "keywords": "uci iris 鸢尾", "url": "https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data"},
    {"name": "boston_housing", "keywords": "boston housing 房价 波士顿 回归", "url": "https://raw.githubusercontent.com/selva86/datasets/master/BostonHousing.csv"},
    {"name": "car_crashes", "keywords": "crash 车祸 交通事故 伤亡", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/car_crashes.csv"},
    {"name": "seaice", "keywords": "sea ice 海冰 气候 时序", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/seaice.csv"},
    {"name": "flights", "keywords": "flight 航班 乘客 时序", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/flights.csv"},
    {"name": "dots", "keywords": "dot 点 反应 时间", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/dots.csv"},
    {"name": "dowjones", "keywords": "dow jones 道琼斯 股票", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/dowjones.csv"},
    {"name": "taxis", "keywords": "taxi 出租 车 纽约", "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/taxis.csv"},
]


def _match_catalog(problem_text: str) -> List[Dict[str, str]]:
    """从题目文本匹配内置数据集直链表（中英文关键词）。"""
    if not problem_text:
        return []
    text = problem_text.lower()
    hits: List[Dict[str, str]] = []
    seen = set()
    for ds in _DATASET_CATALOG:
        kws = ds["keywords"].lower().split()
        if any(kw in text for kw in kws if len(kw) > 2) and ds["name"] not in seen:
            hits.append(ds)
            seen.add(ds["name"])
    return hits


async def collect_catalog_datasets(
    problem_text: str,
    project_name: Optional[str],
    source_query: str = "",
) -> Tuple[List[DownloadResult], List[str]]:
    """内置数据集直链表采集（免 key，按题目关键词匹配下载）。

    第一道采集：快速可靠，零幻觉。命中即用 GitHub raw / UCI 直链下载。
    """
    hits = _match_catalog(problem_text)
    if not hits:
        logger.info("[self_collector] 内置数据集表：题目未命中已知数据集，跳过")
        return ([], [])

    urls = [h["url"] for h in hits]
    logger.info(f"[self_collector] 内置表命中 {len(hits)} 个数据集: {[h['name'] for h in hits]}")
    results = await collect_urls(
        urls,
        project_name=project_name,
        source_query=source_query or "内置数据集表",
        concurrency=4,
        timeout_sec=30,
        max_size_mb=50,
    )
    # GitHub raw 命中的文件名是 sha 哈希，重命名为可读名
    rel_paths: List[str] = []
    target_dir = get_project_data_subdir(project_name, "self_collected")
    from ..core.paths import _PROJECT_ROOT
    for ds, dr in zip(hits, results):
        if dr.filename:
            src = target_dir / dr.filename
            new_name = f"catalog_{ds['name']}.csv"
            dst = target_dir / new_name
            try:
                if src.exists() and src != dst:
                    src.rename(dst)
                    dr.filename = new_name
            except Exception:
                pass
            try:
                rel = str(dst.relative_to(_PROJECT_ROOT))
            except ValueError:
                rel = str(dst)
            rel_paths.append(rel)
    ok = sum(1 for r in results if r.filename)
    logger.info(f"[self_collector] 内置表采集完成: {ok}/{len(results)} 成功")
    return (results, rel_paths)


def _extract_search_keywords(problem_text: str, max_kws: int = 3) -> List[str]:
    """从题目文本提炼数据集搜索关键词（英文优先，中文按 2 字片段）。

    数据集名多为英文，故英文词优先；中文正则贪婪匹配会把整句当一个 token，
    故按 2 字滑窗切成短词，再过滤无意义虚词。
    """
    if not problem_text:
        return []
    import re
    # 英文词（≥3 字母），数据集名首选
    en_words = re.findall(r"[a-zA-Z]{3,}", problem_text)
    # 中文按 2-4 字滑窗：先按标点/空格分段，再取每段前 2-3 字
    cn_segments = re.split(r"[，。、；：,;.\s（）()【】\[\]\"'""''《》<>!?！？\n]+", problem_text)
    cn_words: List[str] = []
    for seg in cn_segments:
        seg = seg.strip()
        if 2 <= len(seg) <= 4 and re.fullmatch(r"[一-鿿]+", seg):
            cn_words.append(seg)
    stop = {"the", "and", "for", "with", "from", "that", "this", "are", "was",
            "基于", "分析", "研究", "问题", "数据", "模型", "构建", "评估", "预测",
            "对比", "比较", "效果", "影响", "构建", "通过", "进行", "基于", "利用",
            "数据集", "题目", "本文", "本文", "使用"}
    kws: List[str] = []
    for w in en_words + cn_words:
        wl = w.lower()
        if wl in stop or len(wl) < 2:
            continue
        if w not in kws:
            kws.append(w)
    return kws[:max_kws]


async def collect_github_datasets(
    problem_text: str,
    project_name: Optional[str],
    source_query: str = "",
    max_files: int = 5,
) -> Tuple[List[DownloadResult], List[str]]:
    """GitHub Code Search 采集：搜 *.csv 文件，下 raw 直链。

    需配置 GitHub token（匿名仅 60 次/小时且 code search 需认证）。无 token 时降级跳过。
    """
    from ..core.datasource_config import get_datasource_key
    keys = get_datasource_key("github")
    token = (keys or {}).get("token", "")
    if not token:
        logger.info("[self_collector] GitHub 采集：未配置 token，跳过（code search 需认证）")
        return ([], [])

    kws = _extract_search_keywords(problem_text, max_kws=3)
    if not kws:
        return ([], [])
    query = " ".join(kws) + " extension:csv"
    logger.info(f"[self_collector] GitHub code search: {query[:60]}")

    from ..core.proxy import smart_get
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    raw_urls: List[str] = []
    try:
        resp = await smart_get(
            "https://api.github.com/search/code",
            params={"q": query, "per_page": max_files},
            headers=headers,
            timeout=15.0,
        )
        if resp.status_code != 200:
            logger.warning(f"[self_collector] GitHub code search HTTP {resp.status_code}: {resp.text[:200]}")
            return ([], [])
        items = resp.json().get("items", [])
        for it in items:
            html_url = it.get("html_url", "")  # https://github.com/{owner}/{repo}/blob/{ref}/{path}
            # 转 raw URL
            if "github.com" in html_url and "/blob/" in html_url:
                raw = html_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/", 1)
                raw_urls.append(raw)
    except Exception as e:
        logger.warning(f"[self_collector] GitHub code search 失败: {e}")
        return ([], [])

    if not raw_urls:
        logger.info("[self_collector] GitHub code search 无结果")
        return ([], [])

    results = await collect_urls(
        raw_urls,
        project_name=project_name,
        source_query=source_query or "github_code_search",
        concurrency=3,
        timeout_sec=30,
        max_size_mb=20,
    )
    rel_paths: List[str] = []
    from ..core.paths import _PROJECT_ROOT
    target_dir = get_project_data_subdir(project_name, "self_collected")
    for dr in results:
        if dr.filename:
            try:
                rel = str((target_dir / dr.filename).relative_to(_PROJECT_ROOT))
            except ValueError:
                rel = str(target_dir / dr.filename)
            rel_paths.append(rel)
    ok = sum(1 for r in results if r.filename)
    logger.info(f"[self_collector] GitHub 采集完成: {ok}/{len(results)} 成功")
    return (results, rel_paths)


async def collect_kaggle_datasets(
    problem_text: str,
    project_name: Optional[str],
    source_query: str = "",
    max_files: int = 3,
) -> Tuple[List[DownloadResult], List[str]]:
    """Kaggle 数据集采集：按关键词搜 + 下载（需 username+key 认证）。

    无 key 或 kaggle SDK 缺失时跳过。下载的文件解压后取 CSV。
    """
    from ..core.datasource_config import get_datasource_key
    keys = get_datasource_key("kaggle")
    if not keys or not keys.get("username") or not keys.get("key"):
        logger.info("[self_collector] Kaggle 采集：未配置 key，跳过")
        return ([], [])
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError:
        logger.warning("[self_collector] kaggle SDK 未安装，Kaggle 采集跳过")
        return ([], [])

    # 提炼搜索关键词
    kws = _extract_search_keywords(problem_text, max_kws=2)
    if not kws:
        return ([], [])
    search = " ".join(kws)
    logger.info(f"[self_collector] Kaggle 搜索: {search[:60]}")

    import os
    kaggle_dir = os.path.expanduser("~/.kaggle")
    os.makedirs(kaggle_dir, exist_ok=True)
    cred_path = os.path.join(kaggle_dir, "kaggle.json")
    target_dir = get_project_data_subdir(project_name, "self_collected")
    target_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    results: List[DownloadResult] = []
    rel_paths: List[str] = []

    from ..core.proxy import maybe_set_proxy_env_for
    _restore_proxy = await maybe_set_proxy_env_for("www.kaggle.com")
    try:
        import json
        with open(cred_path, "w") as f:
            json.dump({"username": keys["username"], "key": keys["key"]}, f)
        os.chmod(cred_path, 0o600)

        api = KaggleApi()
        api.authenticate()
        # dataset_list 按搜索词
        ds_list = api.dataset_list(search=search, page_size=max_files)
        downloaded = 0
        for ds in ds_list[:max_files]:
            ref = getattr(ds, "ref", "")  # owner/dataset-slug
            if not ref:
                continue
            res = DownloadResult(
                url=f"kaggle://{ref}",
                source_query=source_query or "kaggle",
                downloaded_at=int(datetime.now(timezone.utc).timestamp() * 1000),
            )
            try:
                # 下载到临时目录再筛 CSV
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    api.dataset_download_files(ref, path=tmp, unzip=True, quiet=True)
                    # 收集所有 csv
                    csvs = list(Path(tmp).rglob("*.csv"))
                    if not csvs:
                        res.error = "no_csv_in_dataset"
                        results.append(res)
                        continue
                    # 取最大的 CSV（避免小元数据文件）
                    csvs.sort(key=lambda p: p.stat().st_size, reverse=True)
                    for csv_file in csvs[:2]:
                        sha = _sha1_short(csv_file.read_bytes())
                        dst = target_dir / f"kaggle_{sha}.csv"
                        if not dst.exists():
                            import shutil
                            shutil.copy2(csv_file, dst)
                        res.filename = dst.name
                        res.size = dst.stat().st_size
                        res.content_type = "text/csv"
                        res.http_status = 200
                        results.append(res)
                        from ..core.paths import _PROJECT_ROOT
                        try:
                            rel = str(dst.relative_to(_PROJECT_ROOT))
                        except ValueError:
                            rel = str(dst)
                        rel_paths.append(rel)
                        downloaded += 1
                        break
            except Exception as e:
                res.error = f"exception:{type(e).__name__}:{e}"
                results.append(res)
        logger.info(f"[self_collector] Kaggle 采集完成: {downloaded} 个数据集")
    except Exception as e:
        logger.warning(f"[self_collector] Kaggle 采集失败: {e}")
    finally:
        try:
            os.remove(cred_path)
        except Exception:
            pass
        if _restore_proxy:
            _restore_proxy()

    return (results, rel_paths)


async def collect_huggingface_datasets(
    problem_text: str,
    project_name: Optional[str],
    source_query: str = "",
    max_files: int = 3,
) -> Tuple[List[DownloadResult], List[str]]:
    """HuggingFace 数据集采集（走 hf-mirror.com 镜像）。

    官方 huggingface.co 在国内常被 DNS 污染/墙，hf-mirror.com 镜像可直连。
    流程：datasets 搜索 API → tree API 找 csv/parquet 文件 → resolve 下载。
    有 token 时带认证（可下受限数据集），无 token 也能下公开数据集。
    """
    from ..core.datasource_config import get_datasource_key
    from ..core.proxy import smart_get
    token = (get_datasource_key("huggingface") or {}).get("token", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    base = "https://hf-mirror.com"

    # 提炼搜索关键词
    kws = _extract_search_keywords(problem_text, max_kws=2)
    if not kws:
        return ([], [])
    search = " ".join(kws)
    logger.info(f"[self_collector] HuggingFace 搜索(镜像): {search[:60]}")

    target_dir = get_project_data_subdir(project_name, "self_collected")
    target_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    from ..core.paths import _PROJECT_ROOT
    results: List[DownloadResult] = []
    rel_paths: List[str] = []

    try:
        # 1. 搜索数据集（smart_get：直连优先，失败回退代理）
        resp = await smart_get(
            f"{base}/api/datasets",
            params={"search": search, "limit": max_files * 2},
            headers=headers,
            timeout=20.0,
        )
        if resp.status_code != 200:
            logger.warning(f"[self_collector] HF 搜索 HTTP {resp.status_code}")
            return ([], [])
        ds_list = resp.json()
        downloaded = 0
        for ds in ds_list[:max_files * 2]:
            did = ds.get("id")
            if not did:
                continue
            # 2. 列文件树，找 csv
            try:
                tree_resp = await smart_get(
                    f"{base}/api/datasets/{did}/tree/main",
                    headers=headers, timeout=20.0,
                )
                tree = tree_resp.json()
                files = tree if isinstance(tree, list) else []
                csv_paths = [f.get("path") for f in files
                             if (f.get("path") or "").endswith(".csv")]
                if not csv_paths:
                    continue
                # 取第一个 CSV 下载
                path = csv_paths[0]
                res = DownloadResult(
                    url=f"hf-mirror://{did}/{path}",
                    source_query=source_query or "huggingface",
                    downloaded_at=int(datetime.now(timezone.utc).timestamp() * 1000),
                )
                dl_resp = await smart_get(
                    f"{base}/datasets/{did}/resolve/main/{path}",
                    headers=headers, timeout=30.0,
                )
                if dl_resp.status_code != 200 or not dl_resp.content:
                    res.error = f"http_{dl_resp.status_code}"
                    results.append(res)
                    continue
                sha = _sha1_short(dl_resp.content)
                dst = target_dir / f"hf_{sha}.csv"
                if not dst.exists():
                    dst.write_bytes(dl_resp.content)
                res.filename = dst.name
                res.size = dst.stat().st_size
                res.content_type = "text/csv"
                res.http_status = 200
                results.append(res)
                try:
                    rel = str(dst.relative_to(_PROJECT_ROOT))
                except ValueError:
                    rel = str(dst)
                rel_paths.append(rel)
                downloaded += 1
                if downloaded >= max_files:
                    break
            except Exception as e:
                logger.debug(f"[self_collector] HF 数据集 {did} 处理失败: {e}")
                continue
        logger.info(f"[self_collector] HuggingFace 采集完成: {downloaded} 个数据集")
    except Exception as e:
        logger.warning(f"[self_collector] HuggingFace 采集失败: {e}")

    return (results, rel_paths)


async def collect_datasets_multi(
    problem_text: str,
    project_name: Optional[str],
    source_query: str = "",
) -> Tuple[List[DownloadResult], List[str]]:
    """多路通用数据集采集（内置表 → GitHub → Kaggle），命中即返回。

    金融选题的指数行情走 collect_financial_data，本函数处理通用数据集。
    各路独立 try，任一成功即纳入 data_files。
    """
    all_rel: List[str] = []
    all_results: List[DownloadResult] = []

    # 第一路：内置数据集直链表（免 key，最快最可靠）
    try:
        r1, p1 = await collect_catalog_datasets(problem_text, project_name, source_query)
        all_results.extend(r1)
        all_rel.extend(p1)
    except Exception as e:
        logger.warning(f"[self_collector] 内置表采集异常: {e}")

    # 第二路：GitHub Code Search（需 token）
    if not all_rel:
        try:
            r2, p2 = await collect_github_datasets(problem_text, project_name, source_query)
            all_results.extend(r2)
            all_rel.extend(p2)
        except Exception as e:
            logger.warning(f"[self_collector] GitHub 采集异常: {e}")

    # 第三路：Kaggle（需 key）
    if not all_rel:
        try:
            r3, p3 = await collect_kaggle_datasets(problem_text, project_name, source_query)
            all_results.extend(r3)
            all_rel.extend(p3)
        except Exception as e:
            logger.warning(f"[self_collector] Kaggle 采集异常: {e}")

    # 第四路：HuggingFace（走 hf-mirror.com 镜像，免 token 可下公开数据集）
    if not all_rel:
        try:
            r4, p4 = await collect_huggingface_datasets(problem_text, project_name, source_query)
            all_results.extend(r4)
            all_rel.extend(p4)
        except Exception as e:
            logger.warning(f"[self_collector] HuggingFace 采集异常: {e}")

    # 第五路：GitHub 仓库/开源代码（repo tarball，免 token 可下公开仓库）
    # 涉及 baseline 开源代码、评测脚本、工程实现的选题走此路。
    if not all_rel:
        try:
            r5, p5 = await collect_github_repos(
                problem_text=problem_text,
                project_name=project_name,
                source_query=source_query or "github_repos",
            )
            all_results.extend(r5)
            all_rel.extend(p5)
        except Exception as e:
            logger.warning(f"[self_collector] GitHub 仓库采集异常: {e}")

    return (all_results, all_rel)


# ──────────────────────────────────────────────────────────────────────
# GitHub 仓库/开源代码抓取（搜索引擎 + codeload tarball）
# 覆盖"baseline 开源实现 / 评测脚本 / 工程代码"的采集需求（EMNLP/CCF-A 常用）。
# 与 collect_github_datasets 的区别：后者搜的是具体 *.csv **文件**，
# 本能力抓的是整个 **仓库源码树**（tarball），供 agent 解压后读取 baseline/脚本。
# ──────────────────────────────────────────────────────────────────────

# GitHub 仓库搜索：扩展名/仓库名字段中找 matching repos。按 star 降序取 top。
def _repo_from_url(url: str) -> Optional[str]:
    """把 github URL 规整为 owner/repo 形式；非 github.com 域名返回 None。"""
    if not url:
        return None
    # 去掉 query/fragment
    base = url.split("?", 1)[0].split("#", 1)[0]
    # 只接受 github.com 域名（含子路径）
    import re as _re2
    m = _re2.match(r"https?://(?:www\.)?github\.com/", base)
    if not m:
        return None
    parts = base[m.end():].strip("/").split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    # owner/repo 只允许字母数字和 -_（排除 /tree/ /blob/ 等路径误捕获）
    if not owner or not repo or not _re2.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        return None
    return f"{owner}/{repo}"


async def collect_github_repos(
    problem_text: str,
    project_name: Optional[str],
    source_query: str = "",
    repo_hints: Optional[List[str]] = None,
    max_repos: int = 3,
) -> Tuple[List[DownloadResult], List[str]]:
    """GitHub 仓库源码抓取：搜索/直接指定 repo → codeload tarball 下载。

    与 collect_github_datasets（只搜 *.csv 文件）互补——本函数抓**整仓库源码**，
    用于"获取 baseline 开源实现 / 评测脚本 / 基准代码"。匿名也可下公开 repos。

    Args:
        problem_text: 题目文本（提炼搜索关键词）
        project_name: 项目名
        source_query: 来源意图
        repo_hints: 显式指定的 owner/repo 列表（优先），非空则不再搜索
        max_repos: 抓取仓库数上限

    Returns:
        (results, rel_paths)：rel_paths 是 tarball 相对路径（agent 需解包）
    """
    from ..core.datasource_config import get_datasource_key
    from ..core.proxy import smart_get
    token = (get_datasource_key("github") or {}).get("token", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    target_dir = get_project_data_subdir(project_name, "self_collected")
    target_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    from ..core.paths import _PROJECT_ROOT
    results: List[DownloadResult] = []
    rel_paths: List[str] = []

    repos: List[str] = []
    if repo_hints:
        for r in repo_hints:
            rr = r if "/" in r else None
            # 也接受裸 URL/裸名字解析
            if r.startswith("http"):
                rr = _repo_from_url(r) or rr
            if rr and rr not in repos:
                repos.append(rr)
    elif problem_text:
        # 从题目提炼关键词 → GitHub repo search
        kws = _extract_search_keywords(problem_text, max_kws=3)
        query = " ".join(kws) if kws else problem_text[:60]
        logger.info(f"[self_collector] GitHub repo search: {query[:60]}")
        try:
            def _norm(r: str) -> Optional[str]:
                return _repo_from_url(r) if "http" in r else (r if "/" in r else None)
            resp = await smart_get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": max_repos * 3},
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code == 200:
                for it in resp.json().get("items", [])[:max_repos]:
                    full = it.get("full_name")
                    if full and full not in repos:
                        repos.append(full)
            else:
                logger.warning(f"[self_collector] GitHub repo search HTTP {resp.status_code}")
                # 匿名限流时 fallback：用内置的已知 benchmark 仓库？——不，避免硬编码，直接空
        except Exception as e:
            logger.warning(f"[self_collector] GitHub repo search 异常: {e}")

    if not repos:
        logger.info("[self_collector] GitHub 仓库：无候选 repo，跳过")
        return ([], [])

    for repo in repos[:max_repos]:
        res = DownloadResult(
            url=f"github://{repo}",
            source_query=source_query or f"repo:{repo}",
            downloaded_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        try:
            # codeload tarball（免 token，稳定直链）
            dl = await smart_get(
                f"https://codeload.github.com/{repo}/tar.gz/HEAD",
                headers=headers, timeout=60.0,
            )
            if dl.status_code != 200 or not dl.content:
                res.error = f"http_{dl.status_code}"
                results.append(res)
                continue
            safe_name = repo.replace("/", "__")
            dst = target_dir / f"repo_{safe_name}.tar.gz"
            if not dst.exists():
                dst.write_bytes(dl.content)
            res.filename = dst.name
            res.size = dst.stat().st_size
            res.content_type = "application/gzip"
            res.http_status = 200
            results.append(res)
            try:
                rel = str(dst.relative_to(_PROJECT_ROOT))
            except ValueError:
                rel = str(dst)
            rel_paths.append(rel)
            logger.info(f"[self_collector] 仓库抓取成功 {repo} → {dst.name} ({res.size}B)")
        except Exception as e:
            res.error = f"exception:{type(e).__name__}:{e}"
            results.append(res)
            logger.warning(f"[self_collector] 仓库抓取失败 {repo}: {e}")

    if results:
        index_entries = []
        for r in results:
            meta = SelfCollectedMeta(
                url=r.url, filename=r.filename, size=r.size,
                downloaded_at=r.downloaded_at, content_type=r.content_type,
                source_query=r.source_query, http_status=r.http_status, error=r.error,
            )
            index_entries.append(meta.to_dict())
        append_self_collected_index(project_name, index_entries)

    ok = sum(1 for r in results if r.filename)
    logger.info(f"[self_collector] GitHub 仓库采集完成: {ok}/{len(results)} 成功")
    return (results, rel_paths)

