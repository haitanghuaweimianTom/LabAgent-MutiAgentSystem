"""Tests for labagent_trace_plugin."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from labagent.plugin import Context, SessionLog


def test_trace_dumps_each_step_output(tmp_path):
    from labagent_trace_plugin.plugin import TracePlugin
    log = SessionLog(session_id="t", root=tmp_path)
    ctx = Context()
    ctx.register("session_log", log)
    p = TracePlugin(out_dir=tmp_path / "tr")
    p.setup(ctx)
    ctx.emit("step/end", {"step": "research", "output": "LIT REVIEW OK"})
    ctx.emit("step/end", {"step": "code", "output": "code ran"})
    files = sorted((tmp_path / "tr").glob("*.json"))
    assert len(files) == 2
    contents = [json.loads(f.read_text())["step"] for f in files]
    assert contents == ["research", "code"]


def test_trace_redacts_secrets(tmp_path):
    from labagent_trace_plugin.plugin import TracePlugin
    log = SessionLog(session_id="t", root=tmp_path)
    ctx = Context()
    ctx.register("session_log", log)
    p = TracePlugin(out_dir=tmp_path / "tr")
    p.setup(ctx)
    ctx.emit("step/end", {
        "step": "code",
        "output": "API_KEY=sk-12345 should be hidden",
    })
    files = list((tmp_path / "tr").glob("*.json"))
    assert files
    text = files[0].read_text()
    assert "sk-12345" not in text
    assert "[REDACTED]" in text
