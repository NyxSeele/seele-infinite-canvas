#!/usr/bin/env bash
# G39: Download facebook/audiogen-medium via hf-mirror (~2G)
set -euo pipefail
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
DEST=/root/autodl-tmp/models/audiogen-medium
CLI=/root/autodl-tmp/miniconda3/bin/huggingface-cli

avail_kb=$(df -Pk /root/autodl-tmp | awk 'NR==2 {print $4}')
avail_g=$((avail_kb / 1024 / 1024))
echo "Available: ${avail_g}G"
if [ "$avail_g" -lt 5 ]; then
  echo "ERROR: need >=5G free" >&2
  exit 1
fi

mkdir -p "$DEST"
if [ -f "$DEST/state_dict.bin" ] || [ -f "$DEST/compression_state_dict.bin" ] || ls "$DEST"/*.bin >/dev/null 2>&1; then
  echo "SKIP: weights appear present in $DEST"
  ls -lh "$DEST" | head -20
  exit 0
fi

echo "=== facebook/audiogen-medium ==="
$CLI download facebook/audiogen-medium \
  --local-dir "$DEST" --local-dir-use-symlinks False

echo "DONE"
ls -lh "$DEST" | head -30
df -h /root/autodl-tmp | tail -1
