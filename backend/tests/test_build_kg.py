"""Tests for build_kg script."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


def test_import_build_kg():
    """Test that build_kg module can be imported."""
    from scripts import build_kg
    assert hasattr(build_kg, "scan_papers")
    assert hasattr(build_kg, "import_to_neo4j")
    assert hasattr(build_kg, "main")


def test_scan_papers_empty_dir(tmp_path):
    """Test scan_papers with empty directory."""
    from scripts.build_kg import scan_papers
    result = scan_papers(str(tmp_path))
    assert result == []


def test_scan_papers_no_reading(tmp_path):
    """Test scan_papers when no reading directory exists."""
    from scripts.build_kg import scan_papers
    (tmp_path / "project1").mkdir()
    result = scan_papers(str(tmp_path))
    assert result == []


def test_scan_papers_with_files(tmp_path):
    """Test scan_papers finds .md files in reading dirs."""
    from scripts.build_kg import scan_papers
    # Create project structure
    project = tmp_path / "test_project"
    reading = project / "reading"
    reading.mkdir(parents=True)
    (reading / "paper1.md").write_text("# Test Paper\nSome content")
    (reading / "paper2.md").write_text("# Another Paper\nMore content")

    result = scan_papers(str(tmp_path))
    assert len(result) == 2
    assert all(p["project"] == "test_project" for p in result)


def test_scan_papers_global_refs(tmp_path):
    """Test scan_papers finds global reference files."""
    from scripts.build_kg import scan_papers
    global_refs = tmp_path / "_global" / "global_references"
    global_refs.mkdir(parents=True)
    (global_refs / "ref1.md").write_text("# Reference\nContent")

    result = scan_papers(str(tmp_path))
    assert len(result) == 1
    assert result[0]["project"] == "_global"


def test_config_kg_settings():
    """Test KG settings exist in config."""
    from app.config import Settings
    s = Settings()
    assert hasattr(s, "kg_enabled")
    assert hasattr(s, "kg_extraction_batch_size")
    assert hasattr(s, "kg_max_traversal_depth")
    assert hasattr(s, "kg_rrf_weight_graph")
    assert s.kg_enabled is True
    assert s.kg_extraction_batch_size == 5
    assert s.kg_max_traversal_depth == 3
    assert s.kg_rrf_weight_graph == 0.3
