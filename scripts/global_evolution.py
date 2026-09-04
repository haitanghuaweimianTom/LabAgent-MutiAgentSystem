"""
Global Evolution Store - Cross-project lesson accumulation with project snapshots.

Inspired by Sibyl's `.sibyl/evolution` global store + workspace snapshot pattern.

Lessons gathered from every pipeline run accumulate in a single global store,
so project A's lessons inform project B's runs. To isolate a run from concurrent
global writes (and from corrupting the global store itself), each run reads a
private *snapshot* copied from the global store at start; at the end the run's
new lessons are merged back into the global store under a file lock.

Concurrency:
  - flock (fcntl.flock) around global mutations
  - atomic writes (write temp + rename) so readers never see partial state
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional

from self_evolution import LessonV2

__all__ = ["GlobalEvolutionStore", "SNAPSHOT_DIR"]

SNAPSHOT_DIR = ".evolution_snapshot"
_ENV_DIR = "LABAGENT_EVOLUTION_DIR"


class _Lock:
    """Context-manager file lock using fcntl.flock (best-effort on non-POSIX)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fh = None

    def __enter__(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a+")
        try:
            import fcntl

            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass  # non-POSIX or fcntl unavailable: degrade to no-op
        return self

    def __exit__(self, *exc) -> None:
        try:
            import fcntl

            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        self._fh.close()
        self._fh = None


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class GlobalEvolutionStore:
    """Shared, cross-project store of lessons plus per-project snapshot isolation."""

    def __init__(self, root_dir: Path | str | None = None) -> None:
        if root_dir is None:
            root_dir = Path(os.environ.get(_ENV_DIR, "")) if os.environ.get(_ENV_DIR) else None
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent / ".evolution"
        self._dir = Path(root_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lessons_path = self._dir / "lessons.jsonl"
        self._lock_path = self._dir / ".lock"

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def lessons_path(self) -> Path:
        return self._lessons_path

    def _load_lines(self) -> list[dict[str, Any]]:
        if not self._lessons_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self._lessons_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def load_all(self) -> list[LessonV2]:
        return [LessonV2.from_dict(r) for r in self._load_lines()]

    def count(self) -> int:
        return len(self._load_lines())

    def _dedup_key(self, record: dict[str, Any]) -> str:
        # Same issue + same run is a duplicate; same issue across runs is kept.
        issue_key = record.get("issue_key", "")
        return f"{record.get('run_id', '')}::{issue_key}"

    def merge_lessons(self, lessons: list[LessonV2]) -> int:
        """Merge new lessons into the global store, dedup by (issue_key, run_id)."""
        if not lessons:
            return 0
        added = 0
        with _Lock(self._lock_path):
            existing = self._load_lines()
            seen = {self._dedup_key(r) for r in existing}
            rows = list(existing)
            for lesson in lessons:
                rec = lesson.to_dict()
                key = self._dedup_key(rec)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(rec)
                added += 1
            text = "".join(
                json.dumps(r, ensure_ascii=False) + "\n" for r in rows
            )
            _atomic_write_text(self._lessons_path, text)
        return added

    def snapshot_to(self, project_dir: Path | str) -> Path:
        """Copy the global lessons into a project's private snapshot dir.

        Returns the snapshot lessons.jsonl path.
        """
        project = Path(project_dir)
        snap_dir = project / SNAPSHOT_DIR
        snap_dir.mkdir(parents=True, exist_ok=True)
        target = snap_dir / "lessons.jsonl"
        if self._lessons_path.exists():
            # Lock to avoid copying a half-written file.
            with _Lock(self._lock_path):
                text = self._lessons_path.read_text(encoding="utf-8")
            _atomic_write_text(target, text)
        else:
            _atomic_write_text(target, "")
        return target

    def merge_from_project(self, project_dir: Path | str) -> int:
        """Pull new lessons written into a project's snapshot dir into global store.

        Lessons already present in the global store (by dedup key) are skipped,
        so converge-append semantics naturally dedup against prior projects.
        """
        project = Path(project_dir)
        snap = project / SNAPSHOT_DIR / "lessons.jsonl"
        if not snap.exists():
            return 0
        records: list[LessonV2] = []
        for line in snap.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(LessonV2.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
        return self.merge_lessons(records)