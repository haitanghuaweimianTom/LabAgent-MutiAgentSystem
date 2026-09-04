"""
Issue Signature - Problem deduplication signatures.

Inspired by Sibyl's issue_key mechanism. Two descriptions that express the
same underlying problem (possibly with different wording, iteration numbers,
or numeric parameters) must map to the same signature so the evolution store
doesn't fill with near-duplicate lessons.

Signature format: "{category}:{preview}:{hash}" where hash = sha1[:12].
"""

from __future__ import annotations

import hashlib
import re

# Categories supported by the self-evolution system (8 = Sibyl's + our domain).
ALLOWED_CATEGORIES = {
    "system",
    "experiment",
    "writing",
    "analysis",
    "literature",
    "pipeline",
    "ideation",
    "planning",
    "efficiency",
}

# Map surface forms (Chinese and English) to a canonical token.
ISSUE_SYNONYMS: dict[str, str] = {
    # Chinese -> canonical
    "运行超时": "timeout",
    "超时": "timeout",
    "超": "timeout",
    "timeout": "timeout",
    "time limit": "timeout",
    # 引用 / 参考文献
    "引用": "citation",
    "引文": "citation",
    "参考文献": "citation",
    "citation": "citation",
    "reference": "citation",
    # 过拟合
    "过拟合": "overfitting",
    "overfit": "overfitting",
    "overfitting": "overfitting",
    # 语法错误
    "语法错误": "syntax-error",
    "syntax error": "syntax-error",
    "parse error": "syntax-error",
    # NaN / 除零
    "除零": "nan-inf",
    "divided by zero": "nan-inf",
    "division by zero": "nan-inf",
    "nan": "nan-inf",
    "inf": "nan-inf",
    "无穷": "nan-inf",
    # 乱码 / 编码
    "乱码": "encoding",
    "编码": "encoding",
    "encoding": "encoding",
    "garbled": "encoding",
    # 超页
    "超页": "overpage",
    "页数超限": "overpage",
    "超出页数": "overpage",
    "overpage": "overpage",
    "page limit": "overpage",
    # 缺图
    "缺图": "missing-figure",
    "图缺失": "missing-figure",
    "未生成图表": "missing-figure",
    "missing figure": "missing-figure",
    # 不收敛
    "不收敛": "convergence",
    "收敛失败": "convergence",
    "convergence failure": "convergence",
    # 虚假引用
    "虚假引用": "hallucinated-ref",
    "编造文献": "hallucinated-ref",
    "fake reference": "hallucinated-ref",
    "hallucinated": "hallucinated-ref",
    # 消融
    "消融": "ablation",
    "ablation": "ablation",
    # 过拟合重现 / over
}

# The set of canonical token values (targets of the synonym table).
CANONICAL_TOKENS = set(ISSUE_SYNONYMS.values())


def normalize_synonyms(text: str) -> str:
    """Replace known synonyms with canonical tokens (case-insensitive)."""
    lower = (text or "").lower()
    for phrase, canonical in sorted(ISSUE_SYNONYMS.items(), key=lambda kv: -len(kv[0])):
        lower = lower.replace(phrase, canonical)
    return lower


# Pattern for numbers with optional units (handles "30min", "75%", "n=5", "60 秒")
_NUM_UNIT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|min|h|%|秒|分钟|小时|字节|个|次|轮)?\b")
_ITER_RE = re.compile(r"iteration\s*\d+\b|第\s*\d+\s*轮|\biteration\s+\d+|迭代\s*\d+")
_PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fa5 ]+")
_WS_RE = re.compile(r"\s+")


def _has_token(text: str, token: str) -> bool:
    """Word-boundary token presence check, tolerant of hyphenated canonical tokens."""
    return re.search(rf"(?<![A-Za-z0-9-]){re.escape(token)}(?![A-Za-z0-9-])", text) is not None


def normalize_text(text: str) -> str:
    """Full normalization: lower → synonyms → strip nums/iterations → strip punct → sort tokens."""
    if not text:
        return ""
    t = normalize_synonyms(text)
    t = _ITER_RE.sub("", t)
    t = _NUM_UNIT_RE.sub(" ", t)
    t = _PUNCT_RE.sub(" ", t)
    tokens = [tok for tok in _WS_RE.split(t) if tok]
    tokens.sort()
    return " ".join(tokens)


def build_issue_key(description: str, category: str) -> str:
    """Build a stable issue key for a description under a category.

    Strategy: dedup on shared domain vocabulary (canonical tokens present in
    the description). If no canonical tokens fire, fall back to the full
    normalized text fingerprint so genuinely different problems stay distinct.

    Signature: "{category}:{preview}:{hash}" with hash = sha1[:12].
    """
    cat = category if category in ALLOWED_CATEGORIES else "pipeline"
    normalized = normalize_text(description)
    if not normalized:
        normalized = "unknown"

    hits = sorted(c for c in CANONICAL_TOKENS if _has_token(normalized, c))
    content_for_hash = " ".join(hits) if hits else normalized
    preview = content_for_hash[:24]
    digest = hashlib.sha1(content_for_hash.encode("utf-8")).hexdigest()[:12]
    return f"{cat}:{preview}:{digest}"