#!/usr/bin/env python3
"""Batch test all 12 templates end-to-end.

Usage:
    python scripts/test_all_templates.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# ==================== 12 模板的样本问题 ====================

TEMPLATES = {
    "math_modeling": {
        "problem": "某物流公司在 5 个仓库和 20 个客户之间建立配送路径,每辆车最大载重 1000kg,客户需求 50-200kg,要求总运输成本最小。",
        "language": "zh",
    },
    "coursework": {
        "problem": "Design and implement a simple web crawler that fetches product prices from an e-commerce site, stores them in SQLite, and computes weekly price trends. Evaluate accuracy against ground truth.",
        "language": "en",
    },
    "neurips_2024": {
        "problem": "We propose a sparse attention mechanism for long-context transformers that reduces memory from O(n^2) to O(n log n) while preserving accuracy on language modeling. Provide theoretical analysis and empirical results on WikiText-103.",
        "language": "en",
    },
    "iclr_2024": {
        "problem": "We propose a graph contrastive learning method that combines local and global views through a novel mutual information estimator. Evaluate on OGB benchmarks (ogbg-molhiv, ogbn-arxiv).",
        "language": "en",
    },
    "icml_2024": {
        "problem": "We propose a causal bandit algorithm that handles unobserved confounders through instrumental variable regression. Prove regret bound O(sqrt(T) log T) and evaluate on synthetic + semi-synthetic data.",
        "language": "en",
    },
    "aaai_2024": {
        "problem": "We propose a multi-agent reinforcement learning approach for warehouse robot coordination with dynamic task arrival. Evaluate on RWARE benchmark.",
        "language": "en",
    },
    "acm_sigconf": {
        "problem": "We present a database query optimizer that learns from execution traces via offline reinforcement learning. Implement in PostgreSQL and evaluate on TPC-H.",
        "language": "en",
    },
    "ieee_conference": {
        "problem": "We propose a real-time speech enhancement system using a lightweight convolutional recurrent network, deployed on edge devices. Evaluate on DNS Challenge dataset.",
        "language": "en",
    },
    "springer_lncs": {
        "problem": "We propose a knowledge graph embedding method that incorporates temporal information through hyper-relational facts. Evaluate on ICEWS dataset.",
        "language": "en",
    },
    "research_survey": {
        "problem": "A comprehensive survey on the integration of large language models with symbolic reasoning systems, covering 80+ papers from 2020-2026.",
        "language": "en",
    },
    "financial_analysis": {
        "problem": "构建中国 A 股 2024 年沪深 300 成分股动量因子模型,分析 12 个月动量与反转效应的统计显著性,给出因子收益率曲线。",
        "language": "zh",
    },
    "presentation": {
        "problem": "Present the above logistics vehicle routing research in 12 slides for an academic conference talk, with clear visualizations and speaker notes.",
        "language": "en",
    },
}


async def run_one(template_id: str, problem: str, output_dir: Path) -> dict:
    """Run a single template pipeline. Return stats dict."""
    from scripts.generate_paper import run_pipeline  # type: ignore

    project_name = f"test_{template_id}_2026"
    start = time.time()
    try:
        artifact = await run_pipeline(
            template_id=template_id,
            problem=problem,
            project_name=project_name,
            output_dir=output_dir,
        )
        elapsed = time.time() - start
        paper_md = artifact.folder / "paper.md"
        code_py = artifact.folder / "code" / "model.py"

        paper_lines = 0
        if paper_md.exists():
            paper_lines = sum(1 for _ in open(paper_md, encoding="utf-8"))
        code_lines = 0
        if code_py.exists():
            code_lines = sum(1 for _ in open(code_py, encoding="utf-8"))

        review_rec = "?"
        try:
            review_rec = artifact.peer_review.get("recommendation", "?")
        except Exception:
            pass
        refs_count = len(artifact.references) if artifact.references else 0
        filtered = artifact.fake_refs_filtered if artifact.fake_refs_filtered is not None else 0

        return {
            "template": template_id,
            "elapsed": round(elapsed, 1),
            "paper_lines": paper_lines,
            "code_lines": code_lines,
            "real_refs": refs_count,
            "filtered": filtered,
            "tokens": artifact.total_tokens_used,
            "review_recommendation": review_rec,
            "success": paper_lines > 50 and code_lines > 20,
        }
    except Exception as e:
        return {
            "template": template_id,
            "elapsed": round(time.time() - start, 1),
            "error": str(e)[:200],
            "success": False,
        }


async def main():
    os.environ["MINIMAX_API_KEY"] = os.environ.get(
        "MINIMAX_API_KEY",
        "sk-cp-sxw2xgI88b-tHAo-L-BZtRojvuH0-UlbatdZnyukzPpflQW0_wRCmKIHTbsgUL7ZZ5gB8-xvVD0BG9IZf-cZCATs57gpm7bs-dlIYS0VbOXA4MyFf2AZrSM",
    )
    output_dir = ROOT / "outputs" / "batch_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    print(f"{'='*80}")
    print(f"批量验证 12 模板 — {len(TEMPLATES)} templates")
    print(f"{'='*80}")

    results = []
    for i, (template_id, cfg) in enumerate(TEMPLATES.items()):
        print(f"\n>>> [{i+1}/{len(TEMPLATES)}] {template_id}", flush=True)
        result = await run_one(template_id, cfg["problem"], output_dir)
        results.append(result)
        if result.get("success"):
            print(f"   ✅ paper={result['paper_lines']}行 code={result['code_lines']}行 "
                  f"refs={result['real_refs']} token={result['tokens']} "
                  f"review={result['review_recommendation']} time={result['elapsed']}s", flush=True)
        else:
            print(f"   ❌ {'error: ' + result.get('error', 'unknown') if 'error' in result else 'paper too short'}", flush=True)
        # 模板间延迟 20s，避免 API 限流
        if i < len(TEMPLATES) - 1:
            print(f"   ⏳ 等待 20s 避免限流...", flush=True)
            import asyncio as _asyncio
            await _asyncio.sleep(20)

    # 汇总
    print(f"\n{'='*80}")
    print(f"汇总")
    print(f"{'='*80}")
    success = sum(1 for r in results if r.get("success"))
    fail = len(results) - success
    print(f"成功: {success}/{len(results)}")
    print(f"失败: {fail}/{len(results)}")
    print()
    print(f"{'模板':<20} {'状态':<6} {'paper':<8} {'code':<8} {'refs':<6} {'token':<8} {'review':<12} {'time':<6}")
    print("-" * 90)
    for r in results:
        if r.get("success"):
            print(f"{r['template']:<20} {'✅':<6} {r['paper_lines']:<8} {r['code_lines']:<8} "
                  f"{r['real_refs']:<6} {r['tokens']:<8} {r['review_recommendation']:<12} {r['elapsed']:<6}")
        else:
            err = r.get("error", "FAIL")[:30]
            print(f"{r['template']:<20} {'❌':<6} {'-':<8} {'-':<8} {'-':<6} {'-':<8} {'-':<12} {err:<30}")

    # 保存 JSON 报告
    report_path = output_dir / "batch_report.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细报告: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
