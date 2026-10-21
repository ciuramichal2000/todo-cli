"""JSON file storage with atomic writes and loud failure on corrupt data.

File layout (version 1)::

    {"version": 1, "next_id": 4,
     "tasks": [{"id": 1, "title": "...", "priority": 2,
                "due": "2026-10-25" | null, "tags": ["a"], "done": false}]}
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .errors import StorageCorruptError, StorageError, ValidationError
from .models import Task, normalize_tags, parse_due, validate_priority, validate_title
from .todolist import TodoList

FORMAT_VERSION = 1


def encode(todo: TodoList) -> dict[str, Any]:
    """Turn a task list into plain JSON-serialisable data."""
    return {
        "version": FORMAT_VERSION,
        "next_id": todo.next_id,
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "priority": task.priority,
                "due": task.due.isoformat() if task.due is not None else None,
                "tags": list(task.tags),
                "done": task.done,
            }
            for task in todo
        ],
    }


def decode(data: object) -> TodoList:
    """Rebuild a task list from parsed JSON, raising ValueError on any defect.

    Everything is checked (types, ranges, id consistency) because a file that
    was edited by hand or damaged by a crash must be rejected, not half-loaded.
    """
    if not isinstance(data, dict):
        raise ValueError("top level must be a JSON object")
    if _int_field(data, "version", "file") != FORMAT_VERSION:
        raise ValueError(f"unsupported format version {data['version']}")
    next_id = _int_field(data, "next_id", "file")
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError("'tasks' must be a list")
    tasks = [_decode_task(index, item) for index, item in enumerate(raw_tasks)]
    return TodoList(tasks, next_id)


def _int_field(obj: dict[str, Any], key: str, where: str) -> int:
    value = obj.get(key)
    if type(value) is not int:  # bool is an int subclass and must not pass
        raise ValueError(f"{where}: '{key}' must be an integer")
    return value


def _decode_task(index: int, item: object) -> Task:
    where = f"tasks[{index}]"
    if not isinstance(item, dict):
        raise ValueError(f"{where} must be an object")
    task_id = _int_field(item, "id", where)
    if task_id < 1:
        raise ValueError(f"{where}: 'id' must be at least 1")
    done = item.get("done")
    if type(done) is not bool:
        raise ValueError(f"{where}: 'done' must be true or false")
    tags = item.get("tags")
    if not isinstance(tags, list):
        raise ValueError(f"{where}: 'tags' must be a list")
    raw_due = item.get("due")
    if raw_due is not None and not isinstance(raw_due, str):
        raise ValueError(f"{where}: 'due' must be a date string or null")
    try:
        return Task(
            id=task_id,
            title=validate_title(item.get("title")),
            priority=validate_priority(item.get("priority")),
            due=parse_due(raw_due) if raw_due is not None else None,
            tags=normalize_tags(tags),
            done=done,
        )
    except ValidationError as exc:
        raise ValueError(f"{where}: {exc}") from exc


class JsonStore:
    """Reads and writes one task file; the previous version is kept as ``<name>.bak``."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    @property
    def backup_path(self) -> Path:
        return self.path.with_name(self.path.name + ".bak")

    def load(self) -> TodoList:
        """Return the stored tasks; a missing file is simply an empty list.

        A file that exists but is unreadable or invalid raises
        StorageCorruptError and is left exactly as it was, because the next
        save would otherwise overwrite whatever could still be recovered.
        """
        try:
            text = self.path.read_text(encoding="utf-8-sig")  # tolerate an editor-added BOM
        except FileNotFoundError:
            return TodoList()
        except UnicodeDecodeError as exc:
            raise self._corrupt(f"not valid UTF-8 text ({exc.reason})") from exc
        except OSError as exc:
            raise StorageError(f"cannot read {self.path}: {exc.strerror or exc}") from exc
        try:
            return decode(json.loads(text))
        except (ValueError, RecursionError) as exc:  # JSONDecodeError is a ValueError
            raise self._corrupt(str(exc) or "nesting too deep") from exc

    def save(self, todo: TodoList) -> None:
        """Write atomically: full content to a temp file in the same directory,
        then os.replace. A crash leaves either the old file or the new one,
        never a half-written file."""
        payload = json.dumps(encode(todo), indent=2, ensure_ascii=False) + "\n"
        temp_name: str | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp"
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.exists():
                shutil.copyfile(self.path, self.backup_path)
            os.replace(temp_name, self.path)
        except OSError as exc:
            raise StorageError(f"cannot write {self.path}: {exc.strerror or exc}") from exc
        finally:
            if temp_name is not None:
                with contextlib.suppress(OSError):  # already gone after a successful replace
                    os.unlink(temp_name)

    def _corrupt(self, reason: str) -> StorageCorruptError:
        if self.backup_path.exists():
            advice = f"restore it from the previous version at {self.backup_path}, or remove it to start fresh"
        else:
            advice = "repair it, or remove it to start fresh"
        return StorageCorruptError(
            f"{self.path} is corrupted: {reason}. The file was left unchanged; {advice}."
        )
