"""Tests for global_evolution.py - global store + project snapshot."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from global_evolution import GlobalEvolutionStore
from self_evolution import LessonV2


def make_lesson(desc, run_id, **kw):
    return LessonV2(
        stage_name=kw.get("stage_name", "step1"),
        category=kw.get("category", "experiment"),
        severity=kw.get("severity", "error"),
        description=desc,
        run_id=run_id,
        source=kw.get("source", "reflection"),
    )


class TestGlobalEvolutionStore:
    def test_default_dir_created(self, tmp_path):
        store = GlobalEvolutionStore(tmp_path / ".evolution")
        assert (tmp_path / ".evolution").exists()
        assert (tmp_path / ".evolution" / "lessons.jsonl").parent.exists()

    def test_merge_into_global_store(self, tmp_path):
        store = GlobalEvolutionStore(tmp_path / ".evolution")
        store.merge_lessons([make_lesson("A specific global problem about VRPTW solver", "run-global")])
        assert store.count() == 1

    def test_snapshot_copies_global_lessons(self, tmp_path):
        store = GlobalEvolutionStore(tmp_path / ".evolution")
        store.merge_lessons([make_lesson("A specific global problem about VRPTW solver", "run-global")])
        project = tmp_path / "projB"
        store.snapshot_to(project)
        target = project / ".evolution_snapshot" / "lessons.jsonl"
        assert target.exists()
        assert "VRPTW" in target.read_text(encoding="utf-8")

    def test_merge_dedups_same_issue_and_run(self, tmp_path):
        store = GlobalEvolutionStore(tmp_path / ".evolution")
        l1 = make_lesson("a specific problem about overfitting", "run1")
        l2 = make_lesson("a specific problem about overfitting", "run1")
        store.merge_lessons([l1, l2])
        assert store.count() == 1

    def test_merge_keeps_distinct_run_issues(self, tmp_path):
        store = GlobalEvolutionStore(tmp_path / ".evolution")
        store.merge_lessons([make_lesson("problem one specific text", "run1")])
        store.merge_lessons([make_lesson("problem two specific text", "run2")])
        assert store.count() == 2

    def test_snapshot_isolates_projects(self, tmp_path):
        store = GlobalEvolutionStore(tmp_path / ".evolution")
        store.merge_lessons([make_lesson("shared problem alpha", "run-g")])
        pA = tmp_path / "prodA"
        pB = tmp_path / "prodB"
        store.snapshot_to(pA)  # snapshot A before new lesson
        store.merge_lessons([make_lesson("new problem beta", "run-g2")])
        store.snapshot_to(pB)  # snapshot B after new lesson
        snapA = (pA / ".evolution_snapshot" / "lessons.jsonl").read_text(encoding="utf-8")
        snapB = (pB / ".evolution_snapshot" / "lessons.jsonl").read_text(encoding="utf-8")
        assert "beta" not in snapA
        assert "beta" in snapB

    def test_merge_from_snapshot_dir(self, tmp_path):
        store = GlobalEvolutionStore(tmp_path / ".evolution")
        project = tmp_path / "prodC"
        store.merge_lessons([make_lesson("seed issue gamma", "run-seed")])
        store.snapshot_to(project)
        # Simulate new lessons written into the project's snapshot dir
        new_lesson = make_lesson("a brand new problem delta", "run-c")
        write_lesson(project / ".evolution_snapshot" / "lessons.jsonl", new_lesson)
        merged = store.merge_from_project(project)
        # delta is new; seed already in global so not duplicated
        assert any(l.description == "a brand new problem delta" for l in store.load_all())


def write_lesson(path: Path, lesson) -> None:
    import json as _json
    with path.open("a", encoding="utf-8") as f:
        f.write(_json.dumps(lesson.to_dict(), ensure_ascii=False) + "\n")