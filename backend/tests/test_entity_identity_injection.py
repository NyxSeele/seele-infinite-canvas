"""identity 门禁与参考图注入（DramaClaw 选项1 自写实现）"""

import pytest

from services.entity_refs import (
    MissingIdentityError,
    build_entity_ref_audit,
    entity_lines_for_prompt,
    identity_lock_lines,
    pick_ref_urls,
    resolve_cast_refs_for_row,
    validate_row_identity,
)


def _cast(name: str, **kwargs):
    return {
        "name": name,
        "type": "character",
        "identityId": kwargs.get("identity_id", f"{name.lower()}_default"),
        "faceUrl": kwargs.get("face_url"),
        "threeViewUrl": kwargs.get("three_view_url"),
        "costumeUrl": kwargs.get("costume_url"),
        "imageUrl": kwargs.get("image_url"),
        **{k: v for k, v in kwargs.items() if k not in ("identity_id", "face_url", "three_view_url", "costume_url", "image_url")},
    }


def test_validate_passes_when_no_character_refs():
    validate_row_identity({"prompt": "空镜，夕阳"}, [_cast("Alice", face_url="http://a/1.png")])


def test_validate_missing_identity_when_referenced_without_images():
    lib = [_cast("Alice", identity_id="alice_default")]
    row = {"identityIds": ["alice_default"], "prompt": "Alice 走进房间"}
    with pytest.raises(MissingIdentityError) as exc:
        validate_row_identity(row, lib)
    assert "alice_default" in exc.value.identity_ids
    assert "Alice" in exc.value.names


def test_validate_passes_with_three_view_url():
    lib = [_cast("Alice", three_view_url="http://a/3view.png")]
    row = {"identityIds": ["alice_default"]}
    validate_row_identity(row, lib)


def test_pick_ref_urls_priority():
    entry = _cast(
        "Bob",
        three_view_url="http://t",
        face_url="http://f",
        costume_url="http://c",
        image_url="http://i",
    )
    assert pick_ref_urls(entry) == ["http://t", "http://f", "http://c"]


def test_identity_lock_lines_contains_constraint():
    lib = [_cast("Alice", face_url="http://a/f.png")]
    row = {"identityIds": ["alice_default"]}
    resolved = resolve_cast_refs_for_row(row, lib)
    text = identity_lock_lines(resolved)
    assert "alice_default" in text
    assert "跨镜头" in text


def test_entity_lines_for_prompt_with_row_binding():
    lib = [_cast("Alice", three_view_url="http://a/3.png")]
    row = {"identityIds": ["alice_default"], "prompt": "test"}
    pkg = entity_lines_for_prompt(lib, [], row)
    assert "alice_default" in pkg


def test_same_identity_stable_ref_urls_across_rows():
    lib = [_cast("Alice", three_view_url="http://a/3.png", face_url="http://a/f.png")]
    row_a = {"identityIds": ["alice_default"], "shot_number": 1}
    row_b = {"identityIds": ["alice_default"], "shot_number": 2}
    audit_a = build_entity_ref_audit(resolve_cast_refs_for_row(row_a, lib))
    audit_b = build_entity_ref_audit(resolve_cast_refs_for_row(row_b, lib))
    assert audit_a == audit_b
    assert audit_a[0]["urls"] == ["http://a/3.png", "http://a/f.png"]


def test_text_match_triggers_validation():
    lib = [_cast("Mia", identity_id="mia_default")]
    row = {"prompt": "Mia 在雨中奔跑"}
    with pytest.raises(MissingIdentityError):
        validate_row_identity(row, lib)
