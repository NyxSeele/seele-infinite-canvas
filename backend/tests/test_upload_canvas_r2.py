"""Canvas image R2 presign/register validation."""

import pytest
from fastapi import HTTPException

from routers.upload import (
    _assert_canvas_key,
    _validate_canvas_image_meta,
    _validate_client_dimensions,
)


def test_validate_canvas_image_meta_accepts_jpeg():
    assert _validate_canvas_image_meta("photo.jpg", "image/jpeg", 1024) == "image/jpeg"


def test_validate_canvas_image_meta_rejects_heic_extension():
    with pytest.raises(HTTPException) as exc:
        _validate_canvas_image_meta("photo.heic", "image/jpeg", 1024)
    assert exc.value.status_code == 400
    assert "HEIC" in exc.value.detail


def test_validate_canvas_image_meta_rejects_oversize():
    with pytest.raises(HTTPException) as exc:
        _validate_canvas_image_meta("big.jpg", "image/jpeg", 21 * 1024 * 1024)
    assert exc.value.status_code == 413


def test_assert_canvas_key_rejects_team_prefix():
    with pytest.raises(HTTPException) as exc:
        _assert_canvas_key("team/2026/07/foo.jpg")
    assert exc.value.status_code == 400


def test_assert_canvas_key_accepts_canvas_prefix():
    assert _assert_canvas_key("canvas/2026/07/foo.jpg") == "canvas/2026/07/foo.jpg"


def test_validate_client_dimensions_accepts_reasonable():
    assert _validate_client_dimensions(1920, 1080, object_size=500_000) == (1920, 1080)


def test_validate_client_dimensions_rejects_too_small_file():
    assert _validate_client_dimensions(4000, 3000, object_size=100) is None
