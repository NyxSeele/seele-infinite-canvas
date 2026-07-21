"""
将 model_registry.COMFYUI_LOCAL_PROVIDERS 与权重落盘状态同步到 registered_models。

启动时调用，避免改 model_registry 后 DB 仍指向旧 comfyui_file（如 int4→fp4）。
运维脚本 scripts/_enable_gpu_models.py 复用本模块。
"""

from __future__ import annotations

from pathlib import Path

from db.session import SessionLocal
from model_registry import COMFYUI_LOCAL_PROVIDERS, COMFYUI_PROVIDER_MAP, VIDEO_ENHANCE_SEEDVR2_ID
from models import RegisteredModel

COMFY_MODELS_ROOT = Path("/root/autodl-tmp/ComfyUI/models")
SEEDVR_ROOT = COMFY_MODELS_ROOT / "SEEDVR2"
SEEDVR_VAE = SEEDVR_ROOT / "ema_vae_fp16.safetensors"
SEEDVR_7B = SEEDVR_ROOT / "seedvr2_ema_7b_fp16.safetensors"
SEEDVR_7B_SHARP = SEEDVR_ROOT / "seedvr2_ema_7b_sharp_fp16.safetensors"
SEEDVR_3B = SEEDVR_ROOT / "seedvr2_ema_3b_fp8_e4m3fn.safetensors"

# 已从产品下架：启动时强制禁用 DB 残留行
FORCE_DISABLE_IDS = frozenset({
    "hunyuan-video",
    "hunyuan-video-1.5",
    "qwen-image-edit-2509",
    "ltx2-i2av",
    "flux-dev",
    "flux-schnell",
})

# 仅维护权重路径；元数据（display_name / comfyui_file 等）以 COMFYUI_LOCAL_PROVIDERS 为准。
MODEL_WEIGHT_REQUIREMENTS: dict[str, dict] = {
    "wan-2.6": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
        ],
    },
    "wan-i2v": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        ],
    },
    "wan-fun-inpaint": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors",
        ],
    },
    "hidream": {
        "weight_paths": [
            COMFY_MODELS_ROOT / "diffusion_models/hidream_i1_dev_fp8.safetensors",
        ],
    },
    "flux-pulid": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/svdq-fp4_r32-flux.1-dev.safetensors",
            COMFY_MODELS_ROOT / "pulid/pulid_flux_v0.9.1.safetensors",
            COMFY_MODELS_ROOT / "clip/EVA02_CLIP_L_336_psz14_s6B.pt",
        ],
    },
    "qwen-image": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/svdq-fp4_r128-qwen-image-lightningv1.0-4steps.safetensors",
            COMFY_MODELS_ROOT / "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
            COMFY_MODELS_ROOT / "vae/qwen_image_vae.safetensors",
        ],
    },
    "qwen-image-edit": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors",
            COMFY_MODELS_ROOT
            / "loras/qwen-image-edit-2511-multiple-angles-lora.safetensors",
            COMFY_MODELS_ROOT
            / "loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
            COMFY_MODELS_ROOT / "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
            COMFY_MODELS_ROOT / "vae/qwen_image_vae.safetensors",
        ],
        "min_bytes": {
            COMFY_MODELS_ROOT
            / "diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors": 15_000_000_000,
        },
    },
    "qwen-image-restore": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors",
            COMFY_MODELS_ROOT
            / "loras/qwen-image-edit-2511-multiple-angles-lora.safetensors",
            COMFY_MODELS_ROOT
            / "loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
            COMFY_MODELS_ROOT / "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
            COMFY_MODELS_ROOT / "vae/qwen_image_vae.safetensors",
        ],
        "min_bytes": {
            COMFY_MODELS_ROOT
            / "diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors": 15_000_000_000,
        },
    },
    "qwen-image-material": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors",
            COMFY_MODELS_ROOT
            / "loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
            COMFY_MODELS_ROOT / "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
            COMFY_MODELS_ROOT / "vae/qwen_image_vae.safetensors",
        ],
        "min_bytes": {
            COMFY_MODELS_ROOT
            / "diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors": 15_000_000_000,
        },
    },
    "ltx2-fp4": {
        "weight_paths": [
            COMFY_MODELS_ROOT / "checkpoints/ltx-2-19b-dev-fp4.safetensors",
            COMFY_MODELS_ROOT / "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
            COMFY_MODELS_ROOT
            / "latent_upscale_models/ltx-2-spatial-upscaler-x2-1.0.safetensors",
            COMFY_MODELS_ROOT / "loras/ltx-2-19b-distilled-lora-384.safetensors",
        ],
        "min_bytes": {
            COMFY_MODELS_ROOT / "checkpoints/ltx-2-19b-dev-fp4.safetensors": 19_500_000_000,
            COMFY_MODELS_ROOT
            / "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors": 8_500_000_000,
        },
    },
    "ltx23-i2av": {
        "weight_paths": [
            COMFY_MODELS_ROOT
            / "diffusion_models/ltx-2.3-22b-dev_transformer_only_fp8_scaled.safetensors",
            COMFY_MODELS_ROOT / "text_encoders/ltx-2.3_text_projection_bf16.safetensors",
            COMFY_MODELS_ROOT / "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
            COMFY_MODELS_ROOT / "loras/ltx-2.3-22b-distilled-lora-384.safetensors",
            COMFY_MODELS_ROOT / "vae/LTX23_audio_vae_bf16.safetensors",
            COMFY_MODELS_ROOT / "vae/LTX23_video_vae_bf16.safetensors",
        ],
        "min_bytes": {
            COMFY_MODELS_ROOT
            / "diffusion_models/ltx-2.3-22b-dev_transformer_only_fp8_scaled.safetensors": 21_000_000_000,
            COMFY_MODELS_ROOT
            / "text_encoders/ltx-2.3_text_projection_bf16.safetensors": 2_000_000_000,
            COMFY_MODELS_ROOT
            / "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors": 8_500_000_000,
            COMFY_MODELS_ROOT
            / "loras/ltx-2.3-22b-distilled-lora-384.safetensors": 7_000_000_000,
            COMFY_MODELS_ROOT / "vae/LTX23_audio_vae_bf16.safetensors": 300_000_000,
            COMFY_MODELS_ROOT / "vae/LTX23_video_vae_bf16.safetensors": 1_200_000_000,
        },
    },
    VIDEO_ENHANCE_SEEDVR2_ID: {
        "seedvr_enhance": True,
    },
    "image-enhance-seedvr2": {
        "seedvr_enhance": True,
    },
}


def _weight_file_ready(path: Path, min_bytes: int = 1_000_000) -> bool:
    if not path.is_file():
        return False
    if path.with_suffix(path.suffix + ".aria2").is_file():
        return False
    if path.stat().st_size < min_bytes:
        return False
    ok, _ = _safetensors_readable(path)
    return ok


def seedvr_available_model_sizes() -> list[str]:
    """返回当前落盘的 SeedVR 规模：7b 顶配或 3b 轻量（5090）。"""
    if not _weight_file_ready(SEEDVR_VAE, 100_000_000):
        return []
    sizes: list[str] = []
    if _weight_file_ready(SEEDVR_7B, 15_000_000_000) and _weight_file_ready(
        SEEDVR_7B_SHARP, 15_000_000_000
    ):
        sizes.append("7b")
    if _weight_file_ready(SEEDVR_3B, 3_000_000_000):
        sizes.append("3b")
    return sizes


def default_seedvr_model_size() -> str:
    sizes = seedvr_available_model_sizes()
    if "7b" in sizes:
        return "7b"
    if "3b" in sizes:
        return "3b"
    return "7b"


def _seedvr_enhance_weights_ready() -> tuple[bool, str]:
    sizes = seedvr_available_model_sizes()
    if sizes:
        return True, f"ok ({','.join(sizes)})"
    if not _weight_file_ready(SEEDVR_VAE, 100_000_000):
        return False, f"missing {SEEDVR_VAE}"
    return False, f"missing {SEEDVR_7B} or {SEEDVR_3B}"


def _safetensors_readable(path: Path) -> tuple[bool, str]:
    if path.suffix != ".safetensors":
        return True, "ok"
    try:
        from safetensors import safe_open

        with safe_open(str(path), framework="pt") as handle:
            keys = list(handle.keys())
        if not keys:
            return False, f"empty safetensors {path}"
        return True, "ok"
    except Exception as exc:
        return False, f"corrupt safetensors {path}: {exc}"


def weights_ready(model_id: str) -> tuple[bool, str]:
    spec = MODEL_WEIGHT_REQUIREMENTS.get(model_id)
    if not spec:
        return False, f"no weight spec for {model_id}"
    if spec.get("seedvr_enhance"):
        return _seedvr_enhance_weights_ready()
    min_bytes: dict[Path, int] = spec.get("min_bytes") or {}
    missing_local: list[str] = []
    for path in spec.get("weight_paths") or []:
        p = Path(path)
        if not p.is_file():
            missing_local.append(str(p))
            continue
        if p.with_suffix(p.suffix + ".aria2").is_file():
            return False, f"incomplete download {p}.aria2"
        floor = min_bytes.get(p, 1_000_000)
        if p.stat().st_size < floor:
            return False, f"too small {p} ({p.stat().st_size} < {floor})"
        ok, reason = _safetensors_readable(p)
        if not ok:
            return False, reason
    if not missing_local:
        return True, "ok"
    # 本地缺权重时：任一 Comfy 节点（含远程 H800）能列出对应文件名则视为就绪
    if _remote_comfy_has_weight_files(missing_local):
        return True, "ok (remote comfy)"
    return False, f"missing {missing_local[0]}"


def _remote_comfy_has_weight_files(missing_paths: list[str]) -> bool:
    """同步探测各 Comfy 节点 /models/{folder} 是否含缺的权重文件名。"""
    try:
        import httpx
        from core.comfyui_settings import comfyui_nodes_list
    except Exception:
        return False

    names = {Path(p).name for p in missing_paths if p}
    if not names:
        return True
    folders = ("diffusion_models", "checkpoints", "unet", "vae", "text_encoders", "loras")
    try:
        with httpx.Client(timeout=5.0) as client:
            for base in comfyui_nodes_list():
                base = (base or "").rstrip("/")
                if not base:
                    continue
                found: set[str] = set()
                for folder in folders:
                    try:
                        res = client.get(f"{base}/models/{folder}")
                    except Exception:
                        continue
                    if res.status_code != 200:
                        continue
                    raw = res.json()
                    if isinstance(raw, list):
                        items = [str(x) for x in raw]
                    elif isinstance(raw, dict):
                        val = raw.get(folder, raw.get("checkpoints", raw))
                        if isinstance(val, dict):
                            items = [str(k) for k in val.keys()]
                        elif isinstance(val, list):
                            items = [str(x) for x in val]
                        else:
                            items = [str(k) for k in raw.keys()]
                    else:
                        items = []
                    for item in items:
                        for name in names:
                            if name in item:
                                found.add(name)
                if names <= found:
                    return True
    except Exception:
        return False
    return False


def _provider_payload(model_id: str) -> dict | None:
    provider = COMFYUI_PROVIDER_MAP.get(model_id)
    if not provider:
        return None
    comfyui_file = (provider.get("comfyui_file") or provider.get("comfyui_checkpoint") or "").strip()
    if not comfyui_file:
        return None
    return {
        "display_name": provider["display_name"],
        "category": provider["category"],
        "type": provider["type"],
        "provider": provider.get("provider"),
        "comfyui_file": comfyui_file,
    }


def sync_registered_models(*, only: set[str] | None = None, verbose: bool = False) -> int:
    """
    将 model_registry 元数据 + 权重落盘状态写入 registered_models。
    返回发生变更（插入或字段更新）的条数。
    """
    db = SessionLocal()
    changed = 0
    enable_ids: set[str] = set()
    try:
        model_ids = sorted(MODEL_WEIGHT_REQUIREMENTS.keys())
        if only is not None:
            model_ids = [mid for mid in model_ids if mid in only]

        for model_id in model_ids:
            payload = _provider_payload(model_id)
            if not payload:
                if verbose:
                    print(f"skip {model_id}: missing COMFYUI_LOCAL_PROVIDERS entry")
                continue

            if model_id in FORCE_DISABLE_IDS:
                enabled = False
            else:
                ok, reason = weights_ready(model_id)
                enabled = ok
                if ok:
                    enable_ids.add(model_id)
                elif verbose:
                    print(f"skip enable {model_id}: {reason}")

            row = db.get(RegisteredModel, model_id)
            if row:
                dirty = False
                for key, value in payload.items():
                    if getattr(row, key) != value:
                        setattr(row, key, value)
                        dirty = True
                if bool(row.enabled) != enabled:
                    row.enabled = enabled
                    dirty = True
                if dirty:
                    changed += 1
                    if verbose:
                        print(f"updated {model_id} enabled={enabled} file={payload['comfyui_file']}")
            else:
                db.add(RegisteredModel(id=model_id, enabled=enabled, **payload))
                changed += 1
                if verbose:
                    print(f"inserted {model_id} enabled={enabled}")

        for model_id in FORCE_DISABLE_IDS:
            row = db.get(RegisteredModel, model_id)
            if row and row.enabled:
                row.enabled = False
                changed += 1
                if verbose:
                    print(f"force disabled {model_id}")

        if changed:
            db.commit()
    finally:
        db.close()

    for entry in COMFYUI_LOCAL_PROVIDERS:
        pid = entry["id"]
        if pid in FORCE_DISABLE_IDS:
            entry["enabled"] = False
        elif pid in enable_ids:
            entry["enabled"] = True

    return changed


__all__ = [
    "sync_registered_models",
    "weights_ready",
    "MODEL_WEIGHT_REQUIREMENTS",
    "seedvr_available_model_sizes",
    "default_seedvr_model_size",
]
