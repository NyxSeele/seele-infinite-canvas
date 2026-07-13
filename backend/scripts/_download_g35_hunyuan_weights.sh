#!/usr/bin/env bash
# G35: Download HunyuanVideo T2V weights via hf-mirror (~30G+)
set -euo pipefail

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
COMFY=/root/autodl-tmp/ComfyUI/models
CLI=/root/autodl-tmp/miniconda3/bin/huggingface-cli
REPO=Comfy-Org/HunyuanVideo_repackaged

avail_kb=$(df -Pk /root/autodl-tmp | awk 'NR==2 {print $4}')
avail_g=$((avail_kb / 1024 / 1024))
echo "Available on /root/autodl-tmp: ${avail_g}G"
if [ "$avail_g" -lt 35 ]; then
  echo "ERROR: need >=35G free for Hunyuan weights (have ${avail_g}G)" >&2
  exit 1
fi

mkdir -p "$COMFY/diffusion_models" "$COMFY/vae" "$COMFY/text_encoders"

need_download() {
  local path="$1"
  local min_bytes="${2:-1000000}"
  if [ -f "$path" ] && [ "$(stat -c%s "$path")" -ge "$min_bytes" ]; then
    echo "SKIP exists: $path ($(stat -c%s "$path") bytes)"
    return 1
  fi
  return 0
}

echo "=== Hunyuan UNET t2v 720p bf16 ==="
UNET="$COMFY/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors"
if need_download "$UNET" 10000000000; then
  $CLI download "$REPO" \
    split_files/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors \
    --local-dir /tmp/g35_hunyuan_unet --local-dir-use-symlinks False
  mv -f /tmp/g35_hunyuan_unet/split_files/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors "$UNET"
  rm -rf /tmp/g35_hunyuan_unet
fi

echo "=== Hunyuan VAE bf16 ==="
VAE="$COMFY/vae/hunyuan_video_vae_bf16.safetensors"
if need_download "$VAE" 100000000; then
  $CLI download "$REPO" \
    split_files/vae/hunyuan_video_vae_bf16.safetensors \
    --local-dir /tmp/g35_hunyuan_vae --local-dir-use-symlinks False
  mv -f /tmp/g35_hunyuan_vae/split_files/vae/hunyuan_video_vae_bf16.safetensors "$VAE"
  rm -rf /tmp/g35_hunyuan_vae
fi

echo "=== clip_l ==="
CLIP_L="$COMFY/text_encoders/clip_l.safetensors"
if need_download "$CLIP_L" 100000000; then
  $CLI download comfyanonymous/flux_text_encoders clip_l.safetensors \
    --local-dir "$COMFY/text_encoders" --local-dir-use-symlinks False
fi

echo "=== llava_llama3_fp8_scaled ==="
LLAVA="$COMFY/text_encoders/llava_llama3_fp8_scaled.safetensors"
if need_download "$LLAVA" 1000000000; then
  $CLI download "$REPO" \
    split_files/text_encoders/llava_llama3_fp8_scaled.safetensors \
    --local-dir /tmp/g35_hunyuan_llava --local-dir-use-symlinks False
  mv -f /tmp/g35_hunyuan_llava/split_files/text_encoders/llava_llama3_fp8_scaled.safetensors "$LLAVA"
  rm -rf /tmp/g35_hunyuan_llava
fi

echo "DONE"
ls -lh "$UNET" "$VAE" "$CLIP_L" "$LLAVA"
df -h /root/autodl-tmp | tail -1
