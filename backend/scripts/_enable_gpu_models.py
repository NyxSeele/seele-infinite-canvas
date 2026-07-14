#!/usr/bin/env python3
"""启用 GPU 验收所需 registered_models 与 COMFYUI provider（一次性运维脚本）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.session import SessionLocal
from model_registry import (
    COMFYUI_LOCAL_PROVIDERS,
    VIDEO_ENHANCE_SEEDVR2_ID,
)
from models import RegisteredModel

ENABLE_MODELS = {
    "flux-dev": {
        "display_name": "Flux Dev",
        "category": "image",
        "type": "local",
        "provider": "comfyui",
        "comfyui_file": "flux1-dev-fp8.safetensors",
    },
    "wan-2.6": {
        "display_name": "Wan 2.6",
        "category": "video",
        "type": "local",
        "provider": "comfyui",
        "comfyui_file": "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
    },
    "wan-i2v": {
        "display_name": "Wan 2.6 I2V",
        "category": "video",
        "type": "local",
        "provider": "comfyui",
        "comfyui_file": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
    },
    "wan-fun-inpaint": {
        "display_name": "Wan Fun Inpaint",
        "category": "video",
        "type": "local",
        "provider": "comfyui",
        "comfyui_file": "wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors",
    },
    "hidream": {
        "display_name": "HiDream",
        "category": "image",
        "type": "local",
        "provider": "comfyui",
        "comfyui_file": "hidream_i1_dev_fp8.safetensors",
    },
    "flux-pulid": {
        "display_name": "Flux + PuLID",
        "category": "image",
        "type": "local",
        "provider": "comfyui",
        "comfyui_file": "svdq-int4_r32-flux.1-dev.safetensors",
    },
    "ltx2-fp4": {
        "display_name": "LTX-2 fp4",
        "category": "video",
        "type": "local",
        "provider": "comfyui",
        "comfyui_file": "ltx-2-19b-dev-fp4.safetensors",
    },
    "hunyuan-video-1.5": {
        "display_name": "HunyuanVideo 1.5",
        "category": "video",
        "type": "local",
        "provider": "comfyui",
        "comfyui_file": "hunyuanvideo1.5_720p_t2v_fp16.safetensors",
    },
}

PROVIDER_ENABLE_IDS = (
    "flux-dev",
    "flux-pulid",
    "wan-2.6",
    "wan-i2v",
    "wan-fun-inpaint",
    "hidream",
    "ltx2-fp4",
    "hunyuan-video-1.5",
    VIDEO_ENHANCE_SEEDVR2_ID,
)


def main() -> int:
  db = SessionLocal()
  try:
    for mid, meta in ENABLE_MODELS.items():
      row = db.get(RegisteredModel, mid)
      if row:
        row.enabled = True
        row.comfyui_file = meta["comfyui_file"]
        print(f"updated {mid}")
      else:
        db.add(RegisteredModel(id=mid, enabled=True, **meta))
        print(f"inserted {mid}")
    db.commit()
  finally:
    db.close()

  for entry in COMFYUI_LOCAL_PROVIDERS:
    if entry["id"] in PROVIDER_ENABLE_IDS:
      entry["enabled"] = True
      print(f"provider enabled {entry['id']}")

  print("OK")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
