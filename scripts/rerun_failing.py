#!/usr/bin/env python3
"""Rerun only the 7 failing templates with per-template rate limit delay."""
import asyncio, os, logging, sys, time
from pathlib import Path

os.chdir("/home/tomgame/projects/MathModel-MutiAgentSystem")
os.environ["MINIMAX_API_KEY"] = "sk-cp-sxw2xgI88b-tHAo-L-BZtRojvuH0-UlbatdZnyukzPpflQW0_wRCmKIHTbsgUL7ZZ5gB8-xvVD0BG9IZf-cZCATs57gpm7bs-dlIYS0VbOXA4MyFf2AZrSM"
os.environ["LLM_MAX_CONTEXT_LENGTH"] = "500000"
os.environ["LLM_AUTO_COMPRESS_RATIO"] = "0.9"
sys.path.insert(0, ".")
sys.path.insert(0, "src")

import sys
logging.basicConfig(level=logging.WARNING, format="%(message)s")

from scripts.generate_paper import run_pipeline

FAILING = {
    "acm_sigconf": "We present a database query optimizer that learns from execution traces via offline RL.",
    "icml_2024": "We propose a causal bandit algorithm with O(sqrt(T)) regret bound and instrumental variables.",
    "ieee_conference": "We propose a real-time speech enhancement system using a lightweight convolutional recurrent network.",
    "springer_lncs": "We propose a knowledge graph embedding method incorporating temporal hyper-relational facts.",
    "research_survey": "A comprehensive survey on LLM integration with symbolic reasoning systems.",
    "financial_analysis": "构建中国A股2024年沪深300成分股动量因子模型,分析12个月动量与反转效应。",
    "presentation": "Create a 12-slide conference talk about the logistics vehicle routing research.",
}

async def main():
    out = Path("outputs/batch_test")
    for tid, prob in FAILING.items():
        pn = f"test_{tid}_2026"
        if (out / pn / "paper.md").exists():
            p = sum(1 for _ in open(out / pn / "paper.md"))
            print(f"⏭️  {tid}: already done ({p} lines)")
            continue
        print(f">>> {tid}", flush=True)
        start = time.time()
        try:
            a = await run_pipeline(tid, prob, pn, out)
            p = sum(1 for _ in open(a.folder / "paper.md")) if (a.folder / "paper.md").exists() else 0
            c = sum(1 for _ in open(a.folder / "code" / "model.py")) if (a.folder / "code" / "model.py").exists() else 0
            print(f"   ✅ {tid}: paper={p}行 code={c}行 refs={len(a.references)} token={a.total_tokens_used} time={time.time()-start:.0f}s", flush=True)
        except Exception as e:
            print(f"   ❌ {tid}: {str(e)[:120]}", flush=True)
        await asyncio.sleep(10)

asyncio.run(main())