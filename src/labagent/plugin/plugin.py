"""Plugin Protocol + PluginSpec.

A plugin is a unit of extension. It declares:
  - name: identifier
  - inject: optional list of service names it requires
  - setup(ctx): registration callback (hooks + services + effects)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable


@runtime_checkable
class Plugin(Protocol):
    """The minimum contract a plugin must satisfy.

    A plugin can be:
      - A class with `name` and `setup(ctx)` (or `inject` attribute)
      - A function `apply(ctx)` with `name`/`inject` module-level attributes
      - A factory function returning a configured instance
    """

    name: str

    def setup(self, ctx) -> None:
        """Register hooks, provide services, declare effects on the given ctx."""
        ...


@dataclass
class PluginSpec:
    """A discovered plugin's metadata, before instantiation."""

    name: str
    entry: str  # "module.path:object" — module to import, object (plugin instance or factory)
    version: str = "0.0.0"
    inject: List[str] = field(default_factory=list)
    source: str = ""  # "entry_point" or "directory:/path/to/plugin"
    config: dict = field(default_factory=dict)  # user-provided config for the plugin

    def __repr__(self) -> str:
        return f"PluginSpec(name={self.name!r}, entry={self.entry!r}, source={self.source!r})"
