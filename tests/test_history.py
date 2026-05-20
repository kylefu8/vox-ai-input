"""
history 模块测试。
"""

from src.history import HistoryStore


def test_append_and_list_recent(tmp_path):
    store = HistoryStore(path=tmp_path / "history.jsonl", max_entries=10)

    first = store.append("raw 1", "final 1", 1.2, 2, source="audio")
    second = store.append(
        "raw 2",
        "final 2",
        0.8,
        1,
        source="streaming",
        metadata={"polish_profile": "claude"},
    )

    entries = store.list_recent()
    assert [entry.id for entry in entries] == [second.id, first.id]
    assert entries[0].final_text == "final 2"
    assert entries[0].metadata["polish_profile"] == "claude"


def test_prunes_to_max_entries(tmp_path):
    store = HistoryStore(path=tmp_path / "history.jsonl", max_entries=2)

    store.append("raw 1", "final 1", 1, 1)
    store.append("raw 2", "final 2", 1, 1)
    store.append("raw 3", "final 3", 1, 1)

    entries = store.list_recent()
    assert [entry.final_text for entry in entries] == ["final 3", "final 2"]


def test_disabled_store_does_not_write(tmp_path):
    path = tmp_path / "history.jsonl"
    store = HistoryStore(path=path, enabled=False)

    assert store.append("raw", "final", 1, 1) is None
    assert not path.exists()


def test_invalid_json_lines_are_ignored(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(
        "not json\n"
        '{"id":"ok","created_at":"2026-01-01T00:00:00Z","raw_text":"r","final_text":"f"}\n',
        encoding="utf-8",
    )

    store = HistoryStore(path=path)
    entries = store.list_recent()

    assert len(entries) == 1
    assert entries[0].id == "ok"
