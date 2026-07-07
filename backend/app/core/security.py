"""Shared security utilities for input validation, path traversal, and prompt injection defense."""

import re
import html
from pathlib import Path
from typing import Optional

from .errors import ErrorCode, ValidationError

MAX_UPLOAD_SIZE = 50 * 1024 * 1024

_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

_DANGEROUS_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def validate_path_within(path: Path, base_dir: Path) -> Path:
    """Validate that resolved path stays within base_dir. Raises ValidationError on traversal."""
    resolved_base = base_dir.resolve()
    try:
        resolved_target = path.resolve()
    except (OSError, ValueError) as e:
        raise ValidationError(
            code=ErrorCode.VALIDATION_FAILED,
            message=f"Invalid path: {e}",
            status_code=422,
        )

    if not str(resolved_target).startswith(str(resolved_base) + "/") and resolved_target != resolved_base:
        raise ValidationError(
            code=ErrorCode.VALIDATION_FAILED,
            message=f"Path traversal detected: {path} is outside {base_dir}",
            status_code=422,
        )

    return resolved_target


def sanitize_filename(filename: str) -> str:
    """Remove dangerous characters from filename. Returns 'unnamed' if empty."""
    if not filename:
        return "unnamed"

    name = Path(filename).name

    name = _DANGEROUS_FILENAME_RE.sub('', name)

    name = re.sub(r'\.{2,}', '.', name)

    name = name.lstrip('.')

    return name if name else "unnamed"


def wrap_user_content(content: str, tag: str = "user_input") -> str:
    """Wrap user content with XML-style delimiters to prevent prompt injection."""
    safe_tag = re.sub(r'[^a-zA-Z0-9_]', '', tag)

    escaped = html.escape(content, quote=False)

    return f"<{safe_tag}>\n{escaped}\n</{safe_tag}>"


def sanitize_input(
    text: str,
    max_length: Optional[int] = None,
    strip_control: bool = True
) -> str:
    """Sanitize text input by removing control characters and enforcing length."""
    if not isinstance(text, str):
        return str(text)

    result = text

    if strip_control:
        result = _CONTROL_CHAR_RE.sub('', result)

    if max_length is not None and len(result) > max_length:
        result = result[:max_length]

    return result
