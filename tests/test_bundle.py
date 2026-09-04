"""Tests for Bundle/Profile loading (P2)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from labagent.plugin.bundle import (
    Bundle,
    Profile,
    collect_bundle_plugins,
    discover_bundles,
    load_bundle,
    load_profile,
)
from labagent.plugin.plugin import PluginSpec


class TestProfile:
    def test_load_from_yaml(self, tmp_path):
        p = tmp_path / "profile.yaml"
        p.write_text(
            "name: math_paper\n"
            "bundles:\n"
            "  - academic-core\n"
            "  - paper-quality\n"
            "config:\n"
            "  log_level: INFO\n"
        )
        prof = load_profile(p)
        assert prof.name == "math_paper"
        assert prof.bundles == ["academic-core", "paper-quality"]
        assert prof.config == {"log_level": "INFO"}


class TestBundle:
    def test_load_with_plugins(self, tmp_path):
        b = tmp_path / "bundle.yaml"
        b.write_text(
            "name: academic-core\n"
            "plugins:\n"
            "  - name: self-evolution\n"
            "    entry: labagent_evolve.plugin:plugin\n"
            "    inject: [llm, session]\n"
            "  - name: memory-store\n"
            "    entry: labagent_memory.plugin:plugin\n"
            "config:\n"
            "  log_level: INFO\n"
        )
        bundle = load_bundle(b)
        assert bundle.name == "academic-core"
        assert len(bundle.plugins) == 2
        assert bundle.plugins[0].name == "self-evolution"
        assert bundle.plugins[0].inject == ["llm", "session"]
        assert bundle.config == {"log_level": "INFO"}

    def test_load_bare_string_plugins(self, tmp_path):
        b = tmp_path / "bundle.yaml"
        b.write_text(
            "name: minimal\n"
            "plugins:\n"
            "  - just-a-name\n"
        )
        bundle = load_bundle(b)
        assert len(bundle.plugins) == 1
        assert bundle.plugins[0].name == "just-a-name"


class TestDiscoverBundles:
    def test_empty(self, tmp_path):
        assert discover_bundles(tmp_path) == []

    def test_finds_bundle_files(self, tmp_path):
        for name in ["alpha", "beta"]:
            d = tmp_path / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "bundle.yaml").write_text(f"name: {name}\nplugins: []\n")
        bundles = discover_bundles(tmp_path)
        assert [b.name for b in bundles] == ["alpha", "beta"]


class TestCollectBundlePlugins:
    def test_dedup(self, tmp_path):
        # Two bundles both declare the same plugin name -> only one wins
        for name in ["core", "extras"]:
            d = tmp_path / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "bundle.yaml").write_text(
                f"name: {name}\n"
                "plugins:\n"
                "  - name: shared\n"
                f"    entry: {name}.shared:plugin\n"
            )
        prof = Profile(name="p", bundles=["core", "extras"])
        specs = collect_bundle_plugins(prof, bundles_dir=tmp_path)
        assert len(specs) == 1
        assert specs[0].name == "shared"

    def test_no_bundles_dir_treats_bundles_as_names(self, tmp_path):
        prof = Profile(name="p", bundles=["self-evolution", "memory-store"])
        specs = collect_bundle_plugins(prof)
        assert [s.name for s in specs] == ["self-evolution", "memory-store"]
