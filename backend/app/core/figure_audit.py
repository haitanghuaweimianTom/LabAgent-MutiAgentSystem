"""插图审计：去重 / 代码-caption 核对 / 引用完整性 / VLM 视觉校准。

在 writer 产出 LaTeX 后执行，检测并自动修补三类常见问题：
1. 插图重复 —— 同一图片文件（按内容哈希）被多个 figure 环境引用
2. caption 与绘图代码不一致 —— 从 {figure_id}_code.py AST 提取 plt.title /
   ax.set_xlabel / ax.set_ylabel 等调用，与 LaTeX \\caption{} 文本比对
3. 引用缺失 —— \\label{fig:xxx} 在正文中无对应 \\ref / \\cref

有视觉模型时额外执行 VLM 视觉校准：将图片 + caption 发给 LLM 检查内容一致性。
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_FIGURE_BLOCK_RE = re.compile(r"\\begin\{figure\*?\}(?s:.*?)\\end\{figure\*?\}")
_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_CAPTION_RE = re.compile(r"\\caption(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}")
_REF_RE = re.compile(r"\\(?:c?ref)\{([^}]+)\}")


def _file_hash(path: Path) -> str:
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()


def _stem(p: str) -> str:
    try:
        return Path(p or "").stem
    except Exception:
        return p or ""


class _CodeLabelExtractor(ast.NodeVisitor):
    """从绘图代码 AST 提取 plt.title / ax.set_title / ax.set_xlabel / ax.set_ylabel 调用的字符串参数。"""

    LABEL_METHODS = {"title", "set_title", "set_xlabel", "set_ylabel", "suptitle"}

    def __init__(self):
        self.labels: List[str] = []

    def visit_Call(self, node: ast.Call):
        func_name = ""
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id

        if func_name in self.LABEL_METHODS:
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    self.labels.append(arg.value.strip())
                elif isinstance(arg, ast.JoinedStr):
                    parts = []
                    for val in arg.values:
                        if isinstance(val, ast.Constant) and isinstance(val.value, str):
                            parts.append(val.value)
                    if parts:
                        self.labels.append("".join(parts).strip())
        self.generic_visit(node)


def _extract_code_labels(code_path: Path) -> List[str]:
    try:
        tree = ast.parse(code_path.read_text(encoding="utf-8"))
        visitor = _CodeLabelExtractor()
        visitor.visit(tree)
        return visitor.labels
    except Exception:
        return []


def _cjk_bigrams(text: str) -> set:
    cjk = re.findall(r"[一-鿿]", text)
    return {cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)}


def _text_similarity(a: str, b: str) -> float:
    ba, bb = _cjk_bigrams(a), _cjk_bigrams(b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def _find_code_file(figure_stem: str, search_dirs: List[Path]) -> Optional[Path]:
    for d in search_dirs:
        candidate = d / f"{figure_stem}_code.py"
        if candidate.exists():
            return candidate
    return None


async def _vlm_review_figure(
    figure_path: Path,
    caption: str,
    llm_call,
) -> Optional[Dict[str, Any]]:
    import base64

    try:
        raw = figure_path.read_bytes()
        if len(raw) > 1_500_000:
            return None
        b64 = base64.b64encode(raw).decode("ascii")
        mime = "image/png" if figure_path.suffix.lower() == ".png" else "image/jpeg"
        prompt = (
            "你是科研图表审稿人。请检查图像内容与 caption 是否一致（图中数据/标题/坐标轴"
            "是否与 caption 描述吻合），给出 1-5 分与问题列表。只输出 JSON："
            '{"score":1-5,"issues":[],"needs_regen":true|false}\n'
            f"Caption: {caption[:500]}"
        )
        messages = [
            {"role": "system", "content": "You are a scientific figure reviewer."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            },
        ]
        resp = await llm_call(messages)
        text = resp if isinstance(resp, str) else ""
        if isinstance(resp, dict):
            choices = resp.get("choices") or []
            if choices:
                text = choices[0].get("message", {}).get("content", "")
        match = re.search(r"\{[\s\S]*\}", text or "")
        if not match:
            return None
        data = json.loads(match.group(0))
        return {
            "score": float(data.get("score", 3)),
            "issues": list(data.get("issues") or []),
            "needs_regen": bool(data.get("needs_regen", False)),
        }
    except Exception as exc:
        logger.debug(f"[figure_audit] VLM review failed: {exc}")
        return None


def audit_figures(
    latex_code: str,
    figures: List[Dict[str, Any]],
    output_dir: Path,
    *,
    code_search_dirs: Optional[List[Path]] = None,
    vlm_llm_call=None,
) -> Tuple[List[Dict[str, Any]], str]:
    """审计插图，返回 (issues, patched_latex)。

    Args:
        latex_code: writer 产出的完整 LaTeX 源码
        figures: figure_agent 返回的 figures 列表（含 figure_id / figure_path / code）
        output_dir: 项目输出目录（含 charts/ 子目录）
        code_search_dirs: 查找 {figure_id}_code.py 的目录列表（默认 [output_dir/charts, output_dir]）
        vlm_llm_call: 已废弃，VLM 校准请用 async vlm_review_figures（同步函数内无法 await）
    """
    issues: List[Dict[str, Any]] = []
    patched_latex = latex_code

    if not latex_code:
        return issues, patched_latex

    output_dir = Path(output_dir)
    search_dirs = code_search_dirs or [
        output_dir / "charts",
        output_dir,
    ]

    # --- 1. 解析所有 figure 块 ---
    blocks: List[Dict[str, Any]] = []
    for bi, m in enumerate(_FIGURE_BLOCK_RE.finditer(latex_code)):
        block = m.group(0)
        ig = _INCLUDEGRAPHICS_RE.search(block)
        lb = _LABEL_RE.search(block)
        cap_m = _CAPTION_RE.search(block)
        blocks.append({
            "index": bi,
            "start": m.start(),
            "end": m.end(),
            "text": block,
            "img_path": ig.group(1).strip() if ig else "",
            "img_stem": _stem(ig.group(1)) if ig else "",
            "label": lb.group(1).strip() if lb else "",
            "caption": cap_m.group(1).strip() if cap_m else "",
        })

    if not blocks:
        return issues, patched_latex

    # --- 2. 去重：按图片文件内容哈希检测重复 ---
    hash_map: Dict[str, int] = {}  # hash -> first block index
    duplicates: List[int] = []

    for b in blocks:
        img_name = b["img_path"]
        if not img_name:
            continue
        # 尝试在磁盘上找到图片文件
        img_file: Optional[Path] = None
        for d in [output_dir / "charts", output_dir, output_dir.parent]:
            candidate = d / Path(img_name).name
            if candidate.exists():
                img_file = candidate
                break
        if img_file and img_file.exists():
            try:
                fh = _file_hash(img_file)
            except Exception:
                continue
            if fh in hash_map:
                duplicates.append(b["index"])
                issues.append({
                    "severity": "error",
                    "category": "duplicate_figure",
                    "figure_id": b.get("label") or b["img_stem"],
                    "message": f"插图重复：与图 {hash_map[fh] + 1} 使用同一图片文件（哈希 {fh[:8]}）",
                    "suggestion": "删除重复的 figure 块，或为该图生成不同内容的图表",
                })
            else:
                hash_map[fh] = b["index"]
        else:
            # 同路径重复也标记（文件不存在但路径相同）
            for prev in blocks[:b["index"]]:
                if prev["img_path"] and prev["img_path"] == b["img_path"]:
                    duplicates.append(b["index"])
                    issues.append({
                        "severity": "error",
                        "category": "duplicate_figure",
                        "figure_id": b.get("label") or b["img_stem"],
                        "message": f"插图重复：与图 {prev['index'] + 1} 引用相同路径 {img_name}",
                        "suggestion": "删除重复 figure 块或更换图片",
                    })
                    break

    # 自动去重：删除重复的 figure 块（保留第一个）
    if duplicates:
        dup_set = set(duplicates)
        parts: List[str] = []
        last_pos = 0
        for b in blocks:
            parts.append(latex_code[last_pos:b["start"]])
            if b["index"] not in dup_set:
                parts.append(b["text"])
            last_pos = b["end"]
        parts.append(latex_code[last_pos:])
        patched_latex = "".join(parts)
        logger.info(f"[figure_audit] auto-removed {len(duplicates)} duplicate figure block(s)")

    # --- 3. 代码-caption 核对：从绘图代码提取 title/labels 对比 caption ---
    agent_code_map: Dict[str, str] = {}
    for fig in figures:
        if not isinstance(fig, dict):
            continue
        key = fig.get("figure_id") or _stem(fig.get("figure_path", ""))
        if key and fig.get("code"):
            agent_code_map[key] = fig["code"]

    for b in blocks:
        if b["index"] in duplicates:
            continue
        stem = b["img_stem"]
        if not stem:
            continue
        # 优先从 agent 返回的 code 字段取，否则从磁盘 {stem}_code.py 取
        code_text = agent_code_map.get(stem) or agent_code_map.get(b.get("label", ""))
        code_labels: List[str] = []
        if code_text:
            try:
                tree = ast.parse(code_text)
                visitor = _CodeLabelExtractor()
                visitor.visit(tree)
                code_labels = visitor.labels
            except Exception:
                pass
        if not code_labels:
            code_file = _find_code_file(stem, search_dirs)
            if code_file:
                code_labels = _extract_code_labels(code_file)

        if not code_labels:
            continue

        caption = b["caption"]
        if not caption:
            continue

        # 将代码 labels 拼成参考文本，与 caption 比相似度
        ref_text = " ".join(code_labels)
        sim = _text_similarity(caption, ref_text)
        # 也检查 caption 是否包含代码中的关键标签词
        code_keywords = [w for w in code_labels if len(w) >= 2]
        caption_lower = caption.lower()
        keyword_hits = sum(1 for kw in code_keywords if kw.lower() in caption_lower)

        if sim < 0.03 and keyword_hits == 0 and len(code_labels) >= 1:
            issues.append({
                "severity": "warning",
                "category": "caption_code_mismatch",
                "figure_id": b.get("label") or stem,
                "message": (
                    f"caption 与绘图代码不一致：代码中标题/轴标签为 "
                    f"{'; '.join(code_labels[:3])}，caption 为「{caption[:60]}」"
                ),
                "suggestion": "根据绘图代码中的实际标题和坐标轴标签修正 caption",
            })

    # --- 4. 引用完整性：每个 \label{fig:xxx} 须有对应 \ref ---
    ref_keys: set = set()
    for rm in _REF_RE.finditer(latex_code):
        for k in rm.group(1).split(","):
            ref_keys.add(k.strip())

    for b in blocks:
        if b["index"] in duplicates:
            continue
        label = b["label"]
        if not label:
            issues.append({
                "severity": "warning",
                "category": "missing_label",
                "figure_id": b["img_stem"] or f"block_{b['index']}",
                "message": "figure 块缺少 \\label，正文无法引用",
                "suggestion": "添加 \\label{fig:xxx}",
            })
            continue
        if label not in ref_keys:
            issues.append({
                "severity": "warning",
                "category": "unreferenced_figure",
                "figure_id": label,
                "message": f"图表 \\label{{{label}}} 在正文中无对应 \\ref 引用",
                "suggestion": "在正文中添加 \\ref{{{label}}} 或 \\cref{{{label}}} 引用该图",
            })

    # --- 5. caption 文字去重：两张图 caption 高度雷同视为错用/复用 ---
    # 归一化 caption：去掉 Figure/图 N: 前缀和标点，仅比较实质内容
    def _norm_caption(s: str) -> str:
        s = re.sub(r"^(图|Figure|Fig\.?)\s*\d+\s*[:：\.\-—]?", "", s, flags=re.IGNORECASE)
        return re.sub(r"[\s\W_]+", "", s.lower())

    norm_caps: List[Tuple[int, str, str]] = []  # (block_index, normalized, original)
    for b in blocks:
        if b["index"] in duplicates or not b["caption"]:
            continue
        norm_caps.append((b["index"], _norm_caption(b["caption"]), b["caption"]))

    for i in range(len(norm_caps)):
        for j in range(i + 1, len(norm_caps)):
            bi, ni, ci = norm_caps[i]
            bj, nj, cj = norm_caps[j]
            if not ni or not nj:
                continue
            # 完全相同或高度相似
            sim = _text_similarity(ni, nj)
            if ni == nj or sim > 0.8:
                issues.append({
                    "severity": "error",
                    "category": "duplicate_caption",
                    "figure_id": f"fig{bi + 1}/fig{bj + 1}",
                    "message": (
                        f"图表标题文字重复/错用：图{bi + 1} 与图{bj + 1} 的 caption 高度雷同"
                        f"（相似度 {sim:.0%}）。「{ci[:50]}」vs「{cj[:50]}」"
                    ),
                    "suggestion": "为每张图表撰写独立的、准确反映其内容的 caption，禁止复用或错用",
                })

    return issues, patched_latex


async def vlm_review_figures(
    latex_code: str,
    figures: List[Dict[str, Any]],
    output_dir: Path,
    llm_call,
) -> List[Dict[str, Any]]:
    """VLM 视觉校准：将图片 + caption 发给视觉模型检查内容一致性。

    需在 async 上下文中 await 调用。llm_call 须为 async (messages) -> str|dict，
    且底层模型须支持 image_url 多模态输入。
    """
    if not latex_code or not llm_call:
        return []

    output_dir = Path(output_dir)
    blocks: List[Dict[str, Any]] = []
    for bi, m in enumerate(_FIGURE_BLOCK_RE.finditer(latex_code)):
        block = m.group(0)
        ig = _INCLUDEGRAPHICS_RE.search(block)
        cap_m = _CAPTION_RE.search(block)
        lb = _LABEL_RE.search(block)
        blocks.append({
            "index": bi,
            "img_path": ig.group(1).strip() if ig else "",
            "img_stem": _stem(ig.group(1)) if ig else "",
            "label": lb.group(1).strip() if lb else "",
            "caption": cap_m.group(1).strip() if cap_m else "",
        })

    vlm_issues: List[Dict[str, Any]] = []
    for b in blocks:
        img_name = b["img_path"]
        if not img_name:
            continue
        img_file: Optional[Path] = None
        for d in [output_dir / "charts", output_dir, output_dir.parent]:
            candidate = d / Path(img_name).name
            if candidate.exists():
                img_file = candidate
                break
        if not img_file:
            continue
        result = await _vlm_review_figure(img_file, b["caption"], llm_call)
        if result and result.get("needs_regen"):
            vlm_issues.append({
                "severity": "warning",
                "category": "vlm_content_mismatch",
                "figure_id": b["label"] or b["img_stem"],
                "message": f"VLM 视觉校准：{'; '.join(result.get('issues', [])[:3])}",
                "suggestion": "根据 VLM 反馈重新生成或修改图表",
            })
    return vlm_issues
