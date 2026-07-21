#!/usr/bin/env bash
# H800：一键恢复刚删的 Wan 2.2 权重（6 UNET + 4 Lightx2v LoRA）到 autodl-fs。
# 用法：bash deploy/h800-restore-wan22.sh
# 可选：恢复后提升到本地热盘 → bash deploy/h800-promote-video-models-to-local.sh
set -euo pipefail

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
HF="${HF_ENDPOINT}"
WAN="${HF}/Comfy-Org/Wan_2.2_ComfyUI_repackaged/resolve/main/split_files"
DEST="${WAN22_DIR:-/root/autodl-fs/models}"

mkdir -p "$DEST"/{diffusion_models,loras}

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
  echo "GET $(basename "$dest")"
  aria2c -x 16 -s 16 -k 1M -c --file-allocation=none \
    -o "$(basename "$dest")" -d "$(dirname "$dest")" "$url"
  rm -f "${dest}.aria2"
}

echo "Wan 2.2 restore → $DEST (HF=$HF_ENDPOINT)"
df -h "$(dirname "$DEST")" | tail -1

# 6× UNET (~84G)
aria_get "${WAN}/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" \
  "$DEST/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors" \
  "$DEST/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" \
  "$DEST/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" \
  "$DEST/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors" \
  "$DEST/diffusion_models/wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors" 10000000000
aria_get "${WAN}/diffusion_models/wan2.2_fun_inpaint_low_noise_14B_fp8_scaled.safetensors" \
  "$DEST/diffusion_models/wan2.2_fun_inpaint_low_noise_14B_fp8_scaled.safetensors" 10000000000

# 4× Lightx2v LoRA (~4.8G)
aria_get "${WAN}/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors" \
  "$DEST/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors" 500000000
aria_get "${WAN}/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors" \
  "$DEST/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors" 500000000
aria_get "${WAN}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" \
  "$DEST/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" 500000000
aria_get "${WAN}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" \
  "$DEST/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" 500000000

echo "完成。清单："
ls -lh "$DEST"/diffusion_models/wan2.2_* "$DEST"/loras/wan2.2_* 2>/dev/null
df -h "$(dirname "$DEST")" | tail -1
echo ""
echo "若需同步到本地热盘：bash deploy/h800-promote-video-models-to-local.sh"
