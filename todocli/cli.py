"""Argparse front end: parse arguments, call TodoList, print the result.

Handlers return the lines to print instead of printing, and main() takes the
current date as a parameter, so the whole CLI can be driven from tests.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path

from .errors import TodoError
from .models import DEFAULT_PRIORITY, Task, parse_due
from .storage import JsonStore
from .todolist import STATUSES, TodoList

ENV_FILE_VARIABLE = "TODOCLI_FILE"
DEFAULT_FILE_NAME = ".todocli.json"

Handler = Callable[[TodoList, argparse.Namespace, date], list[str]]


def default_store_path(env: Mapping[str, str] | None = None) -> Path:
    """The file to use when --file is absent: $TODOCLI_FILE, else ~/.todocli.json."""
    environment = os.environ if env is None else env
    configured = environment.get(ENV_FILE_VARIABLE)
    return Path(configured) if configured else Path.home() / DEFAULT_FILE_NAME


def format_task(task: Task, today: date) -> str:
    """One fixed-column line: id, done box, priority, due date, title, tags, overdue flag."""
    box = "x" if task.done else " "
    due = task.due.isoformat() if task.due is not None else "-"
    text = [task.title]
    if task.tags:
        text.append(" ".join(f"#{tag}" for tag in task.tags))
    if task.is_overdue(today):
        text.append("(overdue)")
    return f"{task.id:>4} [{box}] P{task.priority} {due:<10} " + "  ".join(text)


def _format_many(tasks: list[Task], today: date) -> list[str]:
    return [format_task(task, today) for task in tasks] or ["No matching tasks."]


def _add(todo: TodoList, args: argparse.Namespace, today: date) -> list[str]:
    due = parse_due(args.due) if args.due is not None else None
    task = todo.add(" ".join(args.title), priority=args.priority, due=due, tags=args.tag)
    return [f"Added task {task.id}: {task.title}"]


def _list(todo: TodoList, args: argparse.Namespace, today: date) -> list[str]:
    tasks = todo.query(today=today, tag=args.tag, status=args.status, overdue_only=args.overdue)
    return _format_many(tasks, today)


def _done(todo: TodoList, args: argparse.Namespace, today: date) -> list[str]:
    return [f"Completed task {args.id}: {todo.mark_done(args.id).title}"]


def _undo(todo: TodoList, args: argparse.Namespace, today: date) -> list[str]:
    return [f"Reopened task {args.id}: {todo.mark_undone(args.id).title}"]


def _remove(todo: TodoList, args: argparse.Namespace, today: date) -> list[str]:
    return [f"Removed task {args.id}: {todo.remove(args.id).title}"]


def _search(todo: TodoList, args: argparse.Namespace, today: date) -> list[str]:
    return _format_many(todo.search(" ".join(args.query)), today)


def _today(todo: TodoList, args: argparse.Namespace, today: date) -> list[str]:
    view = todo.today_view(today)
    lines: list[str] = []
    if view.overdue:
        lines.append("Overdue:")
        lines.extend(format_task(task, today) for task in view.overdue)
    if view.due_today:
        lines.append("Due today:")
        lines.extend(format_task(task, today) for task in view.due_today)
    return lines or ["Nothing due today."]


HANDLERS: dict[str, Handler] = {
    "add": _add,
    "list": _list,
    "done": _done,
    "undo": _undo,
    "remove": _remove,
    "search": _search,
    "today": _today,
}
# Only these change the data, so read-only commands never rewrite the file.
MUTATING = frozenset({"add", "done", "undo", "remove"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="todo", description="A small to-do manager that keeps its tasks in a JSON file."
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help=f"task file (default: ${ENV_FILE_VARIABLE}, else ~/{DEFAULT_FILE_NAME})",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    add = commands.add_parser("add", help="add a task")
    add.add_argument("title", nargs="+", help="task title (quotes are optional)")
    add.add_argument(
        "-p", "--priority", type=int, default=DEFAULT_PRIORITY, help="1 (most urgent) to 3; default 2"
    )
    add.add_argument("-d", "--due", help="due date as YYYY-MM-DD")
    add.add_argument("-t", "--tag", action="append", default=[], help="tag; repeat for several")

    listing = commands.add_parser("list", help="list tasks, most urgent first")
    listing.add_argument("--tag", help="only tasks with this tag")
    listing.add_argument("--status", choices=STATUSES, default="open", help="default: open")
    listing.add_argument("--overdue", action="store_true", help="only open tasks past their due date")

    for name, help_text in (("done", "mark a task done"), ("undo", "reopen a done task"), ("remove", "delete a task")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("id", type=int, help="task id")

    search = commands.add_parser("search", help="find tasks by title or tag, done ones included")
    search.add_argument("query", nargs="+", help="text to look for")

    commands.add_parser("today", help="show overdue tasks and tasks due today")
    return parser


def main(argv: Sequence[str] | None = None, *, today: date | None = None) -> int:
    """Run one command. Returns 0 on success and 1 on an expected failure;
    argparse itself exits with status 2 on a usage error."""
    args = build_parser().parse_args(argv)
    current_day = today if today is not None else date.today()
    try:
        store = JsonStore(args.file if args.file is not None else default_store_path())
        todo = store.load()
        lines = HANDLERS[args.command](todo, args, current_day)
        if args.command in MUTATING:
            store.save(todo)
    except TodoError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0
