"""知识整理器 — 将任务下载资源自动分类并注册到全局知识库

流程：scan → categorize → organize → index
- scan_task_downloads: 扫描 {task_dir}/downloads/ 和 {task_dir}/ 发现资源
- categorize_resource: 基于规则（文件名、扩展名）分类资源类型/领域/方法/质量
- organize_resources: 复制到全局知识库目录结构并注册到 knowledge_manager
- generate_index: 生成 JSON 索引
- run_full_organization: 端到端流水线
"""
import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ===== 分类枚举 =====

RESOURCE_TYPES = ("paper", "dataset", "code", "benchmark", "survey")
DOMAINS = ("NLP", "CV", "RL", "optimization", "time_series", "math_modeling", "other")
METHODS = (
    "transformer", "CNN", "GNN", "reinforcement_learning",
    "linear_programming", "statistical", "other",
)
QUALITY_LEVELS = ("top_venue", "good", "average", "unknown")

# ===== 扩展名到默认类型的映射 =====

_EXT_TYPE_MAP: Dict[str, str] = {
    ".pdf": "paper",
    ".bib": "paper",
    ".csv": "dataset",
    ".json": "dataset",
    ".xlsx": "dataset",
    ".xls": "dataset",
    ".parquet": "dataset",
    ".py": "code",
    ".ipynb": "code",
    ".tex": "paper",
    ".txt": "dataset",
    ".tsv": "dataset",
}

# 支持扫描的扩展名
_SCANNABLE_EXTENSIONS = set(_EXT_TYPE_MAP.keys())

# ===== 领域关键词 =====

_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "NLP": ["nlp", "natural language", "text", "language model", "bert", "gpt", "llm",
             "token", "sentiment", "translation", "summarization", "ner", "question answering"],
    "CV": ["cv", "computer vision", "image", "object detection", "segmentation",
            "yolo", "resnet", "cnn", "convolution", "visual", "face", "pose"],
    "RL": ["reinforcement", "rl", "reward", "policy", "q-learning", "actor-critic",
            "dqn", "ppo", "a3c", "bandit", "exploration", "exploitation"],
    "optimization": ["optimization", "optimal", "linear programming", "integer programming",
                      "quadratic", "convex", "gradient descent", "solver", "minimize", "maximize"],
    "time_series": ["time series", "forecast", "arima", "lstm", "temporal",
                     "sequential", "autocorrelation", "seasonal", "trend"],
    "math_modeling": ["modeling", "mathematical model", "simulation", "differential equation",
                       "stochastic", "probability", "statistics", "bayesian", "regression"],
}

# ===== 方法关键词 =====

_METHOD_KEYWORDS: Dict[str, List[str]] = {
    "transformer": ["transformer", "attention", "self-attention", "bert", "gpt", "t5",
                     "vit", "deit", "swin", "pretrain", "fine-tune"],
    "CNN": ["cnn", "convolutional", "convolution", "pooling", "resnet", "vgg", "inception",
             "efficientnet", "mobilenet"],
    "GNN": ["gnn", "graph neural", "graph convolution", "gcn", "gat", "graphsage",
             "message passing", "node embedding"],
    "reinforcement_learning": ["reinforcement", "policy gradient", "q-learning", "dqn",
                                "ppo", "a3c", "sac", "td3", "reward shaping"],
    "linear_programming": ["linear program", "integer program", "mixed integer", "simplex",
                           "branch and cut", "lp relaxation"],
    "statistical": ["statistical", "hypothesis test", "regression", "anova", "chi-square",
                     "bootstrap", "bayesian", "mcmc", "monte carlo"],
}

# ===== 顶级会议/期刊关键词 =====

_TOP_VENUE_KEYWORDS = [
    "neurips", "nips", "icml", "iclr", "aaai", "ijcai",
    "cvpr", "iccv", "eccv", "acl", "emnlp", "naacl",
    "sigir", "www", "kdd", "icde", "vldb", "sigmod",
    "nature", "science", "jmlr", "tpami", "tmlr",
]


def scan_task_downloads(task_dir: str) -> List[Dict[str, Any]]:
    """扫描 task_dir/downloads/ 和 task_dir/ 发现资源文件。

    Returns:
        [{"path": str, "filename": str, "ext": str, "size": int}, ...]
    """
    task_path = Path(task_dir)
    if not task_path.is_dir():
        logger.warning(f"[knowledge_organizer] task_dir 不存在: {task_dir}")
        return []

    resources: List[Dict[str, Any]] = []
    scanned_paths: set = set()

    # 扫描目录列表：downloads/ 子目录 + task 根目录
    scan_dirs: List[Path] = []
    downloads_dir = task_path / "downloads"
    if downloads_dir.is_dir():
        scan_dirs.append(downloads_dir)
    scan_dirs.append(task_path)

    for scan_dir in scan_dirs:
        for fpath in scan_dir.iterdir():
            if fpath.name.startswith(".") or fpath.name.startswith("_"):
                continue
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in _SCANNABLE_EXTENSIONS:
                continue
            real_path = fpath.resolve()
            if real_path in scanned_paths:
                continue
            scanned_paths.add(real_path)
            resources.append({
                "path": str(fpath),
                "filename": fpath.name,
                "ext": fpath.suffix.lower(),
                "size": fpath.stat().st_size,
            })

    logger.info(f"[knowledge_organizer] 扫描完成: {len(resources)} 个资源")
    return resources


def categorize_resource(
    resource_path: str,
    content_preview: str = "",
) -> Dict[str, Any]:
    """基于规则分类一个资源。

    Args:
        resource_path: 资源文件路径
        content_preview: 可选的内容预览文本（用于关键词匹配）

    Returns:
        {"type": str, "domain": str, "method": str, "quality": str}
    """
    path = Path(resource_path)
    ext = path.suffix.lower()
    name_lower = path.name.lower()

    # 合并文件名 + 内容预览用于关键词匹配
    text = f"{name_lower} {content_preview}".lower()

    # --- type ---
    res_type = _EXT_TYPE_MAP.get(ext, "other")
    # survey 检查
    if "survey" in text or "review" in text:
        res_type = "survey"
    # benchmark 检查
    if "benchmark" in text:
        res_type = "benchmark"

    # --- domain ---
    domain = "other"
    domain_scores: Dict[str, int] = {}
    for d, keywords in _DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            domain_scores[d] = score
    if domain_scores:
        domain = max(domain_scores, key=domain_scores.get)

    # --- method ---
    method = "other"
    method_scores: Dict[str, int] = {}
    for m, keywords in _METHOD_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            method_scores[m] = score
    if method_scores:
        method = max(method_scores, key=method_scores.get)

    # --- quality ---
    quality = "unknown"
    for venue in _TOP_VENUE_KEYWORDS:
        if venue in text:
            quality = "top_venue"
            break
    if quality == "unknown" and res_type in ("paper", "survey"):
        quality = "average"

    return {
        "type": res_type,
        "domain": domain,
        "method": method,
        "quality": quality,
    }


def organize_resources(
    task_id: str,
    resources: List[Dict[str, Any]],
    knowledge_manager: Any,
    base_id: str = "global",
) -> List[Dict[str, Any]]:
    """将资源复制到全局知识库目录并注册。

    目录结构：
        data/knowledge_bases/global/
            papers/{domain}/{year}/
            datasets/{domain}/{name}/
            code/{method}/

    Args:
        task_id: 任务标识
        resources: scan_task_downloads 返回的资源列表（需含 category 字段）
        knowledge_manager: KnowledgeManager 实例
        base_id: 注册到哪个知识库

    Returns:
        组织结果列表，含新路径和注册状态
    """
    kb_base = Path(__file__).parent.parent.parent.parent / "data" / "knowledge_bases" / "global"
    results: List[Dict[str, Any]] = []

    for res in resources:
        src_path = Path(res["path"])
        category = res.get("category", {})
        res_type = category.get("type", "other")
        domain = category.get("domain", "other")
        method = category.get("method", "other")

        # 确定目标子目录
        if res_type in ("paper", "survey"):
            year = _extract_year(src_path.name)
            dest_dir = kb_base / "papers" / domain / year
        elif res_type in ("dataset", "benchmark"):
            stem = src_path.stem[:30]
            dest_dir = kb_base / "datasets" / domain / stem
        elif res_type == "code":
            dest_dir = kb_base / "code" / method
        else:
            dest_dir = kb_base / "other"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / src_path.name

        # 去重：同名文件已存在则跳过复制
        copied = False
        if not dest_path.exists():
            try:
                shutil.copy2(str(src_path), str(dest_path))
                copied = True
            except Exception as e:
                logger.warning(
                    f"[knowledge_organizer] 复制失败 {src_path.name}: {e}"
                )
                results.append({
                    "filename": src_path.name,
                    "dest": str(dest_path),
                    "copied": False,
                    "registered": False,
                    "error": str(e),
                })
                continue

        # 注册到 knowledge_manager
        registered = False
        reg_error = ""
        try:
            item_id = knowledge_manager.add_item(
                base_id,
                _make_knowledge_item(
                    dest_path,
                    task_id,
                    category,
                ),
            )
            registered = True
            logger.info(f"[knowledge_organizer] 注册成功: {src_path.name} -> {item_id}")
        except Exception as e:
            reg_error = str(e)
            logger.warning(f"[knowledge_organizer] 注册失败 {src_path.name}: {e}")

        results.append({
            "filename": src_path.name,
            "dest": str(dest_path),
            "copied": copied,
            "registered": registered,
            "error": reg_error or None,
            "item_id": item_id if registered else None,
        })

    return results


def generate_index(task_id: str, organized_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """生成 JSON 索引，汇总任务的所有已组织资源。"""
    index = {
        "task_id": task_id,
        "generated_at": int(time.time() * 1000),
        "total": len(organized_results),
        "registered": sum(1 for r in organized_results if r.get("registered")),
        "failed": sum(1 for r in organized_results if r.get("error")),
        "resources": organized_results,
    }
    return index


def run_full_organization(
    task_id: str,
    task_dir: str,
    knowledge_manager: Any,
    base_id: str = "global",
) -> Dict[str, Any]:
    """端到端流水线：scan → categorize → organize → index。

    Returns:
        {"index": dict, "organized": list, "errors": list}
    """
    logger.info(f"[knowledge_organizer] 开始整理 task={task_id}, dir={task_dir}")
    errors: List[str] = []

    # 1. 扫描
    resources = scan_task_downloads(task_dir)
    if not resources:
        logger.info(f"[knowledge_organizer] 无资源可整理: {task_id}")
        return {"index": generate_index(task_id, []), "organized": [], "errors": []}

    # 2. 分类
    for res in resources:
        try:
            preview = _read_preview(res["path"])
            res["category"] = categorize_resource(res["path"], preview)
        except Exception as e:
            res["category"] = {
                "type": "other", "domain": "other",
                "method": "other", "quality": "unknown",
            }
            errors.append(f"categorize {res['filename']}: {e}")

    # 3. 组织 + 注册
    organized = organize_resources(task_id, resources, knowledge_manager, base_id)

    # 4. 生成索引
    index = generate_index(task_id, organized)

    registered = sum(1 for r in organized if r.get("registered"))
    logger.info(
        f"[knowledge_organizer] 整理完成: total={len(resources)}, "
        f"registered={registered}, errors={len(errors)}"
    )

    return {"index": index, "organized": organized, "errors": errors}


# ===== 内部辅助 =====


def _read_preview(file_path: str, max_bytes: int = 4096) -> str:
    """读取文件开头作为预览文本（用于关键词匹配）。"""
    path = Path(file_path)
    if not path.exists():
        return ""
    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".csv", ".json", ".bib", ".tex", ".py"):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(max_bytes)
        # PDF 等二进制文件跳过预览
        return ""
    except Exception:
        return ""


def _extract_year(filename: str) -> str:
    """从文件名中提取年份，找不到则返回 'unknown'。"""
    matches = re.findall(r"(20[12]\d)", filename)
    if matches:
        return matches[0]
    return "unknown"


def _make_knowledge_item(
    file_path: Path,
    task_id: str,
    category: Dict[str, str],
) -> Any:
    """构建 KnowledgeItem 实例用于注册。"""
    from ..core.knowledge_manager import FileMetadata, KnowledgeItem

    stat = file_path.stat()
    item_id = f"ko_{task_id}_{file_path.stem}"

    return KnowledgeItem(
        id=item_id,
        type="file",
        content=FileMetadata(
            name=file_path.name,
            size=stat.st_size,
            ext=file_path.suffix,
            path=str(file_path),
        ),
        source=f"task:{task_id}",
        metadata={
            "domain": category.get("domain", "other"),
            "method": category.get("method", "other"),
            "quality": category.get("quality", "unknown"),
            "resource_type": category.get("type", "other"),
            "organized_at": int(time.time() * 1000),
        },
    )
