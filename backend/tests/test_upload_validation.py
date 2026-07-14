"""上传校验与媒体鉴权辅助函数测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.upload_validation import normalize_image_upload, validate_image_upload


def test_validate_image_upload_png():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    assert validate_image_upload(png, "image/png") == "image/png"


def test_validate_image_upload_empty_declared_mime():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    assert validate_image_upload(png, None) == "image/png"
    assert validate_image_upload(png, "") == "image/png"


def test_normalize_image_upload_empty_declared_mime():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    out, mime = normalize_image_upload(png, "")
    assert mime == "image/png"
    assert out == png


def test_validate_image_upload_rejects_garbage():
    with pytest.raises(HTTPException) as exc:
        validate_image_upload(b"not an image", "image/png")
    assert exc.value.status_code == 400
