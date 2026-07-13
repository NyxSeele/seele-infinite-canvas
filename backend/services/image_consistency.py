"""Perceptual hash helpers for shot-to-shot visual consistency probes."""
from __future__ import annotations

import io
from typing import Any

import httpx
from PIL import Image


def phash(img: Image.Image, size: int = 8) -> int:
    gray = img.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return int(bits, 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def check_consistency(
    image_urls: list[str],
    token: str,
    *,
    base_url: str = "http://127.0.0.1:7788",
    threshold: int = 14,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """
    Compute phash Hamming distance between adjacent shot images.
    distance > threshold is flagged as drift (observation only in v1).
    """
    headers = {"Authorization": f"Bearer {token}"}
    hashes: list[int] = []
    fetched: list[str] = []

    with httpx.Client(timeout=timeout) as client:
        for raw_url in image_urls:
            if not raw_url:
                continue
            url = raw_url if raw_url.startswith("http") else f"{base_url.rstrip('/')}{raw_url}"
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            hashes.append(phash(img))
            fetched.append(url)

    pairs: list[dict[str, Any]] = []
    for i in range(len(hashes) - 1):
        distance = hamming(hashes[i], hashes[i + 1])
        pairs.append(
            {
                "pair": f"{i + 1:03d}-{i + 2:03d}",
                "distance": distance,
                "drifted": distance > threshold,
            }
        )

    return {
        "consistency_phash": pairs,
        "threshold": threshold,
        "image_count": len(hashes),
        "hashes": hashes,
        "fetched_urls": fetched,
    }
