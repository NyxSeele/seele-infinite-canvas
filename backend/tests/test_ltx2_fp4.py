"""LTX-2 fp4 workflow builder structure tests."""
from comfyui.client import (
    LTX2_CKPT,
    LTX2_GEMMA_ENCODER,
    VIDEO_FPS,
    build_ltx2_fp4_i2v_workflow,
    build_ltx2_fp4_t2v_workflow,
    ltx_video_length,
)

AUDIO_TYPES = {
    "LTXVAudioVAELoader",
    "LTXVEmptyLatentAudio",
    "LTXVAudioVAEDecode",
    "LTXVConcatAVLatent",
}


def test_build_ltx2_fp4_t2v_workflow_nodes():
    wf = build_ltx2_fp4_t2v_workflow(
        "a cat walking in the rain",
        "blurry",
        width=848,
        height=480,
        duration_sec=5,
        seed=42,
        model_filename=LTX2_CKPT,
    )
    assert wf["121"]["inputs"]["text"] == "a cat walking in the rain"
    assert wf["110"]["inputs"]["text"] == "blurry"
    assert wf["138"]["inputs"]["ckpt_name"] == LTX2_CKPT
    assert wf["99"]["inputs"]["text_encoder"] == LTX2_GEMMA_ENCODER
    assert wf["75"]["class_type"] == "SaveVideo"
    assert wf["108"]["inputs"]["length"] == ltx_video_length(5)
    assert wf["115"]["inputs"]["noise_seed"] == 42


def test_build_ltx2_fp4_required_node_types():
    wf = build_ltx2_fp4_t2v_workflow("probe", "neg", duration_sec=5)
    types = {node["class_type"] for node in wf.values()}
    for required in (
        "LTXAVTextEncoderLoader",
        "CheckpointLoaderSimple",
        "LTXVLatentUpsampler",
        "LoraLoaderModelOnly",
        "SaveVideo",
        "CreateVideo",
    ):
        assert required in types


def test_build_ltx2_fp4_frame_rate():
    wf = build_ltx2_fp4_t2v_workflow("probe", "neg", duration_sec=5)
    assert wf["107"]["inputs"]["frame_rate"] == float(VIDEO_FPS)
    assert wf["122"]["inputs"]["fps"] == float(VIDEO_FPS)


def test_build_ltx2_fp4_audio_true_keeps_av_nodes():
    wf = build_ltx2_fp4_t2v_workflow("probe", "neg", duration_sec=5, audio=True)
    types = {node["class_type"] for node in wf.values()}
    assert AUDIO_TYPES.issubset(types)
    assert isinstance(wf["122"]["inputs"].get("audio"), list)


def test_build_ltx2_fp4_audio_false_strips_av_nodes():
    wf = build_ltx2_fp4_t2v_workflow("probe", "neg", duration_sec=5, audio=False)
    types = {node["class_type"] for node in wf.values()}
    assert not (AUDIO_TYPES & types)
    assert "LTXVSeparateAVLatent" not in types
    assert wf["122"]["inputs"].get("audio") is None
    assert wf["113"]["inputs"]["latent_image"] == ["108", 0]
    assert wf["98"]["inputs"]["latent"] == ["108", 0]
    assert wf["119"]["inputs"]["latent_image"] == ["118", 0]
    assert wf["126"]["inputs"]["samples"] == ["119", 1]


def test_build_ltx2_fp4_i2v_workflow_nodes():
    wf = build_ltx2_fp4_i2v_workflow(
        "p",
        "n",
        "x.png",
        width=848,
        height=480,
        duration_sec=5,
        seed=7,
        model_filename=LTX2_CKPT,
    )
    assert wf["200"]["inputs"]["image"] == "x.png"
    assert wf["200"]["class_type"] == "LoadImage"
    assert wf["201"]["class_type"] == "ResizeImagesByLongerEdge"
    assert wf["202"]["class_type"] == "LTXVPreprocess"
    assert wf["203"]["class_type"] == "LTXVImgToVideoInplace"
    assert wf["204"]["class_type"] == "LTXVImgToVideoInplace"
    assert wf["109"]["inputs"]["video_latent"] == ["203", 0]
    assert wf["117"]["inputs"]["video_latent"] == ["204", 0]
    assert wf["203"]["inputs"]["latent"] == ["108", 0]
    assert wf["204"]["inputs"]["latent"] == ["118", 0]
    assert wf["121"]["inputs"]["text"] == "p"
    assert wf["115"]["inputs"]["noise_seed"] == 7


def test_build_ltx2_fp4_i2v_audio_false_uses_inplace_latents():
    wf = build_ltx2_fp4_i2v_workflow("p", "n", "x.png", audio=False)
    types = {node["class_type"] for node in wf.values()}
    assert not (AUDIO_TYPES & types)
    assert "203" in wf and "204" in wf
    assert wf["113"]["inputs"]["latent_image"] == ["203", 0]
    assert wf["98"]["inputs"]["latent"] == ["203", 0]
    assert wf["119"]["inputs"]["latent_image"] == ["204", 0]
    assert wf["126"]["inputs"]["samples"] == ["119", 1]
