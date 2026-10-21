import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, datetime

import pytest

from todocli.errors import ValidationError
from todocli.models import (
    Task,
    normalize_tags,
    parse_due,
    sort_key,
    validate_due,
    validate_priority,
    validate_title,
)


def test_title_is_stripped_of_surrounding_whitespace():
    assert validate_title("  Buy milk \n") == "Buy milk"


def test_title_keeps_non_ascii_text_unchanged():
    assert validate_title("Zażółć gęślą jaźń") == "Zażółć gęślą jaźń"


@pytest.mark.parametrize("blank", ["", "   ", "\t\n "])
def test_blank_title_is_rejected(blank):
    with pytest.raises(ValidationError, match="empty"):
        validate_title(blank)


@pytest.mark.parametrize("bad", ["two\nlines", "tab\tinside", "bell\x07"])
def test_title_with_control_characters_is_rejected(bad):
    with pytest.raises(ValidationError, match="control"):
        validate_title(bad)


def test_title_must_be_text():
    with pytest.raises(ValidationError):
        validate_title(None)


@pytest.mark.parametrize("value", [1, 2, 3])
def test_priorities_one_to_three_are_accepted(value):
    assert validate_priority(value) == value


@pytest.mark.parametrize("value", [0, 4, -1, 100, True, "2", 2.0, None])
def test_other_priorities_are_rejected(value):
    with pytest.raises(ValidationError, match="priority"):
        validate_priority(value)


def test_parse_due_accepts_a_leap_day():
    assert parse_due("2028-02-29") == date(2028, 2, 29)


def test_parse_due_ignores_surrounding_whitespace():
    assert parse_due(" 2026-10-21 ") == date(2026, 10, 21)


@pytest.mark.parametrize(
    "text",
    [
        "2027-02-29",  # 2027 is not a leap year
        "2026-13-01",
        "2026-00-10",
        "2026-04-31",
        "",
        "tomorrow",
        "26-10-21",
        "2026/10/21",
        "20261021",  # date.fromisoformat would accept this; we do not
        "2026-W43-3",
        "2026-10-21T10:00",
        "٢٠٢٦-١٠-٢١",  # non-ASCII digits
    ],
)
def test_parse_due_rejects_anything_but_a_real_iso_date(text):
    with pytest.raises(ValidationError):
        parse_due(text)


def test_validate_due_rejects_datetime_because_it_cannot_be_compared_with_dates():
    with pytest.raises(ValidationError, match="date"):
        validate_due(datetime(2026, 10, 21, 9, 30))


def test_validate_due_passes_none_and_plain_dates_through():
    assert validate_due(None) is None
    assert validate_due(date(2026, 1, 2)) == date(2026, 1, 2)


def test_tags_are_lowercased_and_deduplicated_in_first_seen_order():
    assert normalize_tags(["Work", "home", "WORK", " Errands "]) == ("work", "home", "errands")


def test_tags_may_contain_non_ascii_letters_digits_dash_and_underscore():
    assert normalize_tags(["Zażółć", "q3-plan", "a_b2"]) == ("zażółć", "q3-plan", "a_b2")


def test_no_tags_gives_an_empty_tuple():
    assert normalize_tags([]) == ()


@pytest.mark.parametrize("bad", ["", "   ", "two words", "-lead", "_lead", "a,b", "#x", "semi;colon"])
def test_invalid_tags_are_rejected(bad):
    with pytest.raises(ValidationError, match="tag"):
        normalize_tags([bad])


def test_non_text_tag_is_rejected():
    with pytest.raises(ValidationError):
        normalize_tags([5])


def test_overdue_means_open_and_strictly_before_today():
    today = date(2026, 10, 21)
    assert Task(1, "a", due=date(2026, 10, 20)).is_overdue(today)
    assert not Task(2, "b", due=date(2026, 10, 21)).is_overdue(today)
    assert not Task(3, "c", due=date(2026, 10, 22)).is_overdue(today)
    assert not Task(4, "d", due=None).is_overdue(today)
    assert not Task(5, "e", due=date(2026, 1, 1), done=True).is_overdue(today)


def test_sort_key_orders_priority_before_due_date_and_undated_last():
    urgent_undated = Task(1, "a", priority=1)
    urgent_late = Task(2, "b", priority=1, due=date(2030, 1, 1))
    relaxed_early = Task(3, "c", priority=2, due=date(2020, 1, 1))
    ordered = sorted([relaxed_early, urgent_undated, urgent_late], key=sort_key)
    assert [task.id for task in ordered] == [2, 1, 3]
