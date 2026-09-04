"""Plugin discovery: entry_points + directory scanning.

Two complementary paths (DSH-style flexibility):
  1. entry_points (pip-installed packages declare in pyproject.toml)
  2. ./plugins/{name}/plugin.yaml (in-repo or third-party drop-in)

Both produce a list of PluginSpec for the manager to load.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Iterator, Optional

import yaml

from .plugin import PluginSpec


_ENTRY_POINTS_GROUP = "labagent.plugins"


def discover_entry_points(group: str = _ENTRY_POINTS_GROUP) -> Iterator[PluginSpec]:
    """Discover plugins via Python entry_points (pip-installed packages)."""
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return  # Python < 3.8, shouldn't happen in 3.13

    eps = entry_points(group=group)
    for ep in eps:
        try:
            yield PluginSpec(
                name=ep.name,
                entry=f"{ep.module}:{ep.attr}" if ep.attr else ep.module,
                source=f"entry_point:{group}",
            )
        except Exception:
            # Skip malformed entry points
            continue


def discover_directories(plugins_dir: Path | str) -> Iterator[PluginSpec]:
    """Discover plugins by scanning ./plugins/{name}/plugin.yaml."""
    plugins_dir = Path(plugins_dir)
    if not plugins_dir.exists():
        return

    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "plugin.yaml"
        if not manifest_path.exists():
            continue
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            name = data.get("name") or child.name
            entry = data.get("entry")
            if not entry:
                continue
            yield PluginSpec(
                name=name,
                entry=entry,
                version=str(data.get("version", "0.0.0")),
                inject=list(data.get("inject", [])),
                source=f"directory:{child}",
                config=dict(data.get("config", {})),
            )
        except Exception:
            # Skip malformed manifests
            continue


def load_plugin_instance(spec: PluginSpec) -> object:
    """Instantiate a plugin from its entry string ("module.path:object").

    The object can be:
      - A Plugin instance (with .name, .setup)
      - A factory function returning a Plugin instance
      - A module-level apply(ctx) function (we wrap it)
    """
    module_path, _, attr = spec.entry.partition(":")
    if not module_path:
        raise ValueError(f"Plugin {spec.name!r} entry must be 'module[:attr]': {spec.entry!r}")

    module = importlib.import_module(module_path)
    target = getattr(module, attr) if attr else module

    # Case 1: target is already a Plugin instance
    if hasattr(target, "setup") and hasattr(target, "name"):
        instance = target
    # Case 2: target is a factory function (zero-arg returns Plugin)
    elif callable(target) and not _looks_like_apply(target):
        result = target()
        if hasattr(result, "setup"):
            instance = result
        else:
            raise TypeError(
                f"Plugin {spec.name!r}: factory returned non-Plugin: {type(result)}"
            )
    # Case 3: target is an apply(ctx) function — wrap as a callable plugin
    elif callable(target) and _looks_like_apply(target):
        # Lazy import to avoid cycle
        from .plugin import Plugin
        instance = _FunctionPlugin(spec.name, target, spec.inject)
    else:
        raise TypeError(
            f"Plugin {spec.name!r}: entry {spec.entry!r} did not resolve to a Plugin/apply()."
        )

    # Attach inject from spec if not present
    if not getattr(instance, "inject", None):
        instance.inject = list(spec.inject)
    return instance


def _looks_like_apply(fn) -> bool:
    """Heuristic: an apply(ctx) function takes one positional arg."""
    import inspect
    try:
        sig = inspect.signature(fn)
        params = [
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)
        ]
        return len(params) == 1
    except (ValueError, TypeError):
        return False


class _FunctionPlugin:
    """Wraps a plain `def apply(ctx)` as a Plugin-compatible object."""

    def __init__(self, name: str, apply_fn, inject: list[str]) -> None:
        self.name = name
        self._apply = apply_fn
        self.inject = list(inject)

    def setup(self, ctx) -> None:
        self._apply(ctx)
