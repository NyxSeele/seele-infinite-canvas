#!/usr/bin/env bash
# Download PuLID + Nunchaku FLUX + LTX2-fp4 weights (hf-mirror)
set -euo pipefail
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
COMFY=/root/autodl-tmp/ComfyUI/models
CLI=/root/autodl-tmp/miniconda3/bin/huggingface-cli
mkdir -p "$COMFY/diffusion_models" "$COMFY/pulid" "$COMFY/clip" \
  "$COMFY/insightface/models/antelopev2" "$COMFY/text_encoders" \
  "$COMFY/checkpoints" "$COMFY/latent_upscale_models" "$COMFY/loras"

echo "=== nunchaku flux int4 ==="
$CLI download nunchaku-tech/nunchaku-flux.1-dev \
  svdq-int4_r32-flux.1-dev.safetensors \
  --local-dir "$COMFY/diffusion_models" --local-dir-use-symlinks False

echo "=== PuLID ==="
$CLI download guozinan/PuLID pulid_flux_v0.9.1.safetensors \
  --local-dir "$COMFY/pulid" --local-dir-use-symlinks False

echo "=== EVA-CLIP ==="
$CLI download QuanSun/EVA-CLIP EVA02_CLIP_L_336_psz14_s6B.pt \
  --local-dir "$COMFY/clip" --local-dir-use-symlinks False

echo "=== antelopev2 ==="
curl -L -o /tmp/antelopev2.zip "https://hf-mirror.com/MonsterMMORPG/tools/resolve/main/antelopev2.zip"
unzip -o /tmp/antelopev2.zip -d "$COMFY/insightface/models/"
# ensure onnx files sit directly under antelopev2/
if [ -d "$COMFY/insightface/models/antelopev2/antelopev2" ]; then
  mv "$COMFY/insightface/models/antelopev2/antelopev2/"*.onnx "$COMFY/insightface/models/antelopev2/" 2>/dev/null || true
  rmdir "$COMFY/insightface/models/antelopev2/antelopev2" 2>/dev/null || true
fi

echo "=== facexlib ==="
mkdir -p "$COMFY/facexlib/detection" "$COMFY/facexlib/parsing"
curl -L -o "$COMFY/facexlib/detection/detection_Resnet50_Final.pth" \
  "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth"
curl -L -o "$COMFY/facexlib/parsing/parsing_bisenet.pth" \
  "https://github.com/xinntao/facexlib/releases/download/v0.2.0/parsing_bisenet.pth"
curl -L -o "$COMFY/facexlib/parsing/parsing_parsenet.pth" \
  "https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth"

echo "=== t5 fp16 (PuLID text encoder) ==="
$CLI download comfyanonymous/flux_text_encoders t5xxl_fp16.safetensors \
  --local-dir "$COMFY/text_encoders" --local-dir-use-symlinks False || \
$CLI download black-forest-labs/FLUX.1-dev \
  --include "text_encoder_2/*" \
  --local-dir /tmp/flux-te --local-dir-use-symlinks False

echo "=== LTX2 fp4 bundle (Lightricks + Comfy-Org) ==="
$CLI download Lightricks/LTX-2 ltx-2-19b-dev-fp4.safetensors \
  --local-dir "$COMFY/checkpoints" --local-dir-use-symlinks False
$CLI download Comfy-Org/ltx-2 split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors \
  --local-dir "$COMFY/text_encoders" --local-dir-use-symlinks False
$CLI download Lightricks/LTX-2 ltx-2-spatial-upscaler-x2-1.0.safetensors \
  --local-dir "$COMFY/latent_upscale_models" --local-dir-use-symlinks False
$CLI download Lightricks/LTX-2 ltx-2-19b-distilled-lora-384.safetensors \
  --local-dir "$COMFY/loras" --local-dir-use-symlinks False
$CLI download Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Left \
  ltx-2-19b-lora-camera-control-dolly-left.safetensors \
  --local-dir "$COMFY/loras" --local-dir-use-symlinks False

echo "DONE"
