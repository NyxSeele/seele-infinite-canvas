"""G40 ReActor face-swap workflow structure tests (no GPU)."""

from pathlib import Path

from providers.comfyui import _build_flux_pulid_workflow
from schemas.tasks import CanvasImageRequest

PROFILE = {
    "workflow_type": "flux_pulid",
    "generation_defaults": {
        "steps": 20,
        "sampler_name": "euler",
        "scheduler": "simple",
        "pulid_weight": 0.8,
        "guidance": 3.5,
    },
}


def test_canvas_image_request_accepts_use_reactor():
    body = CanvasImageRequest(
        model="flux-pulid",
        prompt="portrait",
        node_id="n1",
        use_reactor=True,
        reference_image="/api/uploads/images/face.png",
    )
    assert body.use_reactor is True


def test_build_flux_pulid_with_reactor_nodes():
    wf = _build_flux_pulid_workflow(
        "portrait of a woman",
        "svdq-int4_r32-flux.1-dev.safetensors",
        1024,
        1024,
        1,
        PROFILE,
        reference_face_image="face.png",
        use_reactor=True,
    )
    assert wf["60"]["class_type"] == "ReActorFaceSwap"
    assert wf["60"]["inputs"]["source_image"] == ["49", 0]
    assert wf["60"]["inputs"]["input_image"] == ["8", 0]
    assert wf["60"]["inputs"]["swap_model"] == "inswapper_128.onnx"
    assert wf["9"]["inputs"]["images"] == ["60", 0]
    assert Path(
        "/root/autodl-tmp/AIStudio/backend/comfyui/workflows/flux_pulid_reactor.json"
    ).is_file() or (
        Path(__file__).resolve().parents[1]
        / "comfyui"
        / "workflows"
        / "flux_pulid_reactor.json"
    ).is_file()


def test_build_flux_pulid_without_reactor():
    wf = _build_flux_pulid_workflow(
        "portrait",
        "svdq-int4_r32-flux.1-dev.safetensors",
        512,
        512,
        2,
        PROFILE,
        reference_face_image="face.png",
        use_reactor=False,
    )
    types = {n["class_type"] for n in wf.values()}
    assert "ReActorFaceSwap" not in types
    assert wf["9"]["inputs"]["images"] == ["8", 0]
    assert "NunchakuFluxPuLIDApplyV2" in types
