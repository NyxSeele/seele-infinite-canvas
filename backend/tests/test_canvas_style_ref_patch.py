"""canvas_style_ref：定位 video-gen 节点并 patch styleReference。"""

import pytest
from fastapi import HTTPException

from models.canvas_project import CanvasProject
from services.canvas_style_ref import (
    clear_video_node_style_reference,
    find_node,
    find_script_row,
    get_video_node_style_reference,
    load_canvas_data,
    patch_video_node_style_reference,
    resolve_video_node_for_shot,
)

SAMPLE_REF = {
    "color_tone": "desaturated cold gray-green",
    "lighting": "side backlight",
    "shot_language": "close-ups",
    "atmosphere": "suspense",
    "style_keywords": ["noir", "cinematic"],
    "source": "user_upload",
    "display_summary": "低饱和冷灰绿调",
}


def _make_project(canvas_data: dict) -> CanvasProject:
    import json

    return CanvasProject(
        id="proj-1",
        user_id=1,
        name="test",
        data=json.dumps(canvas_data, ensure_ascii=False),
        version=1,
    )


def _two_video_nodes_canvas():
    return {
        "nodes": [
            {"id": "vid-a", "type": "video-gen", "data": {"label": "A"}},
            {"id": "vid-b", "type": "video-gen", "data": {"label": "B"}},
        ],
        "edges": [],
    }


def _script_table_canvas():
    return {
        "nodes": [
            {
                "id": "table-1",
                "type": "script-table",
                "data": {
                    "rows": [
                        {
                            "id": "row-1",
                            "shotNumber": 1,
                            "videoGenNodeId": "vid-a",
                        },
                        {
                            "id": "row-2",
                            "shotNumber": 2,
                            "videoGenNodeId": "vid-b",
                        },
                    ]
                },
            },
            {"id": "vid-a", "type": "video-gen", "data": {}},
            {"id": "vid-b", "type": "video-gen", "data": {}},
        ],
        "edges": [],
    }


def test_find_node_and_get_style_reference():
    canvas = _two_video_nodes_canvas()
    assert find_node(canvas, "vid-a") is not None
    assert get_video_node_style_reference(canvas, "vid-a") is None


def test_patch_only_target_node():
    project = _make_project(_two_video_nodes_canvas())
    patch_video_node_style_reference(project, "vid-a", SAMPLE_REF)
    canvas = load_canvas_data(project)
    assert get_video_node_style_reference(canvas, "vid-a") == SAMPLE_REF
    assert get_video_node_style_reference(canvas, "vid-b") is None


def test_clear_node_style_reference():
    project = _make_project(_two_video_nodes_canvas())
    patch_video_node_style_reference(project, "vid-a", SAMPLE_REF)
    clear_video_node_style_reference(project, "vid-a")
    canvas = load_canvas_data(project)
    assert get_video_node_style_reference(canvas, "vid-a") is None


def test_resolve_video_node_for_shot():
    canvas = _script_table_canvas()
    node_id = resolve_video_node_for_shot(canvas, "table-1", "row-1")
    assert node_id == "vid-a"


def test_patch_syncs_script_row_mirror():
    project = _make_project(_script_table_canvas())
    patch_video_node_style_reference(
        project,
        "vid-a",
        SAMPLE_REF,
        script_table_node_id="table-1",
        row_id="row-1",
    )
    canvas = load_canvas_data(project)
    found = find_script_row(canvas, "table-1", "row-1")
    assert found is not None
    _, row = found
    assert row.get("styleReference") == SAMPLE_REF
    assert get_video_node_style_reference(canvas, "vid-b") is None


def test_resolve_shot_missing_video_node_raises():
    canvas = {
        "nodes": [
            {
                "id": "table-1",
                "type": "script-table",
                "data": {"rows": [{"id": "row-1", "shotNumber": 1}]},
            }
        ],
        "edges": [],
    }
    with pytest.raises(HTTPException) as exc:
        resolve_video_node_for_shot(canvas, "table-1", "row-1")
    assert exc.value.status_code == 400
