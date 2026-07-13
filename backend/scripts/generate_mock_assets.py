#!/usr/bin/env python3
"""生成 Mock 占位图与占位视频到 backend/assets/mock/，并同步探针参考图到 uploads/images/。"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BACKEND_DIR / "assets" / "mock"
UPLOAD_IMAGES_DIR = BACKEND_DIR / "uploads" / "images"

PALETTES = [
    (0x2D, 0x3A, 0x8C),
    (0x1A, 0x73, 0x6E),
    (0x7B, 0x2C, 0xBF),
    (0xC4, 0x4D, 0x34),
    (0x2E, 0x7D, 0x32),
    (0x5C, 0x6B, 0x73),
]

# 与 _entity_library_probe 等约定的文件名一致
PROBE_REF_FILES = (
    ("mock-cast-ref.jpg", PALETTES[0]),
    ("mock-scene-ref.jpg", PALETTES[1]),
)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _write_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    raw = b""
    r, g, b = rgb
    row = bytes([r, g, b]) * width
    for _ in range(height):
        raw += b"\x00" + row
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", ihdr)
    png += _png_chunk(b"IDAT", compressed)
    png += _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def _write_jpeg_via_pillow(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    img = Image.new("RGB", (width, height), rgb)
    draw = ImageDraw.Draw(img)
    label = "MOCK"
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((width - tw) // 2, (height - th) // 2), label, fill=(255, 255, 255, 180), font=font)
    img.save(path, format="JPEG", quality=85)
    return True


def _write_placeholder_image(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    jpg_path = path.with_suffix(".jpg")
    if _write_jpeg_via_pillow(jpg_path, width, height, rgb):
        return
    png_path = path.with_suffix(".png")
    _write_png(png_path, width, height, rgb)


def _write_jpeg_required(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    """探针路径要求 .jpg；依赖 Pillow（backend venv 已装）。"""
    if not _write_jpeg_via_pillow(path, width, height, rgb):
        raise RuntimeError(f"无法写入 JPEG（需 Pillow）: {path}")


def _ffmpeg_executable() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _write_minimal_mp4(path: Path) -> None:
    ffmpeg = _ffmpeg_executable() or "ffmpeg"
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x2D3A8C:s=848x480:d=3",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    # 兜底：写入最小 ftyp 头（不可播放，但保证文件存在）
    path.write_bytes(
        b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free"
    )


def ensure_probe_ref_images(width: int = 960, height: int = 540) -> list[Path]:
    """将 mock-cast-ref.jpg / mock-scene-ref.jpg 写入 uploads/images/（探针约定路径）。"""
    UPLOAD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for idx, (filename, rgb) in enumerate(PROBE_REF_FILES, start=1):
        dest = UPLOAD_IMAGES_DIR / filename
        src_jpg = ASSETS_DIR / f"placeholder_{idx:02d}.jpg"
        if src_jpg.is_file():
            shutil.copy2(src_jpg, dest)
        else:
            _write_jpeg_required(dest, width, height, rgb)
        written.append(dest)
        print(f" wrote {dest}")
    return written


def main() -> int:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    width, height = 960, 540
    for idx, rgb in enumerate(PALETTES, start=1):
        out = ASSETS_DIR / f"placeholder_{idx:02d}.jpg"
        _write_placeholder_image(out, width, height, rgb)
        print(f" wrote {out.with_suffix('.jpg') if out.with_suffix('.jpg').exists() else out.with_suffix('.png')}")
    for idx in (1, 2):
        out = ASSETS_DIR / f"placeholder_video_{idx:02d}.mp4"
        _write_minimal_mp4(out)
        print(f" wrote {out}")
    ensure_probe_ref_images(width, height)
    return 0


if __name__ == "__main__":
    sys.exit(main())
