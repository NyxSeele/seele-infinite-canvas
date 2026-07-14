"""A4 镜数解析与裁剪。"""

from services.segment_duration import (
    clamp_segments_to_shot_count,
    parse_shots_target_from_text,
)


def test_parse_shots_target_explicit():
    assert parse_shots_target_from_text("雨夜重庆，3个镜头") == 3
    assert parse_shots_target_from_text("共 5 镜") == 5
    assert parse_shots_target_from_text("make 4 shots please") == 4
    assert parse_shots_target_from_text("没有镜数") is None


def test_clamp_segments_to_shot_count():
    segments = [
        {"shots": [{"id": "a", "duration": 8}, {"id": "b", "duration": 8}, {"id": "c", "duration": 8}]},
        {"shots": [{"id": "d", "duration": 8}, {"id": "e", "duration": 8}, {"id": "f", "duration": 8}]},
    ]
    out, warning = clamp_segments_to_shot_count(segments, 3)
    assert warning
    flat = [s for seg in out for s in seg["shots"]]
    assert len(flat) == 3
    assert [s["id"] for s in flat] == ["a", "b", "c"]
