#!/usr/bin/env bash
# G40: offline buffalo_l for ReActor (hf-mirror)
set -euo pipefail
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
DEST=/root/autodl-tmp/ComfyUI/models/insightface/models/buffalo_l
ZIP=/tmp/buffalo_l.zip
mkdir -p "$DEST"
if [ -f "$DEST/det_10g.onnx" ] && [ -f "$DEST/w600k_r50.onnx" ]; then
  echo "SKIP: buffalo_l already present"
  ls -lh "$DEST"
  exit 0
fi
curl -L --fail -o "$ZIP" \
  "${HF_ENDPOINT}/datasets/Gourieff/ReActor/resolve/main/models/buffalo_l.zip"
# zip is flat files
unzip -o "$ZIP" -d "$DEST"
rm -f "$ZIP"
ls -lh "$DEST"
