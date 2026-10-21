"""In-memory task collection.

All behavioural rules live here and the class never touches a file or the
system clock (callers pass ``today``), so every rule can be tested directly.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import date
from typing import NamedTuple

from .errors import InvalidStateError, TaskNotFoundError, ValidationError
from .models import (
    DEFAULT_PRIORITY,
    Task,
    normalize_tags,
    sort_key,
    validate_due,
    validate_priority,
    validate_title,
)

STATUSES = ("open", "done", "all")


class TodayView(NamedTuple):
    """Open tasks that need attention today."""

    overdue: list[Task]
    due_today: list[Task]


class TodoList:
    """A set of tasks plus the counter that hands out ids.

    The counter is stored separately from the tasks and only ever goes up, so
    removing the newest task does not free its id for reuse.
    """

    def __init__(self, tasks: Iterable[Task] = (), next_id: int = 1) -> None:
        loaded = list(tasks)
        ids = [task.id for task in loaded]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate task ids")
        if next_id <= max(ids, default=0):
            raise ValueError(f"next_id {next_id} must be greater than every existing id")
        self._tasks = {task.id: task for task in loaded}
        self._next_id = next_id

    @property
    def next_id(self) -> int:
        """The id the next added task will get."""
        return self._next_id

    def __len__(self) -> int:
        return len(self._tasks)

    def __iter__(self) -> Iterator[Task]:
        """Iterate in id order (creation order)."""
        return iter(sorted(self._tasks.values(), key=lambda task: task.id))

    def add(
        self,
        title: str,
        priority: int = DEFAULT_PRIORITY,
        due: date | None = None,
        tags: Iterable[str] = (),
    ) -> Task:
        """Create a task. Everything is validated before the id counter moves,
        so a rejected add does not burn an id."""
        task = Task(
            id=self._next_id,
            title=validate_title(title),
            priority=validate_priority(priority),
            due=validate_due(due),
            tags=normalize_tags(tags),
        )
        self._tasks[task.id] = task
        self._next_id += 1
        return task

    def get(self, task_id: int) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise TaskNotFoundError(task_id) from None

    def mark_done(self, task_id: int) -> Task:
        """Complete a task. Completing twice is reported, not silently accepted."""
        task = self.get(task_id)
        if task.done:
            raise InvalidStateError(f"task {task_id} is already done")
        task.done = True
        return task

    def mark_undone(self, task_id: int) -> Task:
        """Reopen a completed task."""
        task = self.get(task_id)
        if not task.done:
            raise InvalidStateError(f"task {task_id} is not done")
        task.done = False
        return task

    def remove(self, task_id: int) -> Task:
        task = self.get(task_id)
        del self._tasks[task_id]
        return task

    def query(
        self,
        *,
        today: date,
        tag: str | None = None,
        status: str = "open",
        overdue_only: bool = False,
    ) -> list[Task]:
        """Filter tasks and return them sorted by priority, then due date."""
        if status not in STATUSES:
            raise ValidationError(f"status must be one of {', '.join(STATUSES)}, got {status!r}")
        wanted_tag = normalize_tags([tag])[0] if tag is not None else None
        matches = []
        for task in self._tasks.values():
            if status != "all" and task.done != (status == "done"):
                continue
            if wanted_tag is not None and wanted_tag not in task.tags:
                continue
            if overdue_only and not task.is_overdue(today):
                continue
            matches.append(task)
        return sorted(matches, key=sort_key)

    def search(self, text: str) -> list[Task]:
        """Case-insensitive substring match on title or tags, over all tasks
        (done ones too, because searching is how you find something old)."""
        needle = text.strip().casefold()
        if not needle:
            raise ValidationError("search text must not be empty")
        matches = [
            task
            for task in self._tasks.values()
            if needle in task.title.casefold() or any(needle in tag for tag in task.tags)
        ]
        return sorted(matches, key=sort_key)

    def today_view(self, today: date) -> TodayView:
        """Open tasks that are overdue, and open tasks due exactly today."""
        overdue = [task for task in self._tasks.values() if task.is_overdue(today)]
        due_today = [task for task in self._tasks.values() if not task.done and task.due == today]
        return TodayView(sorted(overdue, key=sort_key), sorted(due_today, key=sort_key))
