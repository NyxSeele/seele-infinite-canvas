"""Tests for project generation memory service."""

from __future__ import annotations

from services.generation_memory_service import (
    apply_image_defaults_from_memory,
    parse_generation_memory,
    record_feedback_routing_hint,
    update_project_generation_memory,
)


class _Project:
    generation_memory = None


def test_parse_generation_memory_defaults():
    mem = parse_generation_memory(None)
    assert mem["preferred_video_model"] == "wan-2.6"
    assert mem["routing_hints"] == {}


def test_update_and_feedback_hints():
    project = _Project()
    update_project_generation_memory(
        project,
        {"protagonist_face_url": "/uploads/images/face.png"},
    )
    mem = parse_generation_memory(project.generation_memory)
    assert mem["protagonist_face_url"] == "/uploads/images/face.png"

    record_feedback_routing_hint(project, model_id="ltx2-fp4", rating=1)
    mem2 = parse_generation_memory(project.generation_memory)
    assert mem2["routing_hints"]["ltx2-fp4"] == 1


def test_feedback_demotes_preferred_video_model_after_repeated_negatives():
    project = _Project()
    update_project_generation_memory(project, {"preferred_video_model": "ltx2-fp4"})
    for _ in range(3):
        record_feedback_routing_hint(project, model_id="ltx2-fp4", rating=0)
    mem = parse_generation_memory(project.generation_memory)
    assert mem["routing_hints"]["ltx2-fp4"] == -3
    assert mem["preferred_video_model"] == "wan-i2v"
    memory = {"protagonist_face_url": "/uploads/face.png", "preferred_image_model": "flux-pulid"}
    ref, refs, model = apply_image_defaults_from_memory(
        memory,
        model_id="qwen-image",
        reference_image=None,
        reference_images=[],
    )
    assert ref == "/uploads/face.png"
    assert refs == ["/uploads/face.png"]
    assert model == "flux-pulid"
