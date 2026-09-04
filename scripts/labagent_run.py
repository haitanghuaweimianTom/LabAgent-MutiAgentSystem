#!/usr/bin/env python3
"""labagent-run — CLI entry point: pick a profile, load plugins, run pipeline.

Usage:
    python scripts/labagent_run.py --profile full --problem "Solve VRPTW"
    python scripts/labagent_run.py --profile quick --problem "..."
    python scripts/labagent_run.py --profile research-only --problem "..."
    python scripts/labagent_run.py --list-profiles

This is the user-facing entry point that proves the plugin framework
end-to-end: profile YAML declares which steps to run; plugins get loaded;
the pipeline emits session/step events; metrics/trace/cost-guard plugins
observe everything in real time.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make `src/` and `scripts/` importable when invoked from any CWD
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))


def _load_profile_yaml(name: str, profiles_dir: Path) -> Path:
    """Resolve a profile name to its YAML file path."""
    candidate = profiles_dir / f"{name}.yaml"
    if not candidate.exists():
        available = sorted(p.stem for p in profiles_dir.glob("*.yaml"))
        print(f"Profile {name!r} not found. Available: {available}", file=sys.stderr)
        sys.exit(1)
    return candidate


async def _run_pipeline(profile_path: Path, problem: str) -> int:
    """Set up the plugin host, load all built-in plugins, run the pipeline."""
    from labagent.plugin import (
        Context,
        PluginManager,
        SessionLog,
        EventKind,
    )

    logger = logging.getLogger("labagent")

    ctx = Context()

    # Register host services (stubs; real LLM call must be supplied by the
    # host environment in production — for CLI dry-run we use a stub).
    from labagent.plugin.session_log import derive_session_id
    session_id = derive_session_id(profile_path.stem, problem)
    log = SessionLog(session_id=session_id, root=_ROOT / "outputs" / session_id)
    ctx.register("session_log", log)
    ctx.register("llm_call", _stub_llm_call)

    mgr = PluginManager(ctx, plugin_dirs=[])

    # Built-in plugins shipped with the host. Loaded explicitly because
    # they aren't pip-installed (so entry_points discovery doesn't find them).
    try:
        from labagent_metrics_plugin import MetricsPlugin
        mgr.activate(MetricsPlugin(out_dir=_ROOT / "outputs" / session_id / "metrics"))
    except ImportError:
        pass
    try:
        from labagent_trace_plugin import TracePlugin
        mgr.activate(TracePlugin(out_dir=_ROOT / "outputs" / session_id / "traces"))
    except ImportError:
        pass
    try:
        from labagent_cost_guard_plugin import CostGuardPlugin
        mgr.activate(CostGuardPlugin(max_tokens=10_000_000))  # effectively unlimited for dry-run
    except ImportError:
        pass
    try:
        from labagent_llm_cache_plugin import LLMCachePlugin
        mgr.activate(LLMCachePlugin(cache_dir=_ROOT / "outputs" / session_id / "llm_cache"))
    except ImportError:
        pass
    # The pipeline plugin itself — instantiated with the requested profile
    # after we have the manager ready to call its setup.
    from labagent_pipeline_plugin.plugin import PipelinePlugin
    pipeline = PipelinePlugin(profile_path=profile_path)
    mgr.activate(pipeline)

    logger.info("loaded profile %r: %d steps", profile_path.stem, len(pipeline.steps))

    try:
        results = await pipeline.run(problem)
        log.append(EventKind.SESSION_END, {"results": list(results.keys())})
        logger.info("done. steps=%s", list(results.keys()))
        return 0
    finally:
        mgr.shutdown()


def _stub_llm_call(system: str, user: str, max_tokens: int = 16000):
    """Stub for the dry-run CLI. Returns a minimal valid response."""
    import json
    content = json.dumps({"issues": [], "success_patterns": [], "ack": True})
    return {"content": content, "usage": {"total_tokens": 0}}


def main() -> int:
    parser = argparse.ArgumentParser(description="LabAgent plugin-based pipeline runner")
    parser.add_argument("--profile", type=str, default="full",
                        help="profile name (yaml file under profiles/, no .yaml)")
    parser.add_argument("--problem", type=str, default="",
                        help="problem statement")
    parser.add_argument("--list-profiles", action="store_true",
                        help="print available profiles and exit")
    parser.add_argument("--profiles-dir", type=Path,
                        default=_ROOT / "profiles")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.list_profiles:
        for p in sorted(args.profiles_dir.glob("*.yaml")):
            print(p.stem)
        return 0

    profile_path = _load_profile_yaml(args.profile, args.profiles_dir)
    if not args.problem:
        print("--problem is required (or use --list-profiles)", file=sys.stderr)
        return 2
    return asyncio.run(_run_pipeline(profile_path, args.problem))


if __name__ == "__main__":
    sys.exit(main())
