# Model Manifest

> 扫描时间：2026-07-13 · 实例数据盘 `/root/autodl-tmp`  
> 对照：`backend/model_registry.py` 中 `COMFYUI_LOCAL_PROVIDERS` 的 `enabled=True` 条目及伴随文件  
> 热模型合计：**约 182.1G**（按 10MB/s 估算下载约 **5.2 小时 / 311 分钟**）

## 热模型（常驻数据盘，每次必须有）

对应 registry `enabled=True`：`flux-dev` / `hidream` / `wan-2.6` / `wan-i2v` / `wan-fun-inpaint` / `hunyuan-video` / `video-enhance-seedvr2`。

| 模型名 | 文件路径 | 大小 | 来源/下载命令 |
|--------|---------|------|-------------|
| flux1-dev-fp8 | `/root/autodl-tmp/ComfyUI/models/diffusion_models/flux1-dev-fp8.safetensors` | 16.1G | `aria2c` hf-mirror `Comfy-Org/flux1-dev` → `flux1-dev-fp8.safetensors` |
| clip_l | `/root/autodl-tmp/ComfyUI/models/text_encoders/clip_l.safetensors` | 235M | hf-mirror `comfyanonymous/flux_text_encoders` |
| t5xxl_fp8_e4m3fn | `/root/autodl-tmp/ComfyUI/models/text_encoders/t5xxl_fp8_e4m3fn.safetensors` | 4.6G | hf-mirror `comfyanonymous/flux_text_encoders` |
| flux-vae-bf16 (+ ae 软链) | `/root/autodl-tmp/ComfyUI/models/vae/flux-vae-bf16.safetensors` → `ae.safetensors` | 320M | hf-mirror `Kijai/flux-fp8`；`ln -sf flux-vae-bf16.safetensors ae.safetensors` |
| hidream_i1_dev_fp8 | `/root/autodl-tmp/ComfyUI/models/diffusion_models/hidream_i1_dev_fp8.safetensors` | 15.9G | hf-mirror `Comfy-Org/HiDream-I1_ComfyUI` `split_files/diffusion_models/` |
| clip_l_hidream | `/root/autodl-tmp/ComfyUI/models/text_encoders/clip_l_hidream.safetensors` | 236M | 同上 `split_files/text_encoders/` |
| clip_g_hidream | `/root/autodl-tmp/ComfyUI/models/text_encoders/clip_g_hidream.safetensors` | 1.3G | 同上 |
| t5xxl_fp8_e4m3fn_scaled | `/root/autodl-tmp/ComfyUI/models/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors` | 4.8G | 同上（与 Flux T5 **独立文件**） |
| llama_3.1_8b_instruct_fp8_scaled | `/root/autodl-tmp/ComfyUI/models/text_encoders/llama_3.1_8b_instruct_fp8_scaled.safetensors` | 8.5G | 同上 |
| wan2.2_t2v_high_noise | `/root/autodl-tmp/ComfyUI/models/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors` | 13.3G | hf-mirror `Comfy-Org/Wan_2.2_ComfyUI_repackaged` |
| wan2.2_t2v_low_noise | `/root/autodl-tmp/ComfyUI/models/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors` | 13.3G | 同上 |
| wan2.2_i2v_high_noise | `/root/autodl-tmp/ComfyUI/models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` | 13.3G | 同上（不可用 fun_inpaint 替代） |
| wan2.2_i2v_low_noise | `/root/autodl-tmp/ComfyUI/models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | 13.3G | 同上 |
| wan2.2_fun_inpaint_high | `/root/autodl-tmp/ComfyUI/models/diffusion_models/wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors` | 13.3G | 同上 |
| wan2.2_fun_inpaint_low | `/root/autodl-tmp/ComfyUI/models/diffusion_models/wan2.2_fun_inpaint_low_noise_14B_fp8_scaled.safetensors` | 16.1G | 同上 |
| umt5_xxl_fp8 | `/root/autodl-tmp/ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors` | 6.3G | 同上（Wan 文本编码器） |
| wan_2.1_vae | `/root/autodl-tmp/ComfyUI/models/vae/wan_2.1_vae.safetensors` | 242M | 同上 |
| wan t2v lightx2v LoRA ×2 | `/root/autodl-tmp/ComfyUI/models/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_{high,low}_noise.safetensors` | 1.1G×2 | 同上 |
| wan i2v lightx2v LoRA ×2 | `/root/autodl-tmp/ComfyUI/models/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_{high,low}_noise.safetensors` | 1.1G×2 | 同上（fun_inpaint 亦用） |
| hunyuan_video_t2v_720p_bf16 | `/root/autodl-tmp/ComfyUI/models/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors` | 23.9G | hf-mirror `Comfy-Org/HunyuanVideo_repackaged` |
| hunyuan_video_vae_bf16 | `/root/autodl-tmp/ComfyUI/models/vae/hunyuan_video_vae_bf16.safetensors` | 470M | 同上 |
| llava_llama3_fp8_scaled | `/root/autodl-tmp/ComfyUI/models/text_encoders/llava_llama3_fp8_scaled.safetensors` | 8.5G | 同上（Hunyuan DualCLIP） |
| seedvr2_ema_3b_fp8 | `/root/autodl-tmp/ComfyUI/models/SEEDVR2/seedvr2_ema_3b_fp8_e4m3fn.safetensors` | 3.2G | hf-mirror `numz/SeedVR2_comfyUI` |
| ema_vae_fp16 | `/root/autodl-tmp/ComfyUI/models/SEEDVR2/ema_vae_fp16.safetensors` | 478M | 同上 |

**路径核对（enabled=True）**：上表文件均已在本机落盘；`ae.safetensors` 为指向 `flux-vae-bf16.safetensors` 的软链。

## 温模型（偶尔使用，换实例时按需下载）

| 模型名 | 文件路径 | 大小 | 来源/下载命令 |
|--------|---------|------|-------------|
| nunchaku flux int4 (flux-pulid) | `/root/autodl-tmp/ComfyUI/models/diffusion_models/svdq-int4_r32-flux.1-dev.safetensors` | 6.3G | `backend/scripts/_download_g30_ltx2_weights.sh` · `nunchaku-tech/nunchaku-flux.1-dev` |
| t5xxl_fp16 (PuLID) | `/root/autodl-tmp/ComfyUI/models/text_encoders/t5xxl_fp16.safetensors` | 9.1G | `comfyanonymous/flux_text_encoders` |
| ltx-2-19b-dev-fp4 | `/root/autodl-tmp/ComfyUI/models/checkpoints/ltx-2-19b-dev-fp4.safetensors` | 18.6G | `Lightricks/LTX-2` |
| gemma_3_12B_it_fp4_mixed | `/root/autodl-tmp/ComfyUI/models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors` | 8.8G | `Comfy-Org/ltx-2` |
| ltx-2-spatial-upscaler-x2 | `/root/autodl-tmp/ComfyUI/models/latent_upscale_models/ltx-2-spatial-upscaler-x2-1.0.safetensors` | 950M | `Lightricks/LTX-2` |
| ltx-2-19b-distilled-lora | `/root/autodl-tmp/ComfyUI/models/loras/ltx-2-19b-distilled-lora-384.safetensors` | 7.1G | 同上 |
| ltx camera dolly-left LoRA | `/root/autodl-tmp/ComfyUI/models/loras/ltx-2-19b-lora-camera-control-dolly-left.safetensors` | 312M | `Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Left` |
| RealESRGAN_x4plus | `/root/autodl-tmp/ComfyUI/models/upscale_models/RealESRGAN_x4plus.pth` | 64M | 官方 Real-ESRGAN（`video-enhance-realesrgan` fallback） |
| audiogen-medium | `/root/autodl-tmp/models/audiogen-medium/`（`state_dict.bin` 等） | ~3.6G | `backend/scripts/_download_g39_audiogen.sh` · `facebook/audiogen-medium` |

## 权重依赖（ReActor/PuLID 等附属权重）

| 模型名 | 文件路径 | 大小 | 来源/下载命令 |
|--------|---------|------|-------------|
| pulid_flux_v0.9.1 | `/root/autodl-tmp/ComfyUI/models/pulid/pulid_flux_v0.9.1.safetensors` | 1.1G | `guozinan/PuLID` |
| EVA02_CLIP_L_336 | `/root/autodl-tmp/ComfyUI/models/clip/EVA02_CLIP_L_336_psz14_s6B.pt` | 817M | `QuanSun/EVA-CLIP` |
| antelopev2 | `/root/autodl-tmp/ComfyUI/models/insightface/models/antelopev2/*.onnx` | ~400M | hf-mirror `MonsterMMORPG/tools` `antelopev2.zip` |
| buffalo_l (ReActor) | `/root/autodl-tmp/ComfyUI/models/insightface/models/buffalo_l/*.onnx` | ~325M | `backend/scripts/_download_g40_buffalo_l.sh` · `Gourieff/ReActor` |
| inswapper_128 | `/root/autodl-tmp/ComfyUI/models/insightface/inswapper_128.onnx` | 529M | ReActor 依赖 |
| GFPGAN / CodeFormer | `/root/autodl-tmp/ComfyUI/models/facerestore_models/*.pth` | ~1.0G | 人脸修复 |
| facexlib detection/parsing | `/root/autodl-tmp/ComfyUI/models/facexlib/` | ~230M | xinntao/facexlib releases |

## 恢复步骤（新实例）

1. 克隆代码：`git clone https://github.com/NyxSeele/seele-infinite-canvas.git AIStudio`
2. 安装 `aria2c` + `huggingface-cli`/`hf`，设置 `export HF_ENDPOINT=https://hf-mirror.com`
3. 跑热模型脚本：`bash model_pull.sh`（约 182G）
4. 按需跑温模型：`backend/scripts/_download_g30_ltx2_weights.sh` / `_download_g35_hunyuan_weights.sh`（若热模型未含 Hunyuan 则已包含）/ `_download_g39_audiogen.sh` / `_download_g40_buffalo_l.sh`
5. 重启 ComfyUI 与后端

一键热模型脚本见同目录 [`model_pull.sh`](model_pull.sh)。
