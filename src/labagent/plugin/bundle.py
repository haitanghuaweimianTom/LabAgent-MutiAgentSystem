"""Bundle/Profile 三层加载 (DSH 风格).

DSH 三层:
  - Profile: 命名应用形态 (web/headless/sdk),列出 ordered bundle 栈
  - Bundle: 一份 plugin manifest 列表 + 引用包;无代码本身
  - Plugin: 具体功能模块

在我们的简化映射:
  - profile.yaml: 列出 bundles 数组 + 自身 config
  - bundle.yaml: 列出 plugins 数组 + 自身 config
  - plugin.yaml: 单个插件 (已存在, 由 discover_directories 读取)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .plugin import PluginSpec

logger = logging.getLogger(__name__)


@dataclass
class Profile:
    """A named application shape; lists ordered bundles + self config."""

    name: str
    bundles: list[str] = field(default_factory=list)  # 路径/标识符
    config: dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "bundles": list(self.bundles), "config": dict(self.config), "source": self.source}


@dataclass
class Bundle:
    """A list of plugins + self config; no code itself."""

    name: str
    plugins: list[PluginSpec] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "plugins": [p.__dict__ for p in self.plugins],
            "config": dict(self.config),
            "source": self.source,
        }


def load_profile(path: Path | str) -> Profile:
    """Load a profile from a YAML file."""
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Profile(
        name=data.get("name", path.stem),
        bundles=list(data.get("bundles", [])),
        config=dict(data.get("config", {})),
        source=str(path),
    )


def load_bundle(path: Path | str) -> Bundle:
    """Load a bundle from a YAML file. Plugins referenced by name are resolved later.

    Bundle format:
        name: academic-core
        plugins:
          - name: self-evolution
            entry: labagent_evolve.plugin:SelfEvolutionPlugin
          - name: memory-store
            entry: labagent_memory.plugin:MemoryStorePlugin
        config:
          log_level: INFO
    """
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    plugins: list[PluginSpec] = []
    for p in data.get("plugins", []) or []:
        if isinstance(p, str):
            # bare string: refer to a known plugin by name
            plugins.append(PluginSpec(name=p, entry=p))
        elif isinstance(p, dict):
            plugins.append(
                PluginSpec(
                    name=p["name"],
                    entry=p["entry"],
                    version=str(p.get("version", "0.0.0")),
                    inject=list(p.get("inject", [])),
                    source=str(path),
                    config=dict(p.get("config", {})),
                )
            )
    return Bundle(
        name=data.get("name", path.stem),
        plugins=plugins,
        config=dict(data.get("config", {})),
        source=str(path),
    )


def discover_bundles(bundles_dir: Path | str) -> list[Bundle]:
    """Scan a directory for bundle.yaml files."""
    bundles_dir = Path(bundles_dir)
    if not bundles_dir.exists():
        return []
    out: list[Bundle] = []
    for child in sorted(bundles_dir.iterdir()):
        manifest = child / "bundle.yaml"
        if not manifest.exists():
            continue
        try:
            out.append(load_bundle(manifest))
        except Exception as e:
            logger.warning(f"Skipping bundle {manifest}: {e}")
    return out


def collect_bundle_plugins(
    profile: Profile,
    *,
    bundles_dir: Optional[Path | str] = None,
) -> list[PluginSpec]:
    """Resolve a profile's bundle list to a flat list of PluginSpec.

    Each bundle is loaded from `<bundles_dir>/<bundle_name>/bundle.yaml`.
    """
    bundles_dir = Path(bundles_dir) if bundles_dir else None
    specs: list[PluginSpec] = []
    seen: set[str] = set()
    for bundle_name in profile.bundles:
        if bundles_dir is None:
            # treat bundle_name as a PluginSpec name (no Bundle file)
            if bundle_name not in seen:
                specs.append(PluginSpec(name=bundle_name, entry=bundle_name))
                seen.add(bundle_name)
            continue
        manifest = bundles_dir / bundle_name / "bundle.yaml"
        if not manifest.exists():
            logger.warning(f"Bundle {bundle_name!r} not found at {manifest}; skipping")
            continue
        bundle = load_bundle(manifest)
        for spec in bundle.plugins:
            if spec.name not in seen:
                specs.append(spec)
                seen.add(spec.name)
    return specs
