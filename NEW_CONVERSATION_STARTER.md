# AI Studio · 新对话起手（NEW_CONVERSATION_STARTER）

用于开启新对话时快速恢复上下文。最后更新：**2026-07-15**

主交接仍以 [`HANDOFF.md`](HANDOFF.md) / [`HANDOFF_SERVER.md`](HANDOFF_SERVER.md) / [`GPU_DEBT.md`](GPU_DEBT.md) 为准。

**硬约束（Cursor）**：勿整文件覆盖 `deploy/supervisor-autodl.conf`；必须保留 comfyui0/comfyui1/backend/**nginx**/**cloudflared** 五段（缺 cloudflared → 公网 1033）。见 HANDOFF 文首。

**硬约束 · 系统盘**：`/` 仅 **30GB**，**严禁**模型/缓存/临时测试/大日志等无关文件写入系统盘 → 一律 `/root/autodl-tmp`；`TMPDIR=/root/autodl-tmp/tmp`。操作前 `df -h /`。

---

## 当前状态

**pytest 154 passed（1 failed 与本次无关）；G31–G50 全部闭合**

### 环境快照

| 项 | 值 |
|----|-----|
| **实例** | AutoDL 北京 B 区 · 双 RTX 5090 32GB |
| **GPU 并行** | GPU0 ComfyUI `:8000` · GPU1 ComfyUI `:8001` |
| **磁盘** | `/root/autodl-tmp` **350G** · 热模型约 **182G** |
| **服务** | 双 ComfyUI · 后端 `:7788` · Nginx `:6006`（Supervisor） |
| **pytest 基线** | **154 passed**（`test_upload_canvas_r2` 1 failed，与 PuLID/Qwen 无关） |

### 已启用模型

| 模型 ID | 说明 |
|---------|------|
| `ltx2-fp4` | LTX-2 fp4 · **76 秒/条** · 验收通过 |
| `hunyuan-video-1.5` | HunyuanVideo 1.5 T2V |
| `wan-2.6` / `wan-i2v` / `wan-fun-inpaint` | Wan 2.2 全系 |
| `flux-dev` | Flux Dev fp8 文生图 |
| `qwen-image` | Qwen-Image · **15.5 秒/条** · Nunchaku fp4 · 4 步 |
| `flux-pulid` | Flux + PuLID · **15.1 秒/条** · fp4 · 角色一致性 · 需正脸参考图 |
| `hidream` | HiDream i1 文生图 |
| `video-enhance-seedvr2` / `image-enhance-seedvr2` | SeedVR2 画质增强 |
| `video-enhance-realesrgan` | RealESRGAN 视频增强 |

Hunyuan 仅保留 `hunyuan-video-1.5`（旧 13B `hunyuan-video` 已下线）。

---

## 待做项

| 项 | 状态 |
|----|------|
| **Seedance Key（G46）** | 搁置 |
| **Qwen-Image** | 已接入，待画布端到端验收 |

---

## 推荐阅读顺序

1. 本文件（一句话状态）
2. [`HANDOFF.md`](HANDOFF.md) 文首「当前总览」
3. [`GPU_DEBT.md`](GPU_DEBT.md)
4. [`HANDOFF_SERVER.md`](HANDOFF_SERVER.md)（AutoDL 运维）

```bash
# 关机后 Supervisor
/usr/bin/supervisord -c /etc/supervisor/supervisord.conf

# 回归
cd /root/autodl-tmp/AIStudio/backend && PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
```
