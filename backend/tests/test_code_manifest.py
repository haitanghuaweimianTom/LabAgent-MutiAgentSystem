"""backend.app.services.code_manifest 回归测试。"""
import json
import pytest

from app.services.code_manifest import (
    CodeFileSpec,
    CodeManifest,
    SplitSuggestion,
    split_by_complexity,
    validate_manifest,
    parse_manifest_from_dict,
    parse_manifest_from_string,
    render_files_block,
    ROLE_FILENAME_HINT,
    CODE_MANIFEST_PROMPT,
)


# ==================== 1. 数据类序列化 ====================

def test_code_file_spec_roundtrip():
    s = CodeFileSpec(path="main.py", role="entry", code="x=1", entry_point=True)
    d = s.to_dict()
    assert d["path"] == "main.py"
    assert d["entry_point"] is True
    s2 = CodeFileSpec.from_dict(d)
    assert s2.path == s.path
    assert s2.entry_point == s.entry_point


def test_code_manifest_roundtrip():
    m = CodeManifest(
        files=[
            CodeFileSpec(path="main.py", role="entry", code="x=1", entry_point=True),
            CodeFileSpec(path="utils.py", role="utility", code="y=2"),
        ],
        runner="python",
        notes="hello",
    )
    d = m.to_dict()
    assert d["runner"] == "python"
    m2 = CodeManifest.from_dict(d)
    assert m2.entry.path == "main.py"
    assert m2.total_loc == 2
    assert m2.notes == "hello"


# ==================== 2. split_by_complexity ====================

def test_split_no_trigger():
    s = split_by_complexity(estimated_loc=50, roles=["solver"], sub_problem_count=1)
    assert s.should_split is False


def test_split_triggered_by_loc():
    s = split_by_complexity(estimated_loc=400, roles=["solver"], sub_problem_count=1)
    assert s.should_split is True
    assert any("300" in r for r in s.reasons)


def test_split_triggered_by_roles():
    s = split_by_complexity(
        estimated_loc=50,
        roles=["data_processing", "model", "train"],
        sub_problem_count=1,
    )
    assert s.should_split is True


def test_split_triggered_by_sub_problems():
    s = split_by_complexity(estimated_loc=50, roles=["solver"], sub_problem_count=2)
    assert s.should_split is True


def test_split_suggested_files_have_naming_convention():
    s = split_by_complexity(
        estimated_loc=400,
        roles=["data_processing", "model", "train"],
        sub_problem_count=2,
    )
    assert s.suggested_files
    # 必须含 data_process_*, model_*, train_*, utils.py, main.py
    text = " ".join(s.suggested_files)
    for kw in ("data_process", "model_", "train_", "utils.py", "main.py"):
        assert kw in text, f"missing {kw} in {s.suggested_files}"


# ==================== 3. validate_manifest ====================

def _mf(*specs):
    return CodeManifest(files=list(specs))


def test_validate_empty_manifest():
    r = validate_manifest(CodeManifest())
    assert r.valid is False
    assert any("empty" in i for i in r.issues)


def test_validate_well_formed():
    m = _mf(
        CodeFileSpec(path="data_process_sub1.py", role="data_processing", code="x=1\n" * 100),
        CodeFileSpec(
            path="main.py", role="entry", code="import dp", entry_point=True,
            depends_on=["data_process_sub1.py"],
        ),
    )
    r = validate_manifest(m)
    assert r.valid is True


def test_validate_single_file_too_long():
    """单文件 > 300 行 → 拒绝。"""
    m = _mf(CodeFileSpec(path="solver.py", role="solver", code="x=1\n" * 400))
    r = validate_manifest(m)
    assert r.valid is False
    assert any("300" in i for i in r.issues)


def test_validate_single_file_too_many_roles():
    m = _mf(CodeFileSpec(path="solver.py", role="solver", code="x"))
    r = validate_manifest(m, role_count=3)
    assert r.valid is False
    assert any("role" in i for i in r.issues)


def test_validate_single_file_multiple_sub_problems():
    m = _mf(CodeFileSpec(path="solver.py", role="solver", code="x"))
    r = validate_manifest(m, sub_problem_count=2)
    assert r.valid is False


def test_validate_multiple_entry_points_rejected():
    m = _mf(
        CodeFileSpec(path="a.py", role="entry", entry_point=True),
        CodeFileSpec(path="b.py", role="entry", entry_point=True),
    )
    r = validate_manifest(m)
    assert r.valid is False
    assert any("entry" in i for i in r.issues)


def test_validate_duplicate_paths_rejected():
    m = _mf(
        CodeFileSpec(path="a.py", role="solver", code="x"),
        CodeFileSpec(path="a.py", role="solver", code="y"),
    )
    r = validate_manifest(m)
    assert r.valid is False
    assert any("duplicate" in i for i in r.issues)


def test_validate_dangling_dependency():
    m = _mf(
        CodeFileSpec(
            path="main.py", role="entry", entry_point=True,
            depends_on=["missing.py"],
        ),
    )
    r = validate_manifest(m)
    assert r.valid is False
    assert any("not in manifest" in i for i in r.issues)


def test_validate_warns_no_entry_point_in_multi_file():
    m = _mf(
        CodeFileSpec(path="a.py", role="solver", code="x"),
        CodeFileSpec(path="b.py", role="solver", code="y"),
    )
    r = validate_manifest(m)
    assert r.valid is True
    assert any("entry" in w for w in r.warnings)


# ==================== 4. parse_manifest_from_string ====================

def test_parse_with_markdown_fence():
    raw = (
        "下面是 manifest：\n"
        "```json\n"
        '{"files": [{"path": "x.py", "role": "solver"}]}\n'
        "```\n"
    )
    m = parse_manifest_from_string(raw)
    assert len(m.files) == 1
    assert m.files[0].path == "x.py"


def test_parse_with_raw_json():
    m = parse_manifest_from_string('{"files": [{"path": "a.py", "role": "solver"}]}')
    assert len(m.files) == 1


def test_parse_no_json_returns_empty():
    m = parse_manifest_from_string("no json here")
    assert m.files == []


def test_parse_uses_code_files_alias():
    """LLM 有时返回 ``code_files`` 而不是 ``files``。"""
    m = parse_manifest_from_dict({"code_files": [{"path": "x.py", "role": "solver"}]})
    assert len(m.files) == 1


# ==================== 5. render_files_block ====================

def test_render_files_block_has_entry_marker():
    m = _mf(
        CodeFileSpec(path="main.py", role="entry", entry_point=True, description="入口"),
        CodeFileSpec(path="utils.py", role="utility", description="工具"),
    )
    block = render_files_block(m)
    assert "main.py" in block
    assert "ENTRY" in block
    assert "入口" in block


def test_render_files_block_with_dependencies():
    m = _mf(
        CodeFileSpec(path="a.py", role="entry", entry_point=True, depends_on=["b.py"]),
        CodeFileSpec(path="b.py", role="utility"),
    )
    block = render_files_block(m)
    assert "deps=b.py" in block


# ==================== 6. CODE_MANIFEST_PROMPT 内容 ====================

def test_prompt_contains_hard_rules():
    assert "300" in CODE_MANIFEST_PROMPT
    assert "≥ 3" in CODE_MANIFEST_PROMPT or ">= 3" in CODE_MANIFEST_PROMPT
    assert "子问题" in CODE_MANIFEST_PROMPT


def test_prompt_contains_naming_conventions():
    for kw in ("data_process", "model_", "train_", "eval_", "viz_", "utils.py", "main.py"):
        assert kw in CODE_MANIFEST_PROMPT, kw
