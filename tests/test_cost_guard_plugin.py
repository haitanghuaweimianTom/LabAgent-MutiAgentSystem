"""Tests for labagent_cost_guard_plugin."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from labagent.plugin import Context


def test_cost_guard_triggers_abort_event(tmp_path):
    from labagent_cost_guard_plugin.plugin import CostGuardPlugin
    ctx = Context()
    aborted = []
    ctx.on("cost/abort", lambda p: aborted.append(p))
    p = CostGuardPlugin(max_tokens=1000, out_dir=tmp_path / "cg")
    p.setup(ctx)
    # Simulate steps spending tokens
    ctx.emit("step/end", {"step": "research", "tokens": 600})
    assert not aborted  # under threshold
    ctx.emit("step/end", {"step": "code", "tokens": 500})
    # total 1100 > 1000 → abort
    assert len(aborted) == 1
    assert aborted[0]["total_tokens"] == 1100
    assert aborted[0]["limit"] == 1000
    # Aborted state is sticky: further emissions should not re-emit
    ctx.emit("step/end", {"step": "write", "tokens": 100})
    assert len(aborted) == 1


def test_cost_guard_does_not_trigger_under_limit():
    from labagent_cost_guard_plugin.plugin import CostGuardPlugin
    ctx = Context()
    aborted = []
    ctx.on("cost/abort", lambda p: aborted.append(p))
    p = CostGuardPlugin(max_tokens=10_000)
    p.setup(ctx)
    ctx.emit("step/end", {"step": "x", "tokens": 500})
    ctx.emit("step/end", {"step": "y", "tokens": 500})
    assert not aborted
    assert p.total_tokens == 1000


def test_cost_guard_under_limit_returns_false():
    from labagent_cost_guard_plugin.plugin import CostGuardPlugin
    p = CostGuardPlugin(max_tokens=100)
    assert p.check(50) is False
    assert p.check(100) is True
    assert p.check(101) is True
