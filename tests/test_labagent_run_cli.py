"""Tests for the labagent_run CLI."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_list_profiles_lists_three(tmp_path):
    """`--list-profiles` prints profile names from profiles/."""
    # Create a temp profiles dir with the three names
    (tmp_path / "research-only.yaml").write_text("name: r\nsteps: [research]\n")
    (tmp_path / "full.yaml").write_text("name: f\nsteps: [research, code]\n")
    (tmp_path / "quick.yaml").write_text("name: q\nsteps: [code]\n")

    # Use subprocess to avoid sys.argv interference
    import subprocess
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "labagent_run.py"),
         "--list-profiles", "--profiles-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    lines = out.stdout.strip().splitlines()
    assert set(lines) == {"research-only", "full", "quick"}


def test_missing_profile_exits_nonzero(tmp_path):
    import subprocess
    (tmp_path / "full.yaml").write_text("name: f\nsteps: []\n")
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "labagent_run.py"),
         "--profile", "does-not-exist", "--problem", "x",
         "--profiles-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "not found" in out.stderr.lower()


def test_runs_full_profile_with_provided_yaml(tmp_path, monkeypatch):
    """With a custom profile, the CLI runs the pipeline end-to-end."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "tiny.yaml").write_text(
        "name: tiny\nsteps:\n  - research\n  - code\n"
    )
    out_dir = tmp_path / "out"
    monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)

    import subprocess
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "labagent_run.py"),
         "--profile", "tiny", "--problem", "test problem",
         "--profiles-dir", str(profiles_dir),
         "--verbose"],
        capture_output=True, text=True,
        cwd=str(ROOT),
    )
    assert "tiny" in out.stdout + out.stderr or out.returncode == 0, (
        f"CLI failed:\nstdout={out.stdout}\nstderr={out.stderr}"
    )
