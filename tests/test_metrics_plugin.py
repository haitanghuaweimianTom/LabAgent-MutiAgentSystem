"""Tests for labagent_metrics_plugin."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from labagent.plugin import Context, EventKind, SessionLog


def test_metrics_plugin_writes_per_step(tmp_path):
    from labagent_metrics_plugin.plugin import MetricsPlugin
    log = SessionLog(session_id="t", root=tmp_path)
    ctx = Context()
    ctx.register("session_log", log)
    p = MetricsPlugin(out_dir=tmp_path / "metrics")
    p.setup(ctx)
    ctx.emit("step/start", {"step": "research"})
    time.sleep(0.01)
    ctx.emit("step/end", {"step": "research", "tokens": 1234})
    ctx.emit("session/end", {"run_id": "r1"})
    f = list((tmp_path / "metrics").glob("r1*.json"))
    assert f, "no metrics file written"
    data = json.loads(f[0].read_text(encoding="utf-8"))
    assert "steps" in data and len(data["steps"]) == 1
    s = data["steps"][0]
    assert s["step"] == "research"
    assert s["tokens"] == 1234
    assert s["duration_s"] >= 0.01


def test_metrics_plugin_accumulates_tokens():
    from labagent_metrics_plugin.plugin import MetricsPlugin
    log = SessionLog(session_id="t", root=Path("/tmp/m1"))
    ctx = Context()
    ctx.register("session_log", log)
    p = MetricsPlugin()
    p.setup(ctx)
    for i in range(3):
        ctx.emit("step/end", {"step": f"s{i}", "tokens": 100})
    assert p.total_tokens == 300
