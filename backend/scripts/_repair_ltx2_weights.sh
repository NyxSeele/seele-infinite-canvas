#!/usr/bin/env bash
# 修复损坏的 LTX2 fp4 权重（checkpoint + gemma），下载后做 safetensors 头校验。
set -euo pipefail
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
COMFY=/root/autodl-tmp/ComfyUI/models
CLI=/root/miniconda3/bin/huggingface-cli
PY=/root/autodl-tmp/AIStudio/backend/.venv/bin/python

validate() {
  local f="$1"
  "$PY" - <<PY
from safetensors import safe_open
p = "$f"
with safe_open(p, framework="pt") as h:
    n = len(list(h.keys()))
print(f"OK {p} tensors={n}")
PY
}

echo "=== remove corrupt LTX2 weights ==="
rm -f "$COMFY/checkpoints/ltx-2-19b-dev-fp4.safetensors" \
      "$COMFY/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
rm -rf "$COMFY/text_encoders/split_files" "$COMFY/text_encoders/.cache"

echo "=== download gemma fp4 ==="
$CLI download Comfy-Org/ltx-2 split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors \
  --local-dir "$COMFY/text_encoders"
GEMMA_SRC="$COMFY/text_encoders/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
GEMMA_DST="$COMFY/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
if [ -f "$GEMMA_SRC" ]; then
  mv -f "$GEMMA_SRC" "$GEMMA_DST"
  rm -rf "$COMFY/text_encoders/split_files"
fi
validate "$GEMMA_DST"

echo "=== download ltx-2-19b-dev-fp4 ==="
$CLI download Lightricks/LTX-2 ltx-2-19b-dev-fp4.safetensors \
  --local-dir "$COMFY/checkpoints"
validate "$COMFY/checkpoints/ltx-2-19b-dev-fp4.safetensors"

echo "=== re-enable models ==="
cd /root/autodl-tmp/AIStudio/backend
"$PY" scripts/_enable_gpu_models.py --only ltx2-fp4

echo "DONE"
