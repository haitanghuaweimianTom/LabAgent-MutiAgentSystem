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
