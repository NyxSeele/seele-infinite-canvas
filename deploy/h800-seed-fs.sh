#!/usr/bin/env bash
# H800：把 MagCache 等「种」进 autodl-fs（只需跑一次；同区域新实例可复用）
#
# 会写入：
#   /root/autodl-fs/models/...
#   /root/autodl-fs/comfy-plugins/ComfyUI-MagCache/
#
# 之后每次新 H800 只需：
#   bash deploy/h800-new-instance.sh
#   curl -fsSL …/h800-bootstrap/h800-new-instance.sh | bash -s --
#
# 用法：
#   bash deploy/h800-seed-fs.sh
#   curl -fsSL https://u1066791-81ad-fb224913.bjb2.seetacloud.com:8443/h800-bootstrap/h800-seed-fs.sh | bash

set -euo pipefail

FS="${AUTODL_FS:-/root/autodl-fs}"
MODELS="$FS/models"
PLUGINS="$FS/comfy-plugins"
HF="${HF_ENDPOINT:-https://hf-mirror.com}"
BOOTSTRAP_BASE="${BOOTSTRAP_BASE:-https://u1066791-81ad-fb224913.bjb2.seetacloud.com:8443/h800-bootstrap}"

if [[ ! -d "$FS" ]]; then
  echo "ERROR: $FS 不存在。请先在 AutoDL 控制台挂载「文件存储」到此实例。"
  exit 1
fi

mkdir -p \
  "$MODELS/diffusion_models" \
  "$MODELS/clip_vision" \
  "$MODELS/text_encoders" \
  "$MODELS/vae" \
  "$MODELS/loras" \
  "$PLUGINS"

aria_get() {
  local url="$1" out="$2" min_bytes="${3:-1000000}"
  if [[ -f "$out" ]]; then
    local sz
    sz=$(stat -Lc%s "$out" 2>/dev/null || echo 0)
    if [[ "$sz" -ge "$min_bytes" ]]; then
      echo "SKIP $(basename "$out") ($(du -h "$out" | cut -f1))"
      return 0
    fi
  fi
  echo "GET  $(basename "$out")"
  if command -v aria2c >/dev/null 2>&1; then
    aria2c -c -x8 -s8 -k 1M --file-allocation=none \
      -d "$(dirname "$out")" -o "$(basename "$out")" "$url"
    rm -f "${out}.aria2"
  else
    curl -L --retry 3 -o "$out" "$url"
  fi
}

echo "==> [1/2] MagCache → $PLUGINS/ComfyUI-MagCache"
MAG_DIR="$PLUGINS/ComfyUI-MagCache"
if [[ -f "$MAG_DIR/nodes.py" ]]; then
  echo "SKIP MagCache already on FS"
else
  TMP="$(mktemp -d)"
  if curl -fsSL "${BOOTSTRAP_BASE}/ComfyUI-MagCache.tgz" -o "${TMP}/MagCache.tgz"; then
    mkdir -p "$MAG_DIR"
    tar -xzf "${TMP}/MagCache.tgz" -C "$PLUGINS"
    # tarball 顶层目录名即 ComfyUI-MagCache
    echo "OK MagCache from 5090 bootstrap"
  else
    echo "bootstrap failed, git clone…"
    git clone --depth 1 https://github.com/Zehong-Ma/ComfyUI-MagCache.git "$MAG_DIR"
  fi
  rm -rf "$TMP"
fi

echo "==> [2/2] SigCLIP → $MODELS"
aria_get \
  "${HF}/Comfy-Org/sigclip_vision_384/resolve/main/sigclip_vision_patch14_384.safetensors" \
  "$MODELS/clip_vision/sigclip_vision_patch14_384.safetensors" \
  100000000

# 标记：restore 脚本可读
date -Is > "$FS/.h800_fs_seeded"
echo
echo "SEED DONE. FS usage:"
df -h "$FS" | tail -1
echo
echo "下次新 H800（挂同一块文件存储）只需："
echo "  bash /root/autodl-fs/bin/h800-restore-env.sh"
echo "  # 或从仓库："
echo "  bash deploy/h800-restore-env.sh"
echo
echo "现在可立即 restore："
echo "  bash \"$(cd "$(dirname "$0")" && pwd)/h800-restore-env.sh\""
