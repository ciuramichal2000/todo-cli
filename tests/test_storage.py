import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import codecs
import json
from datetime import date

import pytest

from todocli.errors import StorageCorruptError, StorageError
from todocli.storage import JsonStore
from todocli.todolist import TodoList

GOOD_TASK = {"id": 1, "title": "Pay rent", "priority": 1, "due": "2026-10-25", "tags": ["home"], "done": False}


def document(**task_overrides):
    """A valid one-task document with some task fields replaced."""
    return {"version": 1, "next_id": 2, "tasks": [{**GOOD_TASK, **task_overrides}]}


def temp_files(directory):
    return [name for name in os.listdir(directory) if name.endswith(".tmp")]


def test_missing_file_loads_as_an_empty_list_and_is_not_created(tmp_path):
    store = JsonStore(tmp_path / "todo.json")
    todo = store.load()
    assert len(todo) == 0
    assert todo.next_id == 1
    assert not (tmp_path / "todo.json").exists()


def test_save_writes_the_documented_json_shape(tmp_path):
    path = tmp_path / "todo.json"
    todo = TodoList()
    todo.add("Pay rent", priority=1, due=date(2026, 10, 25), tags=["home"])
    JsonStore(path).save(todo)
    assert json.loads(path.read_text(encoding="utf-8")) == document()


def test_round_trip_preserves_every_field_including_non_ascii_text(tmp_path):
    store = JsonStore(tmp_path / "todo.json")
    todo = TodoList()
    todo.add("Zażółć gęślą jaźń", priority=3, tags=["Pilne", "dom"])
    todo.add("Second", due=date(2027, 2, 28))
    todo.mark_done(2)
    store.save(todo)

    loaded = store.load()
    rows = [(t.id, t.title, t.priority, t.due, t.tags, t.done) for t in loaded]
    assert rows == [
        (1, "Zażółć gęślą jaźń", 3, None, ("pilne", "dom"), False),
        (2, "Second", 2, date(2027, 2, 28), (), True),
    ]
    assert loaded.next_id == 3


def test_non_ascii_text_is_stored_readably_not_as_escapes(tmp_path):
    path = tmp_path / "todo.json"
    todo = TodoList()
    todo.add("Zażółć")
    JsonStore(path).save(todo)
    assert "Zażółć" in path.read_text(encoding="utf-8")


def test_id_counter_survives_save_and_load_after_removing_the_newest_task(tmp_path):
    store = JsonStore(tmp_path / "todo.json")
    todo = TodoList()
    for title in ("a", "b", "c"):
        todo.add(title)
    todo.remove(3)
    store.save(todo)

    reloaded = store.load()
    assert reloaded.add("d").id == 4  # a "max id + 1" scheme would hand out 3 again


def test_failed_replace_leaves_the_old_file_intact_and_no_temp_file_behind(tmp_path, monkeypatch):
    path = tmp_path / "todo.json"
    store = JsonStore(path)
    original = TodoList()
    original.add("original task")
    store.save(original)
    before = path.read_bytes()

    changed = store.load()
    changed.add("this must not be persisted")

    def exploding_replace(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", exploding_replace)
    with pytest.raises(StorageError, match="cannot write"):
        store.save(changed)

    assert path.read_bytes() == before
    assert temp_files(tmp_path) == []


def test_second_save_keeps_the_previous_version_as_bak(tmp_path):
    path = tmp_path / "todo.json"
    store = JsonStore(path)
    todo = TodoList()
    todo.add("first")
    store.save(todo)
    first_version = path.read_bytes()

    todo.add("second")
    store.save(todo)

    assert store.backup_path == tmp_path / "todo.json.bak"
    assert store.backup_path.read_bytes() == first_version
    assert [t.title for t in store.load()] == ["first", "second"]


def test_first_save_creates_no_bak_because_there_is_nothing_to_back_up(tmp_path):
    store = JsonStore(tmp_path / "todo.json")
    store.save(TodoList())
    assert not store.backup_path.exists()


@pytest.mark.parametrize(
    "content",
    [
        "",  # empty file, e.g. left by a crash in a non-atomic writer
        "{ not json",
        "[]",  # valid JSON, wrong top-level type
        json.dumps({"version": 2, "next_id": 1, "tasks": []}),
        json.dumps({"version": True, "next_id": 1, "tasks": []}),
        json.dumps({"version": 1, "next_id": 1}),  # no tasks key
        json.dumps({"version": 1, "next_id": 1, "tasks": "none"}),
        json.dumps({"version": 1, "next_id": "2", "tasks": []}),
        json.dumps(document(id=1) | {"next_id": 1}),  # counter would reuse id 1
        json.dumps({"version": 1, "next_id": 5, "tasks": [GOOD_TASK, GOOD_TASK]}),  # duplicate ids
        json.dumps(document(id=0)),
        json.dumps(document(id=True)),
        json.dumps(document(priority=7)),
        json.dumps(document(priority="1")),
        json.dumps(document(due="2026-02-30")),
        json.dumps(document(due=20261025)),
        json.dumps(document(done="yes")),
        json.dumps(document(tags="home")),
        json.dumps(document(tags=["has space"])),
        json.dumps(document(title="   ")),
        json.dumps(document(title=None)),
        json.dumps({"version": 1, "next_id": 2, "tasks": ["not an object"]}),
    ],
)
def test_corrupt_content_is_reported_and_the_file_is_left_untouched(tmp_path, content):
    path = tmp_path / "todo.json"
    path.write_text(content, encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(StorageCorruptError, match="corrupted"):
        JsonStore(path).load()

    assert path.read_bytes() == before


def test_invalid_utf8_is_reported_as_corruption(tmp_path):
    path = tmp_path / "todo.json"
    path.write_bytes(b"\xff\xfe{")
    with pytest.raises(StorageCorruptError, match="UTF-8"):
        JsonStore(path).load()


def test_absurdly_deep_nesting_is_reported_as_corruption_not_a_crash(tmp_path):
    path = tmp_path / "todo.json"
    path.write_text("[" * 200_000, encoding="utf-8")
    with pytest.raises(StorageCorruptError):
        JsonStore(path).load()


def test_corruption_error_names_the_file_and_the_backup_when_one_exists(tmp_path):
    path = tmp_path / "todo.json"
    store = JsonStore(path)
    todo = TodoList()
    todo.add("a")
    store.save(todo)
    store.save(todo)  # second save creates todo.json.bak
    path.write_text("garbage", encoding="utf-8")

    with pytest.raises(StorageCorruptError) as info:
        store.load()

    message = str(info.value)
    assert str(path) in message
    assert str(store.backup_path) in message
    # The previous good version is still loadable from the backup.
    assert [t.title for t in JsonStore(store.backup_path).load()] == ["a"]


def test_corruption_error_without_a_backup_does_not_mention_one(tmp_path):
    path = tmp_path / "todo.json"
    path.write_text("garbage", encoding="utf-8")
    with pytest.raises(StorageCorruptError) as info:
        JsonStore(path).load()
    assert ".bak" not in str(info.value)


def test_file_starting_with_a_utf8_bom_still_loads(tmp_path):
    path = tmp_path / "todo.json"
    path.write_bytes(codecs.BOM_UTF8 + json.dumps(document()).encode("utf-8"))
    assert [t.title for t in JsonStore(path).load()] == ["Pay rent"]


def test_a_directory_in_place_of_the_file_is_a_storage_error_not_corruption(tmp_path):
    path = tmp_path / "todo.json"
    path.mkdir()
    with pytest.raises(StorageError) as info:
        JsonStore(path).load()
    assert not isinstance(info.value, StorageCorruptError)


def test_saving_into_a_missing_directory_is_a_storage_error(tmp_path):
    store = JsonStore(tmp_path / "no-such-dir" / "todo.json")
    with pytest.raises(StorageError, match="cannot write"):
        store.save(TodoList())
