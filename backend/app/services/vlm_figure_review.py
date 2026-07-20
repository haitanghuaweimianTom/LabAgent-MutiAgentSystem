"""VLM 图表审阅闭环 —— 读图检查内容一致性 / 美学，生成修改指令。

无可用视觉模型时，回退到基于文件元数据 + caption/数据一致性的启发式检查。
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _heuristic_figure_review(
    figure_path: Path,
    *,
    caption: str = "",
    data_summary: str = "",
) -> Dict[str, Any]:
    issues: List[str] = []
    suggestions: List[str] = []
    score = 4.0

    if not figure_path.exists():
        return {
            "ok": False,
            "score": 1.0,
            "issues": ["图表文件不存在"],
            "suggestions": ["重新生成图表"],
            "needs_regen": True,
            "method": "heuristic",
        }

    size = figure_path.stat().st_size
    if size < 2000:
        issues.append("文件过小，可能是空图或生成失败")
        suggestions.append("检查绘图代码是否调用 savefig / save_figure")
        score -= 1.5

    if figure_path.suffix.lower() not in {".png", ".pdf", ".svg", ".jpg", ".jpeg"}:
        issues.append(f"非常见发表格式: {figure_path.suffix}")
        suggestions.append("同时导出 PNG+PDF/SVG")
        score -= 0.5

    if caption:
        nums_cap = set(re.findall(r"\d+\.?\d*", caption))
        nums_data = set(re.findall(r"\d+\.?\d*", data_summary or ""))
        if nums_cap and nums_data and not (nums_cap & nums_data):
            issues.append("caption 中的数字与数据摘要无明显交集")
            suggestions.append("根据真实结果文件重写 caption")
            score -= 1.0
        if len(caption) < 15:
            issues.append("caption 过短")
            suggestions.append("补充坐标轴含义与主要发现")
            score -= 0.5
    else:
        issues.append("缺少 caption")
        suggestions.append("为每张图撰写与结果一致的 caption")
        score -= 0.5

    score = max(1.0, min(5.0, score))
    return {
        "ok": score >= 3.5 and not any("不存在" in i for i in issues),
        "score": score,
        "issues": issues,
        "suggestions": suggestions,
        "needs_regen": score < 3.0,
        "edit_instruction": "；".join(suggestions) if suggestions else "",
        "method": "heuristic",
    }


async def review_figure_with_vlm(
    figure_path: str,
    *,
    caption: str = "",
    data_summary: str = "",
    llm_call=None,
    max_bytes: int = 1_500_000,
) -> Dict[str, Any]:
    """尝试 VLM 审图；失败则启发式回退。

    llm_call: async (messages) -> str|dict，可选。若支持多模态，messages 含 image。
    """
    path = Path(figure_path)
    base = _heuristic_figure_review(path, caption=caption, data_summary=data_summary)

    if llm_call is None or not path.exists():
        return base

    try:
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            return {**base, "method": "heuristic", "notes": "image too large for VLM"}

        b64 = base64.b64encode(raw).decode("ascii")
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        prompt = (
            "你是科研图表审稿人。请检查图像内容与 caption/数据是否一致，"
            "并给出 1-5 分与修改建议。只输出 JSON："
            '{"score":1-5,"issues":[],"suggestions":[],"needs_regen":true|false}\n'
            f"Caption: {caption[:500]}\nData: {data_summary[:500]}"
        )
        # 兼容纯文本 LLM：把说明发出去；真多模态由调用方扩展
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
        text = resp
        if isinstance(resp, dict):
            choices = resp.get("choices") or []
            if choices:
                text = choices[0].get("message", {}).get("content", "")
        match = re.search(r"\{[\s\S]*\}", text or "")
        if not match:
            return {**base, "method": "heuristic+vlm_parse_fail"}
        data = json.loads(match.group(0))
        score = float(data.get("score", base["score"]))
        issues = list(data.get("issues") or []) + list(base.get("issues") or [])
        suggestions = list(data.get("suggestions") or []) + list(base.get("suggestions") or [])
        needs = bool(data.get("needs_regen", score < 3.0))
        return {
            "ok": score >= 3.5,
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
            "needs_regen": needs,
            "edit_instruction": "；".join(suggestions),
            "method": "vlm",
        }
    except Exception as exc:
        logger.warning(f"[vlm_figure_review] fallback to heuristic: {exc}")
        return {**base, "notes": str(exc)}


async def review_figures_batch(
    figures: List[Dict[str, Any]],
    *,
    llm_call=None,
    max_rounds: int = 1,
) -> Dict[str, Any]:
    """批量审图。figures: [{path, caption, data_summary, id}]"""
    reviews = []
    need_regen = []
    for fig in figures:
        path = fig.get("path") or fig.get("file") or ""
        result = await review_figure_with_vlm(
            path,
            caption=fig.get("caption", ""),
            data_summary=fig.get("data_summary", ""),
            llm_call=llm_call,
        )
        entry = {"id": fig.get("id", path), "path": path, **result}
        reviews.append(entry)
        if result.get("needs_regen"):
            need_regen.append(entry)

    avg = sum(r.get("score", 0) for r in reviews) / len(reviews) if reviews else 0.0
    return {
        "reviews": reviews,
        "need_regen": need_regen,
        "average_score": round(avg, 2),
        "passed": avg >= 3.5 and not need_regen,
        "max_rounds": max_rounds,
    }
