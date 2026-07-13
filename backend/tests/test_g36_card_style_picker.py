"""G36 card camera picker static checks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "frontend/src/components/canvas/VideoGenerationNode.jsx"


def test_video_node_has_camera_defaults():
    src = NODE.read_text(encoding="utf-8")
    assert "CameraMotionPicker" in src
    assert "cameraMove" in src
    assert "shotScale" in src
    assert 'cameraMove || "auto"' in src or 'data.cameraMove || "auto"' in src
    assert 'shotScale || "auto"' in src or 'data.shotScale || "auto"' in src
    assert "gn2-camera-summary" in src


def test_generation_card_has_no_camera_picker():
    card = ROOT / "frontend/src/components/canvas/GenerationCardNode.jsx"
    assert "CameraMotionPicker" not in card.read_text(encoding="utf-8")
