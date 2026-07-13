"""Tests for perceptual hash consistency helpers."""
from io import BytesIO

from PIL import Image

from services.image_consistency import check_consistency, hamming, phash


def test_phash_identical_images_distance_zero():
    img = Image.new("RGB", (64, 64), color=(128, 64, 32))
    assert phash(img) == phash(img.copy())
    assert hamming(phash(img), phash(img)) == 0


def test_check_consistency_empty_urls():
    result = check_consistency([], token="unused")
    assert result["consistency_phash"] == []
    assert result["image_count"] == 0


def test_hamming_known_bits():
    assert hamming(0b11110000, 0b11110000) == 0
    assert hamming(0b11110000, 0b00001111) == 8
