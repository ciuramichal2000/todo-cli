"""Task record and the validation rules for each of its fields."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .errors import ValidationError

MIN_PRIORITY = 1
MAX_PRIORITY = 3
DEFAULT_PRIORITY = 2

# Strict on purpose: date.fromisoformat also accepts forms such as "20261021"
# and "2026-W43-3", which would make stored files and typed input ambiguous.
_DUE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Letters/digits first, then letters, digits, "_" or "-". Keeps tags safe to
# print as "#tag" and free of separators.
_TAG_PATTERN = re.compile(r"[^\W_][\w-]*")


@dataclass
class Task:
    """One to-do item. Priority 1 is the most urgent, 3 the least."""

    id: int
    title: str
    priority: int = DEFAULT_PRIORITY
    due: date | None = None
    tags: tuple[str, ...] = ()
    done: bool = False

    def is_overdue(self, today: date) -> bool:
        """Open and due strictly before today; a task due today is not overdue yet."""
        return not self.done and self.due is not None and self.due < today


def sort_key(task: Task) -> tuple[int, bool, date, int]:
    """Order by priority, then due date (undated last), then id for a stable order."""
    return (task.priority, task.due is None, task.due or date.max, task.id)


def validate_title(raw: str) -> str:
    """Return the stripped title; reject blank titles and control characters.

    Line breaks and tabs would break the one-line-per-task output.
    """
    if not isinstance(raw, str):
        raise ValidationError(f"title must be text, got {type(raw).__name__}")
    title = raw.strip()
    if not title:
        raise ValidationError("title must not be empty")
    if any(unicodedata.category(char) == "Cc" for char in title):
        raise ValidationError("title must not contain tabs, line breaks or other control characters")
    return title


def validate_priority(value: int) -> int:
    """Accept exactly the integers 1, 2 and 3 (a bool is not a priority)."""
    if type(value) is not int or not MIN_PRIORITY <= value <= MAX_PRIORITY:
        raise ValidationError(f"priority must be 1, 2 or 3 (1 = most urgent), got {value!r}")
    return value


def validate_due(value: date | None) -> date | None:
    """Accept None or a plain date; a datetime would not compare with dates."""
    if value is not None and type(value) is not date:
        raise ValidationError(f"due must be a date, got {type(value).__name__}")
    return value


def parse_due(text: str) -> date:
    """Parse a YYYY-MM-DD string into a real calendar date."""
    candidate = text.strip()
    if not _DUE_PATTERN.fullmatch(candidate):
        raise ValidationError(f"due date must look like YYYY-MM-DD, got {text!r}")
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        raise ValidationError(f"{text!r} is not a real calendar date") from None


def normalize_tags(raw: Iterable[str]) -> tuple[str, ...]:
    """Lower-case, validate and de-duplicate tags, keeping first-seen order."""
    seen: dict[str, None] = {}
    for item in raw:
        if not isinstance(item, str):
            raise ValidationError(f"tag must be text, got {type(item).__name__}")
        tag = item.strip().lower()
        if not _TAG_PATTERN.fullmatch(tag):
            raise ValidationError(
                f"invalid tag {item!r}: use letters, digits, '_' or '-', starting with a letter or digit"
            )
        seen.setdefault(tag)
    return tuple(seen)
