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


def render_report(
    on: dict[str, float],
    off: dict[str, float],
    mode: str = "mock 干跑，无 API 成本",
) -> str:
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
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')} ({mode})",
    ]
    return "\n".join(lines)


def metrics_from_result(result: dict[str, Any], injected: bool = False) -> dict[str, Any]:
    """Translate a run_pipeline result/artifact into per-run metrics.

    - score: peer_review.overall_score / 5.0 (0 if unavailable)
    - retry : 0 if recommendation == 'accept', else 1 (revise/reject/missing)
    - tokens: total_tokens_used
    - injected: whether a learned lesson was surfaced to this run
    """
    review = result.get("peer_review") or {}
    score = 0.0
    if review.get("overall_score"):
        try:
            score = float(review["overall_score"]) / 5.0
        except (TypeError, ValueError):
            score = 0.0
    rec = (review.get("recommendation") or "unknown")
    retry = 0 if rec == "accept" else 1
    tokens = int(result.get("total_tokens_used", 0) or 0)
    return {"retry": retry, "score": score, "tokens": tokens, "injected": bool(injected)}


def _real_pipeline_runner():
    """Build the production runner that calls generate_paper.run_pipeline.

    Isolates each arm's global evolution store via LABAGENT_EVOLUTION_DIR.
    """
    async def runner(problem, template, enable_evolution, output_dir, evo_dir):
        import os as _os

        _os.environ["LABAGENT_EVOLUTION_DIR"] = str(evo_dir)
        from generate_paper import run_pipeline  # lazy, avoid heavy import for --mock

        artifact = await run_pipeline(
            template_id=template,
            problem=problem,
            project_name=f"ab_{'on' if enable_evolution else 'off'}_{template}",
            output_dir=output_dir,
            enable_evolution=enable_evolution,
            enable_memory=False,
            auto_hitl=True,
        )
        snapshot = False
        try:
            snap_p = artifact.folder / ".evolution_snapshot" / "lessons.jsonl"
            snapshot = snap_p.exists() and bool(snap_p.read_text(encoding="utf-8").splitlines())
        except Exception:
            snapshot = False
        return {
            "total_tokens_used": artifact.total_tokens_used,
            "peer_review": artifact.peer_review or {},
            "folder": str(artifact.folder),
        }, snapshot

    return runner


def run_real_ab(
    pipeline_runner=None,
    *,
    output_root: Path | str | None = None,
    n_evolution: bool = True,
) -> tuple[dict[str, float], dict[str, float], str]:
    """Run 3 standard problems x evolution{ON,OFF}, aggregate metrics.

    Args:
        pipeline_runner: async callable `(problem, template, enable_evolution,
            output_dir, evo_dir) -> (result_dict, injected_bool)`.
            Defaults to the real generate_paper.run_pipeline wrapper.
        output_root: base dir for arm dirs & project outputs.
        n_evolution: include the ON arm (True) or not.

    Returns:
        (on_metrics, off_metrics, report_markdown)
    """
    output_root = Path(output_root or Path.cwd() / "ab_real_out")
    output_root.mkdir(parents=True, exist_ok=True)
    runner = pipeline_runner or _real_pipeline_runner()

    on_runs: list[dict[str, Any]] = []
    off_runs: list[dict[str, Any]] = []

    for entry in STANDARD_PROBLEMS:
        template = entry["template"]
        problem = entry["problem"]
        for arm in ([True, False] if n_evolution else [False]):
            evo_dir = output_root / ("evo_on" if arm else "evo_off")
            evo_dir.mkdir(parents=True, exist_ok=True)
            out_dir = output_root / "projects"
            result, injected = _sync_runner(runner, problem, template, arm, out_dir, evo_dir)
            metric = metrics_from_result(result, injected)
            if arm:
                on_runs.append(metric)
            else:
                off_runs.append(metric)

    on_metrics = compute_metrics(on_runs)
    off_metrics = compute_metrics(off_runs)
    report = render_report(on_metrics, off_metrics, mode="真实 API A/B")
    return on_metrics, off_metrics, report


def _sync_runner(runner, problem, template, arm, out_dir, evo_dir):
    """Run an async runner inside an event loop."""

    async def _go():
        return await runner(problem, template, arm, out_dir, evo_dir)

    import asyncio
    return asyncio.run(_go())


def main() -> None:
    """CLI entry point. Default: mock dry-run (zero API cost)."""
    import argparse
    import asyncio
    import sys
    from pathlib import Path as _P

    parser = argparse.ArgumentParser(description="自进化 A/B 对比")
    parser.add_argument("--mock", action="store_true", help="mock 干跑（默认，零 API）")
    parser.add_argument("--real", action="store_true", help="真实 A/B（调用 run_pipeline，需 API）")
    parser.add_argument("--n-runs", type=int, default=4, help="mock 每档运行次数")
    parser.add_argument("--output", type=_P, default=_P("ab_report.md"), help="报告输出路径")
    parser.add_argument("--output-root", type=_P, default=_P("ab_real_out"), help="真实 A/B 输出目录")
    args = parser.parse_args()

    if args.real:
        print("== 真实 A/B：3 问题 × evolution{ON,OFF} = 6 次完整 run_pipeline（真实 LLM 调用） ==")
        on, off, report = run_real_ab()
        args.output.write_text(report + "\n", encoding="utf-8")
        print(report)
        return

    on = compute_metrics(run_mock_benchmark(use_evolution=True, n_runs=args.n_runs))
    off = compute_metrics(run_mock_benchmark(use_evolution=False, n_runs=args.n_runs))
    report = render_report(on, off)
    args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
