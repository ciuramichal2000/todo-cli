import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, datetime

import pytest

from todocli.errors import InvalidStateError, TaskNotFoundError, ValidationError
from todocli.models import Task
from todocli.todolist import TodoList

TODAY = date(2026, 10, 21)
YESTERDAY = date(2026, 10, 20)
TOMORROW = date(2026, 10, 22)


def ids(tasks):
    return [task.id for task in tasks]


def test_ids_start_at_one_and_increase():
    todo = TodoList()
    assert [todo.add(title).id for title in ("a", "b", "c")] == [1, 2, 3]


def test_removing_the_newest_task_does_not_free_its_id():
    todo = TodoList()
    for title in ("a", "b", "c"):
        todo.add(title)
    todo.remove(3)
    assert todo.add("d").id == 4
    assert ids(todo) == [1, 2, 4]


def test_removing_every_task_still_does_not_restart_numbering():
    todo = TodoList()
    todo.add("only")
    todo.remove(1)
    assert todo.add("next").id == 2


def test_rejected_add_does_not_consume_an_id():
    todo = TodoList()
    with pytest.raises(ValidationError):
        todo.add("bad priority", priority=9)
    with pytest.raises(ValidationError):
        todo.add("   ")
    with pytest.raises(ValidationError):
        todo.add("bad tag", tags=["no spaces allowed"])
    assert len(todo) == 0
    assert todo.add("fine").id == 1


def test_add_stores_normalised_fields():
    todo = TodoList()
    task = todo.add("  Pay rent ", priority=1, due=date(2026, 11, 1), tags=["Home", "home", "BILLS"])
    assert (task.title, task.priority, task.due, task.tags, task.done) == (
        "Pay rent",
        1,
        date(2026, 11, 1),
        ("home", "bills"),
        False,
    )


def test_add_uses_priority_two_when_none_is_given():
    assert TodoList().add("x").priority == 2


def test_add_rejects_a_datetime_due_value():
    with pytest.raises(ValidationError):
        TodoList().add("x", due=datetime(2026, 10, 21, 8, 0))


def test_query_sorts_by_priority_then_due_date_then_id():
    todo = TodoList()
    todo.add("id1", priority=2, due=date(2026, 11, 1))
    todo.add("id2", priority=1)  # no due date: after dated tasks of its priority
    todo.add("id3", priority=1, due=date(2026, 12, 1))
    todo.add("id4", priority=1, due=date(2026, 10, 25))
    todo.add("id5", priority=2, due=date(2026, 11, 1))  # ties with id1 on priority and due
    todo.add("id6", priority=3, due=date(2026, 1, 1))  # earliest date but lowest priority
    assert ids(todo.query(today=TODAY)) == [4, 3, 2, 1, 5, 6]


def test_query_filters_by_tag_ignoring_case():
    todo = TodoList()
    todo.add("a", tags=["work"])
    todo.add("b", tags=["home"])
    todo.add("c", tags=["work", "home"])
    assert ids(todo.query(today=TODAY, tag="WORK")) == [1, 3]
    assert ids(todo.query(today=TODAY, tag="missing")) == []


def test_query_rejects_an_invalid_tag_filter():
    with pytest.raises(ValidationError):
        TodoList().query(today=TODAY, tag="has space")


def test_query_status_open_done_and_all():
    todo = TodoList()
    for title in ("a", "b", "c"):
        todo.add(title)
    todo.mark_done(2)
    assert ids(todo.query(today=TODAY)) == [1, 3]  # open is the default
    assert ids(todo.query(today=TODAY, status="open")) == [1, 3]
    assert ids(todo.query(today=TODAY, status="done")) == [2]
    assert ids(todo.query(today=TODAY, status="all")) == [1, 2, 3]


def test_query_rejects_unknown_status():
    with pytest.raises(ValidationError, match="status"):
        TodoList().query(today=TODAY, status="pending")


def test_overdue_filter_uses_strictly_before_today_and_skips_done_tasks():
    todo = TodoList()
    todo.add("late", due=YESTERDAY)  # 1
    todo.add("due today", due=TODAY)  # 2
    todo.add("future", due=TOMORROW)  # 3
    todo.add("undated")  # 4
    todo.add("late but finished", due=YESTERDAY)  # 5
    todo.mark_done(5)
    assert ids(todo.query(today=TODAY, overdue_only=True)) == [1]
    assert ids(todo.query(today=TODAY, status="all", overdue_only=True)) == [1]


def test_filters_combine():
    todo = TodoList()
    todo.add("a", due=YESTERDAY, tags=["work"])  # 1: overdue and work
    todo.add("b", due=YESTERDAY, tags=["home"])  # 2: overdue, other tag
    todo.add("c", due=TOMORROW, tags=["work"])  # 3: work, not overdue
    assert ids(todo.query(today=TODAY, tag="work", overdue_only=True)) == [1]


def test_done_then_undo_toggles_the_task():
    todo = TodoList()
    todo.add("a")
    assert todo.mark_done(1).done is True
    assert ids(todo.query(today=TODAY)) == []
    assert todo.mark_undone(1).done is False
    assert ids(todo.query(today=TODAY)) == [1]


def test_completing_a_done_task_again_is_reported():
    todo = TodoList()
    todo.add("a")
    todo.mark_done(1)
    with pytest.raises(InvalidStateError, match="already done"):
        todo.mark_done(1)


def test_reopening_an_open_task_is_reported():
    todo = TodoList()
    todo.add("a")
    with pytest.raises(InvalidStateError, match="not done"):
        todo.mark_undone(1)


@pytest.mark.parametrize("action", ["get", "mark_done", "mark_undone", "remove"])
def test_unknown_id_raises_for_every_id_based_operation(action):
    todo = TodoList()
    todo.add("a")
    with pytest.raises(TaskNotFoundError, match="42") as info:
        getattr(todo, action)(42)
    assert info.value.task_id == 42


def test_removed_task_is_gone_and_returned():
    todo = TodoList()
    todo.add("keep")
    todo.add("drop")
    removed = todo.remove(2)
    assert removed.title == "drop"
    assert ids(todo) == [1]
    with pytest.raises(TaskNotFoundError):
        todo.get(2)


def test_search_matches_title_or_tag_case_insensitively_and_includes_done_tasks():
    todo = TodoList()
    todo.add("Buy Milk")  # 1
    todo.add("Call mom", tags=["family"])  # 2
    todo.add("Pay rent")  # 3
    todo.mark_done(3)
    assert ids(todo.search("MILK")) == [1]
    assert ids(todo.search("fam")) == [2]  # matched through the tag only
    assert ids(todo.search("rent")) == [3]  # done tasks are searchable
    assert ids(todo.search("zzz")) == []


def test_search_results_use_the_same_ordering_as_list():
    todo = TodoList()
    todo.add("report draft", priority=3)  # 1
    todo.add("report review", priority=1)  # 2
    assert ids(todo.search("report")) == [2, 1]


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_search_text_is_rejected(blank):
    with pytest.raises(ValidationError, match="search"):
        TodoList().search(blank)


def test_today_view_separates_overdue_from_due_today_and_drops_the_rest():
    todo = TodoList()
    todo.add("overdue relaxed", priority=2, due=date(2026, 10, 19))  # 1
    todo.add("overdue urgent", priority=1, due=YESTERDAY)  # 2
    todo.add("due today", due=TODAY)  # 3
    todo.add("due tomorrow", due=TOMORROW)  # 4
    todo.add("no date")  # 5
    todo.add("done today", due=TODAY)  # 6
    todo.add("done and old", due=date(2026, 1, 1))  # 7
    todo.mark_done(6)
    todo.mark_done(7)
    view = todo.today_view(TODAY)
    assert ids(view.overdue) == [2, 1]
    assert ids(view.due_today) == [3]


def test_constructor_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="duplicate"):
        TodoList([Task(1, "a"), Task(1, "b")], next_id=2)


@pytest.mark.parametrize("next_id", [1, 3])
def test_constructor_rejects_a_counter_that_would_reuse_an_existing_id(next_id):
    with pytest.raises(ValueError, match="next_id"):
        TodoList([Task(1, "a"), Task(3, "b")], next_id=next_id)


def test_iteration_is_in_id_order_even_when_loaded_out_of_order():
    todo = TodoList([Task(5, "e"), Task(2, "b")], next_id=6)
    assert ids(todo) == [2, 5]
