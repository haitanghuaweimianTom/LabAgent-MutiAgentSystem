"""Tests for skill_library.py - code/writing/prompt skill library."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from skill_library import Skill, SkillLibrary, SkillKind


class TestSkillModel:
    def test_code_skill_defaults(self):
        s = Skill(kind="code", name="vrptw-solver", description="d", content="def solve(): pass")
        assert s.kind == "code"
        assert s.version == 1
        assert s.use_count == 0
        assert s.skill_id != ""

    def test_kind_enum_values(self):
        assert SkillKind.CODE == "code"
        assert SkillKind.WRITING == "writing"
        assert SkillKind.PROMPT == "prompt"


class TestSkillLibrary:
    def test_add_and_count(self, tmp_path):
        lib = SkillLibrary(tmp_path / "skills")
        lib.add_skill(
            kind="writing",
            name="intro-pattern",
            description="strong intro",
            content="Start with gaps then contributions",
            when_to_use="when writing an intro",
            template_id="neurips_2024",
        )
        assert lib.count() == 1

    def test_code_skill_auto_description(self, tmp_path):
        lib = SkillLibrary(tmp_path / "skills")
        s = lib.add_code_skill(
            problem="物流网络最短路径规划，含时间窗约束",
            code="import numpy\ndef solve():\n    pass\n# branch and bound with time windows",
            template_id="math_modeling",
            evidence={"exec_success": True, "quality_score": 0.85},
        )
        assert s.kind == "code"
        assert s.description != ""
        assert "物流" in s.description

    def test_same_problem_increments_version_keeps_old(self, tmp_path):
        lib = SkillLibrary(tmp_path / "skills")
        lib.add_code_skill("same problem text alpha", "code v1", "t")
        s2 = lib.add_code_skill("same problem text alpha", "code v2", "t")
        assert s2.version == 2
        assert sum(1 for s in lib.load_all() if s.name == s2.name) == 2

    def test_retrieve_relevant_ranks_first(self, tmp_path):
        lib = SkillLibrary(tmp_path / "skills")
        lib.add_skill(kind="code", name="vrptw",
                      description="VRPTW solver for vehicle routing with time windows",
                      content="ortools constraint solver", when_to_use="routing with time windows")
        lib.add_skill(kind="writing", name="structure",
                       description="standard scientific paper structure",
                       content="IMRaD with related work", when_to_use="any paper")
        results = lib.retrieve("vehicle routing time window optimization", top_k=3)
        assert len(results) >= 1
        assert results[0].name == "vrptw"

    def test_retrieve_empty_library(self, tmp_path):
        lib = SkillLibrary(tmp_path / "skills")
        assert lib.retrieve("anything", top_k=2) == []

    def test_persist_roundtrip(self, tmp_path):
        lib = SkillLibrary(tmp_path / "skills")
        lib.add_skill(kind="prompt", name="binary-constraints", description="bc",
                       content="Always declare binary decision variables explicitly",
                       when_to_use="modeling MILP")
        lib2 = SkillLibrary(tmp_path / "skills")
        assert lib2.count() == 1
        assert lib2.load_all()[0].kind == "prompt"

    def test_record_use_increments(self, tmp_path):
        lib = SkillLibrary(tmp_path / "skills")
        s = lib.add_skill(kind="code", name="solver", description="d", content="c")
        lib.record_use(s.skill_id)
        reloaded = [x for x in lib.load_all() if x.name == "solver"][0]
        assert reloaded.use_count == 1