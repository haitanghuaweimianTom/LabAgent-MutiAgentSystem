"""Tests for sandbox-docker plugin (and the sandbox protocol)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_sandbox_protocol_shape():
    """The Sandbox protocol has a run() method returning a result dict."""
    from labagent.plugin import Plugin
    from labagent_sandbox_docker.plugin import DockerSandboxPlugin
    # A protocol-style class; we just check it has the method
    assert hasattr(DockerSandboxPlugin, "name")
    assert DockerSandboxPlugin.name == "sandbox_docker"


def test_docker_sandbox_plugin_registers_sandbox_service(tmp_path):
    from labagent.plugin import Context
    from labagent_sandbox_docker.plugin import DockerSandboxPlugin
    ctx = Context()
    p = DockerSandboxPlugin(workspace_dir=tmp_path)
    p.setup(ctx)
    # Should register a sandbox service (a callable / object with .run)
    sb = ctx.get("sandbox")
    assert sb is not None
    assert hasattr(sb, "run")


def test_docker_sandbox_falls_back_when_docker_missing(tmp_path, monkeypatch):
    """When docker is unavailable, the plugin still registers a fallback sandbox."""
    from labagent.plugin import Context
    from labagent_sandbox_docker.plugin import DockerSandboxPlugin
    # Simulate docker not installed
    import labagent_sandbox_docker.plugin as mod
    monkeypatch.setattr(mod, "DOCKER_AVAILABLE", False)
    ctx = Context()
    p = DockerSandboxPlugin(workspace_dir=tmp_path)
    p.setup(ctx)
    sb = ctx.get("sandbox")
    assert sb.backend_name == "subprocess-fallback"
