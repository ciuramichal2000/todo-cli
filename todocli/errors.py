"""Exception types.

Every expected failure derives from TodoError, so the CLI can print one clean
message for any of them while real bugs still surface as tracebacks.
"""


class TodoError(Exception):
    """Base class for failures that are the user's to fix, not bugs."""


class ValidationError(TodoError, ValueError):
    """A title, priority, due date, tag or filter value is not acceptable.

    Also a ValueError so that code decoding stored data can treat bad values
    and bad structure uniformly.
    """


class TaskNotFoundError(TodoError):
    """No task has the requested id (it never existed or was removed)."""

    def __init__(self, task_id: int) -> None:
        super().__init__(f"no task with id {task_id}")
        self.task_id = task_id


class InvalidStateError(TodoError):
    """The task is already in the state the command would put it in."""


class StorageError(TodoError):
    """The storage file could not be read or written."""


class StorageCorruptError(StorageError):
    """The storage file exists but its content is not a valid task list."""
