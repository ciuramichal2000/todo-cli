import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from pathlib import Path

import pytest

from todocli.cli import default_store_path, main
from todocli.storage import JsonStore

TODAY = date(2026, 10, 21)


@pytest.fixture
def run(tmp_path, capsys):
    """Call main() against a temp file and return (exit code, stdout lines, stderr text)."""
    path = tmp_path / "todo.json"

    def call(*args, today=TODAY):
        code = main(["--file", str(path), *args], today=today)
        captured = capsys.readouterr()
        return code, captured.out.splitlines(), captured.err

    call.path = path
    return call


def test_add_reports_the_new_id_and_list_shows_the_task(run):
    code, out, err = run("add", "Pay rent", "-p", "1", "-d", "2026-10-25", "-t", "home")
    assert (code, out, err) == (0, ["Added task 1: Pay rent"], "")

    code, out, err = run("list")
    assert code == 0
    assert out == ["   1 [ ] P1 2026-10-25 Pay rent  #home"]


def test_title_words_do_not_need_quotes(run):
    code, out, _ = run("add", "Buy", "oat", "milk")
    assert (code, out) == (0, ["Added task 1: Buy oat milk"])


def test_task_without_due_date_or_tags_prints_a_dash_and_default_priority(run):
    run("add", "Call mom")
    _, out, _ = run("list")
    assert out == ["   1 [ ] P2 " + "-" + " " * 10 + "Call mom"]


def test_list_orders_by_priority_and_flags_overdue_tasks(run):
    run("add", "relaxed", "-p", "3")
    run("add", "late urgent", "-p", "1", "-d", "2026-10-01", "-t", "work", "-t", "bills")
    run("add", "soon urgent", "-p", "1", "-d", "2026-10-22")
    _, out, _ = run("list")
    assert out == [
        "   2 [ ] P1 2026-10-01 late urgent  #work #bills  (overdue)",
        "   3 [ ] P1 2026-10-22 soon urgent",
        "   1 [ ] P3 " + "-" + " " * 10 + "relaxed",
    ]


def test_list_filters_by_tag_status_and_overdue(run):
    run("add", "a", "-t", "work", "-d", "2026-10-01")  # 1: overdue, work
    run("add", "b", "-t", "home", "-d", "2026-10-02")  # 2: overdue, home
    run("add", "c", "-t", "work")  # 3: work, no date
    run("done", "3")

    _, by_tag, _ = run("list", "--tag", "work")
    assert [line.split()[0] for line in by_tag] == ["1"]

    _, done, _ = run("list", "--status", "done")
    assert [line.split()[0] for line in done] == ["3"]

    _, everything, _ = run("list", "--status", "all")
    assert [line.split()[0] for line in everything] == ["1", "2", "3"]

    _, overdue, _ = run("list", "--overdue")
    assert [line.split()[0] for line in overdue] == ["1", "2"]

    _, both, _ = run("list", "--overdue", "--tag", "home")
    assert [line.split()[0] for line in both] == ["2"]


def test_empty_result_says_so(run):
    code, out, _ = run("list")
    assert (code, out) == (0, ["No matching tasks."])


def test_done_undo_and_remove_flow(run):
    run("add", "first")
    run("add", "second")

    assert run("done", "1")[:2] == (0, ["Completed task 1: first"])
    assert [line.split()[0] for line in run("list")[1]] == ["2"]

    assert run("undo", "1")[:2] == (0, ["Reopened task 1: first"])
    assert [line.split()[0] for line in run("list")[1]] == ["1", "2"]

    assert run("remove", "2")[:2] == (0, ["Removed task 2: second"])
    assert [line.split()[0] for line in run("list", "--status", "all")[1]] == ["1"]


def test_ids_are_never_reused_across_separate_runs(run):
    run("add", "a")
    run("add", "b")
    run("remove", "2")
    code, out, _ = run("add", "c")
    assert (code, out) == (0, ["Added task 3: c"])


def test_done_marks_the_box(run):
    run("add", "a")
    run("done", "1")
    _, out, _ = run("list", "--status", "done")
    assert out == ["   1 [x] P2 " + "-" + " " * 10 + "a"]


def test_search_finds_tasks_by_title_and_tag_including_done_ones(run):
    run("add", "Buy milk", "-t", "shop")
    run("add", "Pay rent", "-t", "home")
    run("done", "2")
    _, by_title, _ = run("search", "MILK")
    _, by_tag, _ = run("search", "home")
    assert [line.split()[0] for line in by_title] == ["1"]
    assert [line.split()[0] for line in by_tag] == ["2"]
    assert run("search", "nothing", "matches")[1] == ["No matching tasks."]


def test_today_view_lists_overdue_before_due_today_and_omits_other_tasks(run):
    run("add", "old", "-d", "2026-10-19")  # 1
    run("add", "now", "-d", "2026-10-21", "-p", "1")  # 2
    run("add", "later", "-d", "2026-10-22")  # 3
    run("add", "undated")  # 4
    code, out, _ = run("today")
    assert code == 0
    assert out == [
        "Overdue:",
        "   1 [ ] P2 2026-10-19 old  (overdue)",
        "Due today:",
        "   2 [ ] P1 2026-10-21 now",
    ]


def test_today_view_with_nothing_due(run):
    run("add", "later", "-d", "2026-10-22")
    assert run("today")[:2] == (0, ["Nothing due today."])


def test_same_data_gives_a_different_today_view_on_a_different_day(run):
    run("add", "report", "-d", "2026-10-21")
    assert run("today", today=date(2026, 10, 21))[1][0] == "Due today:"
    assert run("today", today=date(2026, 10, 22))[1][0] == "Overdue:"
    assert run("today", today=date(2026, 10, 20))[1] == ["Nothing due today."]


def test_unknown_id_fails_with_a_message_on_stderr_only(run):
    run("add", "a")
    code, out, err = run("done", "99")
    assert (code, out) == (1, [])
    assert err == "error: no task with id 99\n"


def test_completing_twice_fails(run):
    run("add", "a")
    run("done", "1")
    code, out, err = run("done", "1")
    assert (code, out) == (1, [])
    assert "already done" in err


@pytest.mark.parametrize("priority", ["0", "4", "-2"])
def test_out_of_range_priority_fails_and_nothing_is_saved(run, priority):
    code, out, err = run("add", "x", "-p", priority)
    assert (code, out) == (1, [])
    assert "priority must be 1, 2 or 3" in err
    assert not run.path.exists()


@pytest.mark.parametrize("due", ["2026-02-30", "tomorrow", ""])
def test_invalid_due_date_fails_and_nothing_is_saved(run, due):
    code, _, err = run("add", "x", "-d", due)
    assert code == 1
    assert "due date" in err or "calendar date" in err
    assert not run.path.exists()


def test_invalid_tag_fails(run):
    code, _, err = run("add", "x", "-t", "two words")
    assert code == 1
    assert "invalid tag" in err


def test_blank_search_fails(run):
    code, _, err = run("search", " ")
    assert code == 1
    assert "search text" in err


def test_corrupted_file_is_reported_and_never_overwritten(run):
    run.path.write_text('{"version": 1, "next_id": 1, "tasks": [', encoding="utf-8")
    before = run.path.read_bytes()

    code, out, err = run("add", "must not be saved")

    assert (code, out) == (1, [])
    assert "corrupted" in err
    assert str(run.path) in err
    assert run.path.read_bytes() == before
    assert not Path(str(run.path) + ".bak").exists()


def test_read_only_commands_never_write_the_file(run, monkeypatch):
    run("add", "a")
    before = run.path.read_bytes()

    def forbidden_save(self, todo):
        raise AssertionError("a read-only command tried to save")

    monkeypatch.setattr(JsonStore, "save", forbidden_save)
    for command in (["list"], ["today"], ["search", "a"]):
        assert run(*command)[0] == 0
    assert run.path.read_bytes() == before


def test_unknown_command_is_a_usage_error(run):
    with pytest.raises(SystemExit) as info:
        run("frobnicate")
    assert info.value.code == 2


def test_non_numeric_id_is_a_usage_error(run):
    with pytest.raises(SystemExit) as info:
        run("done", "abc")
    assert info.value.code == 2


def test_missing_command_is_a_usage_error(run):
    with pytest.raises(SystemExit) as info:
        run()
    assert info.value.code == 2


def test_default_store_path_prefers_the_environment_variable():
    assert default_store_path({"TODOCLI_FILE": "work.json"}) == Path("work.json")


def test_default_store_path_falls_back_to_a_dotfile_in_the_home_directory():
    assert default_store_path({}) == Path.home() / ".todocli.json"
    assert default_store_path({"TODOCLI_FILE": ""}) == Path.home() / ".todocli.json"
