"""画布空覆盖防护单测。"""

from __future__ import annotations

import json

from services.canvas_save_guard import (
    is_empty_overwrite,
    parse_canvas_node_count,
    write_nonempty_backup,
    read_backup,
)


def test_parse_node_count():
    assert parse_canvas_node_count(None) == 0
    assert parse_canvas_node_count("{}") == 0
    assert parse_canvas_node_count('{"nodes": []}') == 0
    assert parse_canvas_node_count(json.dumps({"nodes": [{"id": "a"}]})) == 1


def test_empty_overwrite_blocked_when_server_has_nodes():
    existing = json.dumps({"nodes": [{"id": "n1"}], "edges": []})
    assert is_empty_overwrite(existing, {"nodes": [], "edges": []}) is True
    assert is_empty_overwrite(existing, {"nodes": [], "edges": [], "viewport": {}}) is True


def test_empty_overwrite_allowed_when_server_already_empty():
    existing = json.dumps({"nodes": [], "edges": []})
    assert is_empty_overwrite(existing, {"nodes": [], "edges": []}) is False


def test_non_empty_incoming_not_blocked():
    existing = json.dumps({"nodes": [{"id": "n1"}], "edges": []})
    assert is_empty_overwrite(existing, {"nodes": [{"id": "n2"}], "edges": []}) is False


def test_name_only_update_not_empty_overwrite():
    existing = json.dumps({"nodes": [{"id": "n1"}]})
    assert is_empty_overwrite(existing, None) is False


def test_backup_roundtrip(tmp_path, monkeypatch):
    import services.canvas_save_guard as guard

    monkeypatch.setattr(guard, "_BACKUP_DIR", tmp_path)
    pid = "proj-test-1"
    payload = json.dumps({"nodes": [{"id": "a"}], "edges": []})
    write_nonempty_backup(pid, payload)
    restored = read_backup(pid)
    assert restored is not None
    assert restored["nodes"][0]["id"] == "a"
    # empty should not overwrite backup
    write_nonempty_backup(pid, json.dumps({"nodes": [], "edges": []}))
    restored2 = read_backup(pid)
    assert restored2["nodes"][0]["id"] == "a"
