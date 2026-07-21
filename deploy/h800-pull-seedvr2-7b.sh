#!/usr/bin/env bash
# H800：拉取 SeedVR2 7B FP16 顶配到 autodl-fs（约 33.5G：7B + sharp + VAE）
# 在 H800 SSH 中执行：bash deploy/h800-pull-seedvr2-7b.sh
set -euo pipefail

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
HF="${HF_ENDPOINT}"
SEEDVR="${HF}/numz/SeedVR2_comfyUI/resolve/main"
DEST="${SEEDVR2_DIR:-/root/autodl-fs/models/SEEDVR2}"

mkdir -p "$DEST"

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

echo "SeedVR2 7B FP16 → $DEST (HF=$HF_ENDPOINT)"
df -h "$(dirname "$DEST")" | tail -1

aria_get "${SEEDVR}/seedvr2_ema_7b_fp16.safetensors" \
  "$DEST/seedvr2_ema_7b_fp16.safetensors" 15000000000
aria_get "${SEEDVR}/seedvr2_ema_7b_sharp_fp16.safetensors" \
  "$DEST/seedvr2_ema_7b_sharp_fp16.safetensors" 15000000000
aria_get "${SEEDVR}/ema_vae_fp16.safetensors" \
  "$DEST/ema_vae_fp16.safetensors" 100000000

# 可选：5090 轻量降级（非顶配）
# aria_get "${SEEDVR}/seedvr2_ema_3b_fp8_e4m3fn.safetensors" \
#   "$DEST/seedvr2_ema_3b_fp8_e4m3fn.safetensors" 3000000000

echo "完成。确认 ComfyUI extra_model_paths 指向 $DEST 父目录 models/"
ls -lh "$DEST"/seedvr2_ema_7b*.safetensors "$DEST"/ema_vae_fp16.safetensors
df -h "$(dirname "$DEST")" | tail -1
