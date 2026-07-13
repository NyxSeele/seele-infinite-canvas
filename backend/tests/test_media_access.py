"""media_access 参考图路径解析测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services import media_access


def _admin_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.role = "admin"
    return user


def test_resolve_image_reference_path_comfy_view():
    output_dir = Path("/root/autodl-tmp/ComfyUI/output")
    candidates = sorted(output_dir.glob("*.png"))
    if not candidates:
        pytest.skip("no ComfyUI output png for view resolution test")
    filename = candidates[0].name
    db = MagicMock()
    user = _admin_user()

    path = media_access.resolve_image_reference_path(
        db,
        user,
        f"/api/view?filename={filename}",
    )
    assert path.is_file()
    assert path.name == filename


def test_resolve_image_reference_path_uploads(tmp_path, monkeypatch):
    uploads_root = tmp_path / "uploads"
    image_rel = "images/test_probe_ref.png"
    image_path = uploads_root / image_rel
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    monkeypatch.setattr(media_access, "UPLOAD_ROOT", uploads_root)
    db = MagicMock()
    user = _admin_user()

    path = media_access.resolve_image_reference_path(
        db,
        user,
        f"/api/uploads/{image_rel}",
    )
    assert path.resolve() == image_path.resolve()


def test_resolve_image_reference_path_rejects_invalid_path():
    db = MagicMock()
    user = _admin_user()

    with pytest.raises(HTTPException) as exc:
        media_access.resolve_image_reference_path(db, user, "/not-a-valid-ref")
    assert exc.value.status_code == 400
    assert exc.value.detail == "参考图无效或无权访问"
    assert exc.value.detail != "非法上传路径"


def test_normalize_media_reference_url_strips_host_and_mt():
    out = media_access.normalize_media_reference_url(
        "http://127.0.0.1:7788/api/view?filename=ComfyUI_00001_.mp4&mt=abc"
    )
    assert out.startswith("/api/view?")
    assert "filename=ComfyUI_00001_.mp4" in out
    assert "mt=" not in out


def test_resolve_video_source_absolute_api_view_url():
    output_dir = Path("/root/autodl-tmp/ComfyUI/output")
    candidates = sorted(output_dir.glob("*.mp4")) or sorted(output_dir.glob("*.png"))
    if not candidates:
        pytest.skip("no ComfyUI output for enhance view resolution test")
    filename = candidates[0].name
    db = MagicMock()
    user = _admin_user()
    path = media_access.resolve_video_source_for_enhance(
        db,
        user,
        f"http://127.0.0.1:7788/api/view?filename={filename}&mt=deadbeef",
    )
    assert path is not None
    assert path.is_file()
    assert path.name == filename


def test_resolve_video_source_rejects_bare_filename():
    db = MagicMock()
    user = _admin_user()
    with pytest.raises(HTTPException) as exc:
        media_access.resolve_video_source_for_enhance(db, user, "00008_.mp4")
    assert exc.value.status_code == 400
