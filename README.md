# todo-cli

A command-line to-do manager that keeps its tasks in a single JSON file. Tasks have a priority (1-3), an optional due date and optional tags, and can be listed, filtered, searched, completed, reopened and removed. It uses only the Python standard library.

## Interesting engineering

- **Ids are never reused.** The next id is stored in the file next to the tasks, so removing the newest task does not hand its number to the next one. A rejected `add` does not consume an id either.
- **Atomic writes.** Each save writes a temp file in the same directory, fsyncs it, then swaps it in with `os.replace`. A failed save leaves the old file untouched and removes the temp file.
- **Corruption is reported, not repaired silently.** Invalid JSON, a wrong structure, bad types, duplicate ids or an inconsistent id counter raise a clear error naming the file. The file is left as it was, so it is never overwritten with an empty list. Every save also keeps the previous version as `<file>.bak`, and the error message points to it.
- **Logic is separate from I/O.** `TodoList` never touches a file or the clock (callers pass `today`), `JsonStore` only does file work, and the CLI handlers return lines instead of printing. Tests exercise the logic directly and a few go through `main(argv)` with a fixed date.
- **Strict input rules.** Due dates must be real `YYYY-MM-DD` dates (`20261021` and `2026-02-30` are rejected), priorities must be the integers 1-3, and titles and tags are validated before anything changes.

## Usage

```
python -m todocli --file tasks.json add "Pay rent" -p 1 -d 2026-10-25 -t home -t bills
python -m todocli --file tasks.json add Buy oat milk
python -m todocli --file tasks.json list                       # open tasks, most urgent first
python -m todocli --file tasks.json list --tag home --overdue  # filters combine
python -m todocli --file tasks.json list --status all          # open, done or all
python -m todocli --file tasks.json today                      # overdue + due today
python -m todocli --file tasks.json search rent                # title or tag, done tasks included
python -m todocli --file tasks.json done 1
python -m todocli --file tasks.json undo 1
python -m todocli --file tasks.json remove 1
```

Without `--file`, the file is `$TODOCLI_FILE` if set, otherwise `~/.todocli.json`.

Priority 1 is the most urgent. Lists are sorted by priority, then due date (tasks with no due date last), then id. A task is overdue when it is open and its due date is before today. Completing a task that is already done (or reopening one that is not) is reported as an error. Exit status is 0 on success, 1 for an expected failure such as an unknown id or a corrupted file, and 2 for a command-line usage error.

## Running the tests

```
python -m pytest -q
```

The tests use `tmp_path`, a fixed date and no network, so they do not depend on the current day.

## Limitations

- No file locking: two commands writing at the same moment can lose one update (last writer wins).
- `.bak` holds only the single previous version, and there is no command to restore it; recovery is a manual copy.
- Dates are plain dates without times or time zones; only the `YYYY-MM-DD` form is accepted.
- There is no `edit` command; to change a task, remove it and add it again (it gets a new id).

Built with AI coding assistance.
