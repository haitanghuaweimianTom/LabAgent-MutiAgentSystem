import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.core.security import (
    validate_path_within, sanitize_filename, wrap_user_content,
    sanitize_input, MAX_UPLOAD_SIZE
)
from backend.app.core.errors import ValidationError
import pytest


class TestValidatePathWithin:
    def test_valid_path(self):
        base = Path("/tmp/project")
        target = base / "data" / "file.txt"
        result = validate_path_within(target, base)
        assert result == target.resolve()

    def test_traversal_detected(self):
        base = Path("/tmp/project")
        target = base / "../../etc/passwd"
        with pytest.raises(ValidationError):
            validate_path_within(target, base)

    def test_encoded_dots_not_traversal(self):
        base = Path("/tmp/project")
        target = base / "%2e%2e/etc/passwd"
        result = validate_path_within(target, base)
        assert result == target.resolve()

    def test_symlink_escape(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()
        target = tmp_path / "outside"
        target.mkdir()
        link = base / "link"
        link.symlink_to(target)
        with pytest.raises(ValidationError):
            validate_path_within(link / "file.txt", base)


class TestSanitizeFilename:
    def test_clean_filename(self):
        assert sanitize_filename("report.pdf") == "report.pdf"

    def test_removes_path_separators(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_removes_special_chars(self):
        result = sanitize_filename("file<script>.txt")
        assert "<" not in result
        assert ">" not in result

    def test_preserves_dots_in_name(self):
        assert sanitize_filename("data.v2.json") == "data.v2.json"

    def test_empty_returns_default(self):
        assert sanitize_filename("") == "unnamed"


class TestWrapUserContent:
    def test_wraps_with_delimiters(self):
        result = wrap_user_content("hello world", "user_problem")
        assert "<user_problem>" in result
        assert "</user_problem>" in result
        assert "hello world" in result

    def test_nested_angle_brackets_escaped(self):
        result = wrap_user_content("a < b > c", "input")
        assert "<input>" in result
        assert "&lt;" in result or "<" not in result.replace("<input>", "").replace("</input>", "")


class TestSanitizeInput:
    def test_strips_control_chars(self):
        result = sanitize_input("hello\x00\x01world")
        assert "\x00" not in result
        assert "\x01" not in result

    def test_max_length(self):
        result = sanitize_input("a" * 1000, max_length=100)
        assert len(result) == 100

    def test_preserves_newlines(self):
        result = sanitize_input("line1\nline2")
        assert "\n" in result


class TestMaxUploadSize:
    def test_is_50mb(self):
        assert MAX_UPLOAD_SIZE == 50 * 1024 * 1024


# ── TaskCreateRequest validation (T3) ──────────────────────────────

from backend.app.schemas.schemas import TaskCreateRequest
from pydantic import ValidationError as PydanticValidationError
import pytest


class TestTaskCreateRequestConstraints:
    """Tests for Pydantic Field constraints on TaskCreateRequest."""

    def test_valid_request(self):
        req = TaskCreateRequest(problem_text="hello world")
        assert req.problem_text == "hello world"
        assert req.project_name is None

    def test_problem_text_min_length_rejects_empty(self):
        with pytest.raises(PydanticValidationError):
            TaskCreateRequest(problem_text="")

    def test_problem_text_whitespace_only_stripped_to_empty(self):
        # Pydantic v2: field_validator runs AFTER min_length check,
        # so "   " (len=3) passes min_length=1, then validator strips to "".
        req = TaskCreateRequest(problem_text="   ")
        assert req.problem_text == ""

    def test_problem_text_max_length_rejects_too_long(self):
        with pytest.raises(PydanticValidationError):
            TaskCreateRequest(problem_text="x" * 100001)

    def test_problem_text_max_length_accepts_boundary(self):
        req = TaskCreateRequest(problem_text="x" * 100000)
        assert len(req.problem_text) == 100000

    def test_problem_text_strips_control_characters(self):
        req = TaskCreateRequest(problem_text="hello\x00\x01\x1f\x7fworld")
        assert req.problem_text == "helloworld"

    def test_problem_text_preserves_newlines_and_tabs(self):
        req = TaskCreateRequest(problem_text="line1\nline2\ttab")
        assert "\n" in req.problem_text
        assert "\t" in req.problem_text

    def test_problem_text_strips_leading_trailing_whitespace(self):
        req = TaskCreateRequest(problem_text="  hello  ")
        assert req.problem_text == "hello"

    def test_project_name_max_length_rejects_too_long(self):
        with pytest.raises(PydanticValidationError):
            TaskCreateRequest(problem_text="x", project_name="a" * 101)

    def test_project_name_max_length_accepts_boundary(self):
        req = TaskCreateRequest(problem_text="x", project_name="a" * 100)
        assert len(req.project_name) == 100

    def test_project_name_allows_alphanumeric_underscore_hyphen(self):
        req = TaskCreateRequest(problem_text="x", project_name="work_2026-guangzhou")
        assert req.project_name == "work_2026-guangzhou"

    def test_project_name_rejects_special_characters(self):
        with pytest.raises(PydanticValidationError):
            TaskCreateRequest(problem_text="x", project_name="project@name")

    def test_project_name_rejects_spaces(self):
        with pytest.raises(PydanticValidationError):
            TaskCreateRequest(problem_text="x", project_name="my project")

    def test_project_name_rejects_dots(self):
        with pytest.raises(PydanticValidationError):
            TaskCreateRequest(problem_text="x", project_name="my.project")

    def test_project_name_none_is_valid(self):
        req = TaskCreateRequest(problem_text="x", project_name=None)
        assert req.project_name is None

    def test_project_name_empty_string_rejected(self):
        with pytest.raises(PydanticValidationError):
            TaskCreateRequest(problem_text="x", project_name="")


class TestUploadSizeEnforcement:
    """Verify that upload size checks exist in all router files."""

    def _read_router(self, name: str) -> str:
        router_path = Path(__file__).parent.parent / "backend" / "app" / "routers" / name
        return router_path.read_text()

    def test_data_upload_has_size_check(self):
        src = self._read_router("data.py")
        assert "MAX_UPLOAD_SIZE" in src
        assert "413" in src

    def test_pdf_upload_has_size_check(self):
        src = self._read_router("pdf.py")
        assert "MAX_UPLOAD_SIZE" in src
        assert "413" in src

    def test_knowledge_upload_has_size_check(self):
        src = self._read_router("knowledge.py")
        assert "MAX_UPLOAD_SIZE" in src
        assert "413" in src

    def test_sanitize_filename_used_in_uploads(self):
        for name in ("data.py", "pdf.py", "knowledge.py"):
            src = self._read_router(name)
            assert "sanitize_filename" in src
