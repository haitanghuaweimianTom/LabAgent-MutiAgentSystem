"""
AB Benchmark - measure whether self-evolution actually helps.

Inspired by AutoResearchClaw / ARC-Bench's A/B philosophy: run the same set of
problems with evolution enabled and disabled, then compare high-level metrics
(retry rate, quality, tokens).

Two modes:
  - `--mock`: deterministic dry run using the real evolution modules
    (EvolutionStore, LessonV2, update_effectiveness, query_for_stage).
    Zero API cost; proves the mechanism works and exercises the pipeline.
  - `--real`: disabled by default. Would invoke the full generate_paper.py
    pipeline for (3 problems x evolution on/off = 6) real runs.

Metrics (ARC-Bench/ARC inspired):
  - retry_rate: fraction of runs whose stage needed a retry
  - avg_score: mean weighted paper-quality score
  - total_tokens: sum of tokens
  - injected_runs: how many runs had a learned lesson surfaced
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from self_evolution import EvolutionStore, LessonV2

__all__ = [
    "STANDARD_PROBLEMS",
    "compute_metrics",
    "run_mock_benchmark",
    "render_report",
]

STANDARD_PROBLEMS = [
    {
        "template": "math_modeling",
        "problem": "某城市共享单车调度优化（含时间窗约束，需平衡覆盖与周转）",
    },
    {
        "template": "neurips_2024",
        "problem": "Graph neural networks for molecule property prediction (QED/ESOL)",
    },
    {
        "template": "coursework",
        "problem": "基于多元回归的房价分析与预测（含特征工程）",
    },
]

# A synthetic recurring bug shared by every mock problem, so we can show the
# evolution layer learning to avoid it.
_BUG_DESC = "model code 运行超时：在数据规模超过 50 时未设置求解 time_limit"
_BUG_CATEGORY = "system"


def compute_metrics(runs: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate per-run results into benchmark metrics."""
    if not runs:
        return {
            "n_runs": 0, "retry_count": 0, "retry_rate": 0.0,
            "avg_score": 0.0, "total_tokens": 0, "injected_runs": 0,
            "injection_rate": 0.0,
        }
    n = len(runs)
    retries = sum(1 for r in runs if r.get("retry"))
    injected = sum(1 for r in runs if r.get("injected"))
    scores = [float(r.get("score", 0.0)) for r in runs]
    tokens = int(sum(r.get("tokens", 0) for r in runs))
    return {
        "n_runs": n,
        "retry_count": retries,
        "retry_rate": retries / n,
        "avg_score": sum(scores) / n,
        "total_tokens": tokens,
        "injected_runs": injected,
        "injection_rate": injected / n,
    }


def _record_bug(store: EvolutionStore, run_label: str) -> LessonV2:
    lesson = LessonV2(
        stage_name="step3",
        category=_BUG_CATEGORY,
        severity="error",
        description=_BUG_DESC,
        source="rule",
        run_id=run_label,
    )
    store.append(lesson)
    return lesson


def run_mock_benchmark(
    use_evolution: bool,
    n_runs: int = 4,
    root: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Deterministically simulate `n_runs` pipeline runs for one problem.

    A recurring "time-limit" bug fires on every run **unless** the evolution
    store already surfaced a matching lesson to the step (mock injection). With
    evolution on, the first run discovers & records the bug; later runs surface
    the lesson and avoid retrying, improving quality.
    """
    root = Path(root or (Path.cwd() / ".ab_mock")) / f"evo_{int(use_evolution)}"
    store = EvolutionStore(root / "evolution")

    results: list[dict[str, Any]] = []
    for i in range(n_runs):
        # Has a prior lesson been surfaced to the step? -> avoid the bug.
        injected = bool(store.query_for_stage("step3", max_lessons=5))

        if use_evolution and injected:
            retry = 0
            score = 0.9
        else:
            retry = 1
            score = 0.5
            # On the first run on-mode run, record the bug so future runs inject it.
            if use_evolution and store.count() == 0:
                _record_bug(store, f"mock-run-{i}")

        results.append(
            {
                "run": i,
                "retry": retry,
                "score": score,
                "tokens": 1000 + i * 100,
                "injected": injected,
            }
        )
    return results


def render_report(on: dict[str, float], off: dict[str, float]) -> str:
    """Render a markdown comparison of evolution-on vs off metrics."""
    lines = [
        "# A/B Benchmark Report",
        "",
        "| 指标 | evolution ON | evolution OFF |",
        "|------|-------------|---------------|",
        f"| 运行次数 | {on['n_runs']} | {off['n_runs']} |",
        f"| 重试率 | {on['retry_rate']*100:.1f}% | {off['retry_rate']*100:.1f}% |",
        f"| 平均质量分 | {on['avg_score']:.2f} | {off['avg_score']:.2f} |",
        f"| 总 token | {on['total_tokens']} | {off['total_tokens']} |",
        f"| 教训注入率 | {on['injection_rate']*100:.1f}% | {off['injection_rate']*100:.1f}% |",
        "",
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')} (mock 干跑，无 API 成本)",
    ]
    return "\n".join(lines)

def main() -> None:
    """CLI entry point. Default: mock dry-run (zero API cost)."""
    import argparse
    import sys
    from pathlib import Path as _P

    parser = argparse.ArgumentParser(description="自进化 A/B 对比")
    parser.add_argument("--mock", action="store_true", help="mock 干跑（默认，零 API）")
    parser.add_argument("--real", action="store_true", help="真实 A/B（需 API，暂未接入 run_pipeline）")
    parser.add_argument("--n-runs", type=int, default=4, help="mock 每档运行次数")
    parser.add_argument("--output", type=_P, default=_P("ab_report.md"), help="报告输出路径")
    args = parser.parse_args()

    if args.real:
        print("--real 未实现：请手动触发 generate_paper.py 的 run_pipeline（3 问题 × on/off）。")
        print("当前仅支持 --mock 干跑。")
        sys.exit(1)

    on = compute_metrics(run_mock_benchmark(use_evolution=True, n_runs=args.n_runs))
    off = compute_metrics(run_mock_benchmark(use_evolution=False, n_runs=args.n_runs))
    report = render_report(on, off)
    args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
