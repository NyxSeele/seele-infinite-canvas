#!/bin/bash
# 新实例模型拉取脚本（热模型 / enabled=True 全套）
# 用法：bash model_pull.sh
# 依赖：aria2c；可选 huggingface-cli（部分温模型脚本用）
# 预计：约 182G；按 10MB/s ≈ 5.2 小时
set -euo pipefail

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
HF="${HF_ENDPOINT}"
COMFY="${COMFYUI_MODELS:-/root/autodl-tmp/ComfyUI/models}"
WAN="${HF}/Comfy-Org/Wan_2.2_ComfyUI_repackaged/resolve/main/split_files"
HIDREAM="${HF}/Comfy-Org/HiDream-I1_ComfyUI/resolve/main/split_files"
HUNYUAN="${HF}/Comfy-Org/HunyuanVideo_repackaged/resolve/main/split_files"
FLUX_TE="${HF}/comfyanonymous/flux_text_encoders/resolve/main"
FLUX_DEV="${HF}/Comfy-Org/flux1-dev/resolve/main"
KIJAI="${HF}/Kijai/flux-fp8/resolve/main"
SEEDVR="${HF}/numz/SeedVR2_comfyUI/resolve/main"

mkdir -p \
  "$COMFY/diffusion_models" "$COMFY/text_encoders" "$COMFY/vae" \
  "$COMFY/loras" "$COMFY/SEEDVR2" "$COMFY/checkpoints"

echo "开始下载热模型... (COMFY=$COMFY HF_ENDPOINT=$HF_ENDPOINT)"

aria_get() {
  local url="$1" dest="$2" min_bytes="${3:-1000000}"
  if [[ -e "$dest" ]]; then
    local sz
    sz=$(stat -Lc%s "$dest" 2>/dev/null || echo 0)
    if [[ "$sz" -ge "$min_bytes" ]]; then
      echo "SKIP $(basename "$dest") ($(du -h "$dest" | cut -f1))"
      return 0
    fi
  fi
  mkdir -p "$(dirname "$dest")"
  echo "GET $(basename "$dest")"
  aria2c -x 16 -s 16 -k 1M -c --file-allocation=none \
    -o "$(basename "$dest")" -d "$(dirname "$dest")" "$url"
  rm -f "${dest}.aria2"
}

# ── Flux Dev fp8 + companions ─────────────────────────────────────
aria_get "${FLUX_DEV}/flux1-dev-fp8.safetensors" \
  "$COMFY/diffusion_models/flux1-dev-fp8.safetensors" 10000000000
aria_get "${FLUX_TE}/clip_l.safetensors" \
  "$COMFY/text_encoders/clip_l.safetensors" 100000000
aria_get "${FLUX_TE}/t5xxl_fp8_e4m3fn.safetensors" \
  "$COMFY/text_encoders/t5xxl_fp8_e4m3fn.safetensors" 4000000000
aria_get "${KIJAI}/flux-vae-bf16.safetensors" \
  "$COMFY/vae/flux-vae-bf16.safetensors" 100000000
ln -sfn flux-vae-bf16.safetensors "$COMFY/vae/ae.safetensors"
# 兼容旧探针文件名
ln -sfn flux1-dev-fp8.safetensors "$COMFY/diffusion_models/flux1-dev.safetensors"

# ── HiDream i1 fp8 ────────────────────────────────────────────────
aria_get "${HIDREAM}/diffusion_models/hidream_i1_dev_fp8.safetensors" \
  "$COMFY/diffusion_models/hidream_i1_dev_fp8.safetensors" 10000000000
aria_get "${HIDREAM}/text_encoders/clip_l_hidream.safetensors" \
  "$COMFY/text_encoders/clip_l_hidream.safetensors" 100000000
aria_get "${HIDREAM}/text_encoders/clip_g_hidream.safetensors" \
  "$COMFY/text_encoders/clip_g_hidream.safetensors" 1000000000
aria_get "${HIDREAM}/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors" \
  "$COMFY/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors" 4000000000
aria_get "${HIDREAM}/text_encoders/llama_3.1_8b_instruct_fp8_scaled.safetensors" \
  "$COMFY/text_encoders/llama_3.1_8b_instruct_fp8_scaled.safetensors" 4000000000

# ── Wan 2.2 T2V / I2V / Fun Inpaint ───────────────────────────────
aria_get "${WAN}/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" \
  "$COMFY/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors" \
  "$COMFY/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" \
  "$COMFY/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" \
  "$COMFY/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors" \
  "$COMFY/diffusion_models/wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_fun_inpaint_low_noise_14B_fp8_scaled.safetensors" \
  "$COMFY/diffusion_models/wan2.2_fun_inpaint_low_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
  "$COMFY/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" 5000000000
aria_get "${WAN}/vae/wan_2.1_vae.safetensors" \
  "$COMFY/vae/wan_2.1_vae.safetensors" 100000000
aria_get "${WAN}/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors" \
  "$COMFY/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors" 500000000
aria_get "${WAN}/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors" \
  "$COMFY/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors" 500000000
aria_get "${WAN}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" \
  "$COMFY/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" 500000000
aria_get "${WAN}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" \
  "$COMFY/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" 500000000

# ── HunyuanVideo ──────────────────────────────────────────────────
aria_get "${HUNYUAN}/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors" \
  "$COMFY/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors" 20000000000
aria_get "${HUNYUAN}/vae/hunyuan_video_vae_bf16.safetensors" \
  "$COMFY/vae/hunyuan_video_vae_bf16.safetensors" 100000000
aria_get "${HUNYUAN}/text_encoders/llava_llama3_fp8_scaled.safetensors" \
  "$COMFY/text_encoders/llava_llama3_fp8_scaled.safetensors" 1000000000

# ── SeedVR2 ───────────────────────────────────────────────────────
aria_get "${SEEDVR}/seedvr2_ema_3b_fp8_e4m3fn.safetensors" \
  "$COMFY/SEEDVR2/seedvr2_ema_3b_fp8_e4m3fn.safetensors" 3000000000
aria_get "${SEEDVR}/ema_vae_fp16.safetensors" \
  "$COMFY/SEEDVR2/ema_vae_fp16.safetensors" 100000000

echo "完成，请重启 ComfyUI"
echo "温模型/附属权重可按需执行："
echo "  bash backend/scripts/_download_g30_ltx2_weights.sh   # PuLID + LTX2"
echo "  bash backend/scripts/_download_g40_buffalo_l.sh      # ReActor buffalo_l"
echo "  bash backend/scripts/_download_g39_audiogen.sh       # AudioGen"
df -h "$(dirname "$COMFY")" | tail -1
