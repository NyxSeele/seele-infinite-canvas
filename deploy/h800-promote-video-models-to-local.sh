#!/usr/bin/env bash
# H800 视频 Worker：将 Wan 热路径从 autodl-fs 提升到本地数据盘，缩短冷启动。
# 在 H800 SSH 中执行（约 118G，需确认 df -h /root/autodl-tmp 空间足够）。
set -euo pipefail

FS=/root/autodl-fs/models
LOCAL=/root/autodl-tmp/ComfyUI/models

mkdir -p "$LOCAL"/{diffusion_models,vae,text_encoders,loras}

copy_if_missing() {
  local rel="$1"
  local src="$FS/$rel"
  local dst="$LOCAL/$rel"
  if [[ -f "$dst" ]]; then
    echo "skip (exists) $rel"
    return 0
  fi
  if [[ ! -f "$src" ]]; then
    echo "missing on fs: $src" >&2
    return 1
  fi
  echo "copy $rel"
  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
}

# Wan 6 主干
for f in \
  diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors \
  diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors \
  diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors \
  diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors \
  diffusion_models/wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors \
  diffusion_models/wan2.2_fun_inpaint_low_noise_14B_fp8_scaled.safetensors
do
  copy_if_missing "$f"
done

# VAE + TE + LoRA
for f in \
  vae/wan_2.1_vae.safetensors \
  text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors \
  loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors \
  loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors \
  loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors \
  loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors
do
  copy_if_missing "$f"
done

echo "done. local size:" 
du -sh "$LOCAL"

echo "Next:"
echo "  cp deploy/extra_model_paths.h800-local.yaml /root/ComfyUI/extra_model_paths.yaml"
echo "  # restart ComfyUI on :6006"
