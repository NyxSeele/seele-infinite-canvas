"""新版 backlog 第七节验收：后端可自动覆盖项 + 单线程阶段提示。"""

from services.agent_service import _production_stage_hint
from services.export_service import _row_storyboard_url, _row_video_url


def test_production_stage_skips_mandatory_split_beats():
    script = {
        "id": "st1",
        "rows_summary": [
            {
                "id": "row1",
                "shot_number": 1,
                "has_beats": False,
                "storyboard_ready": False,
                "direct_image_ready": False,
            }
        ],
    }
    stage, hint = _production_stage_hint(script)
    assert stage == "generate_storyboard"
    assert "split_shot_beats" not in hint
    assert "无需先拆分节拍" in hint


def test_production_stage_shot1_storyboard_ready_goes_to_video():
    """镜1 有分镜无视频 → generate_video，禁止跳到镜2 出图。"""
    script = {
        "id": "st1",
        "rows_summary": [
            {
                "id": "row1",
                "shot_number": 1,
                "has_beats": True,
                "storyboard_ready": True,
                "direct_image_ready": True,
                "has_video": False,
            },
            {
                "id": "row2",
                "shot_number": 2,
                "has_beats": False,
                "storyboard_ready": False,
                "direct_image_ready": False,
                "has_video": False,
            },
        ],
    }
    stage, hint = _production_stage_hint(script)
    assert stage == "generate_video"
    assert "row_id=\"row1\"" in hint
    assert "generate_storyboard" not in hint


def test_production_stage_shot1_video_generating_blocks_shot2():
    """镜1 视频生成中且镜2 无图 → wait_video，禁止镜2 出图。"""
    script = {
        "id": "st1",
        "rows_summary": [
            {
                "id": "row1",
                "shot_number": 1,
                "storyboard_ready": True,
                "direct_image_ready": True,
                "has_video": False,
                "video_generating": True,
            },
            {
                "id": "row2",
                "shot_number": 2,
                "storyboard_ready": False,
                "direct_image_ready": False,
                "has_video": False,
            },
        ],
    }
    stage, hint = _production_stage_hint(script)
    assert stage == "wait_video"
    assert "单画布单线程" in hint
    assert "generate_storyboard" not in hint


def test_production_stage_shot1_image_generating_blocks():
    script = {
        "id": "st1",
        "rows_summary": [
            {
                "id": "row1",
                "shot_number": 1,
                "storyboard_ready": False,
                "direct_image_ready": False,
                "image_generating": True,
            },
            {
                "id": "row2",
                "shot_number": 2,
                "storyboard_ready": False,
                "direct_image_ready": False,
            },
        ],
    }
    stage, hint = _production_stage_hint(script)
    assert stage == "wait_storyboard"
    assert "generate_storyboard" not in hint


def test_row_storyboard_url_prefers_direct():
    row = {
        "directResultUrl": "https://example.com/direct.png",
        "keyframes": [{"resultUrl": "https://example.com/beat.png"}],
    }
    assert _row_storyboard_url(row) == "https://example.com/direct.png"


def test_row_storyboard_url_from_beat_card():
    row = {"beatCardNodeId": "bc1"}
    nodes = [
        {
            "id": "bc1",
            "type": "script-beat-card",
            "data": {"keyframes": [{"resultUrl": "https://example.com/kf.png"}]},
        }
    ]
    assert _row_storyboard_url(row, nodes) == "https://example.com/kf.png"


def test_row_video_url_direct_lane():
    row = {"directVideoGenNodeId": "v1"}
    nodes = [
        {
            "id": "v1",
            "type": "video-gen",
            "data": {"status": "completed", "videoUrl": "https://example.com/v.mp4"},
        }
    ]
    assert _row_video_url(row, nodes) == "https://example.com/v.mp4"
