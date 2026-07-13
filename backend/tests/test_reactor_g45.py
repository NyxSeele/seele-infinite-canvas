"""G45 ReActor 视频逐帧：schema / 工作流结构 / 临时目录清理（无 GPU）。"""

from pathlib import Path

from providers.comfyui import build_reactor_frame_workflow
from schemas.tasks import CanvasVideoRequest
from services.reactor_video import cleanup_tmp_reactor, tmp_reactor_dir


def test_canvas_video_request_accepts_use_reactor():
    body = CanvasVideoRequest(
        model="wan-2.6",
        prompt="a person walking",
        node_id="v1",
        use_reactor=True,
        reactor_face_image="/api/uploads/images/face.png",
    )
    assert body.use_reactor is True
    assert body.reactor_face_image.endswith("face.png")


def test_build_reactor_frame_workflow_structure():
    wf = build_reactor_frame_workflow(
        frame_filename="frame.png",
        face_filename="face.png",
    )
    assert wf["1"]["class_type"] == "LoadImage"
    assert wf["2"]["class_type"] == "LoadImage"
    assert wf["60"]["class_type"] == "ReActorFaceSwap"
    assert wf["60"]["inputs"]["input_image"] == ["1", 0]
    assert wf["60"]["inputs"]["source_image"] == ["2", 0]
    assert wf["60"]["inputs"]["swap_model"] == "inswapper_128.onnx"
    assert wf["9"]["inputs"]["images"] == ["60", 0]


def test_tmp_reactor_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr("services.reactor_video.TMP_ROOT", tmp_path)
    task_id = "probe-cleanup-1"
    d = tmp_reactor_dir(task_id)
    d.mkdir(parents=True)
    (d / "frame_000001.png").write_bytes(b"x")
    assert d.is_dir()
    cleanup_tmp_reactor(task_id)
    assert not d.exists()
