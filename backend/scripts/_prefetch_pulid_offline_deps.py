#!/usr/bin/env python3
"""预下载 PuLID 离线依赖到数据盘（避免系统盘 /root/.cache 与运行时联网超时）。"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

from huggingface_hub import snapshot_download

DATA_HF_HOME = Path("/root/autodl-tmp/.cache/huggingface")
DATA_HF_HUB = DATA_HF_HOME / "hub"
FACEXLIB_DIR = DATA_HF_HUB / "facexlib"
ANTELOPE_DIR = DATA_HF_HUB / "insightface" / "models" / "antelopev2"
COMFY_FACEXLIB = Path("/root/autodl-tmp/ComfyUI/models/facexlib")
COMFY_ANTELOPE = Path("/root/autodl-tmp/ComfyUI/models/insightface/models/antelopev2")
COMFY_FACE_DET = Path("/root/autodl-tmp/ComfyUI/models/facedetection/detection_Resnet50_Final.pth")

# FaceRestoreHelper 初始化会拉 parsenet；PuLID pipeline 还会用 bisenet + retinaface 检测权重。
FACEXLIB_URLS = {
    "detection_Resnet50_Final.pth": [
        "https://ghfast.top/https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth",
        "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth",
    ],
    "parsing_bisenet.pth": [
        "https://ghfast.top/https://github.com/xinntao/facexlib/releases/download/v0.2.0/parsing_bisenet.pth",
        "https://github.com/xinntao/facexlib/releases/download/v0.2.0/parsing_bisenet.pth",
    ],
    "parsing_parsenet.pth": [
        "https://ghfast.top/https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth",
        "https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth",
    ],
}

FACEXLIB_MIN_BYTES = {
    "detection_Resnet50_Final.pth": 100_000_000,
    "parsing_bisenet.pth": 50_000_000,
    "parsing_parsenet.pth": 80_000_000,
}

HF_MIRRORS = [
    "https://hf-mirror.com",
    "https://huggingface.co",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pick_fastest_hf_mirror() -> str:
    probe = "DIAMONIK7777/antelopev2/resolve/main/genderage.onnx"
    best_url = HF_MIRRORS[0]
    best_bps = -1.0
    tmp = DATA_HF_HUB / "_mirror_probe.bin"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    for base in HF_MIRRORS:
        url = f"{base}/{probe}"
        t0 = time.time()
        try:
            urllib.request.urlretrieve(url, tmp)
            elapsed = max(time.time() - t0, 0.001)
            bps = tmp.stat().st_size / elapsed
            print(f"mirror probe {base}: {bps/1024:.1f} KiB/s")
            if bps > best_bps:
                best_bps = bps
                best_url = base
        except Exception as exc:
            print(f"mirror probe {base}: FAIL ({exc})")
        finally:
            tmp.unlink(missing_ok=True)
    print(f"selected HF mirror: {best_url}")
    return best_url


def _cleanup_partials(directory: Path) -> None:
    if not directory.is_dir():
        return
    for partial in directory.glob("*.partial"):
        partial.unlink(missing_ok=True)
        print(f"removed partial {partial.name}")


def _download_first(dest: Path, urls: list[str], *, min_bytes: int = 1) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        return
    if dest.is_file():
        dest.unlink(missing_ok=True)
    last_err: Exception | None = None
    for url in urls:
        t0 = time.time()
        try:
            print(f"downloading {url} -> {dest}")
            urllib.request.urlretrieve(url, dest)
            print(f"ok {dest.name} {dest.stat().st_size} bytes in {time.time()-t0:.1f}s")
            return
        except Exception as exc:
            last_err = exc
            dest.unlink(missing_ok=True)
            print(f"failed {url}: {exc}")
    raise RuntimeError(f"all mirrors failed for {dest.name}") from last_err


def _sync_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file() and dst.stat().st_size == src.stat().st_size:
        return
    shutil.copy2(src, dst)


def _ensure_facexlib() -> None:
    FACEXLIB_DIR.mkdir(parents=True, exist_ok=True)
    COMFY_FACEXLIB.mkdir(parents=True, exist_ok=True)
    _cleanup_partials(COMFY_FACEXLIB)
    if COMFY_FACE_DET.is_file() and not (FACEXLIB_DIR / "detection_Resnet50_Final.pth").is_file():
        shutil.copy2(COMFY_FACE_DET, FACEXLIB_DIR / "detection_Resnet50_Final.pth")
    for name, urls in FACEXLIB_URLS.items():
        min_bytes = FACEXLIB_MIN_BYTES.get(name, 1)
        target = FACEXLIB_DIR / name
        _download_first(target, urls, min_bytes=min_bytes)
        comfy_target = COMFY_FACEXLIB / name
        _sync_file(target, comfy_target)
        print(f"facexlib ok {name} bytes={target.stat().st_size}")


def _ensure_antelopev2(hf_endpoint: str) -> None:
    required = [
        "1k3d68.onnx",
        "2d106det.onnx",
        "genderage.onnx",
        "glintr100.onnx",
        "scrfd_10g_bnkps.onnx",
    ]
    missing = [n for n in required if not (ANTELOPE_DIR / n).is_file()]
    if missing:
        print(f"downloading antelopev2 -> {ANTELOPE_DIR} missing={missing}")
        os.environ["HF_HOME"] = str(DATA_HF_HOME)
        os.environ["HF_HUB_CACHE"] = str(DATA_HF_HUB)
        os.environ["HF_ENDPOINT"] = hf_endpoint
        snapshot_download("DIAMONIK7777/antelopev2", local_dir=str(ANTELOPE_DIR))
    COMFY_ANTELOPE.mkdir(parents=True, exist_ok=True)
    for name in required:
        src = ANTELOPE_DIR / name
        if not src.is_file():
            raise FileNotFoundError(f"missing antelopev2 file: {src}")
        dst = COMFY_ANTELOPE / name
        if not dst.is_file():
            shutil.copy2(src, dst)
        print(f"antelopev2 ok {name} sha256={_sha256(src)[:12]}...")


def _verify_all() -> None:
    for name, min_bytes in FACEXLIB_MIN_BYTES.items():
        for root in (FACEXLIB_DIR, COMFY_FACEXLIB):
            path = root / name
            if not path.is_file() or path.stat().st_size < min_bytes:
                raise FileNotFoundError(f"facexlib incomplete: {path}")
    antelope_names = [
        "1k3d68.onnx",
        "2d106det.onnx",
        "genderage.onnx",
        "glintr100.onnx",
        "scrfd_10g_bnkps.onnx",
    ]
    for name in antelope_names:
        for root in (ANTELOPE_DIR, COMFY_ANTELOPE):
            path = root / name
            if not path.is_file() or path.stat().st_size < 1_000_000:
                raise FileNotFoundError(f"antelopev2 incomplete: {path}")


def main() -> int:
    DATA_HF_HUB.mkdir(parents=True, exist_ok=True)
    mirror = _pick_fastest_hf_mirror()
    _ensure_facexlib()
    _ensure_antelopev2(mirror)
    _verify_all()
    print(f"PuLID offline deps ready on data disk: {DATA_HF_HUB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
