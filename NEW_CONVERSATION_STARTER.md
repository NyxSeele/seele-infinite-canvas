# AI Studio · 新对话起手（NEW_CONVERSATION_STARTER）

用于开启新对话时快速恢复上下文。最后更新：**2026-07-10**

主交接仍以 [`HANDOFF.md`](HANDOFF.md) / [`HANDOFF_SERVER.md`](HANDOFF_SERVER.md) / [`GPU_DEBT.md`](GPU_DEBT.md) 为准。

---

## 当前状态

**pytest 114 passed；G31–G45 闭环；清理债项四件套（SD / media_access / api_key / Portal）✅；Hunyuan / AudioGen / ReActor / Phase4–7 仍有效**

### 本轮收口（清理债项）

| 项 | 状态 |
|----|------|
| **G42 SD1.5** | ✅ 产品入口与 registry 已移除；本机无权重 |
| **media_access** | ✅ 绝对 URL 归一化；enhance 用相对路径 |
| **API_KEY_ENCRYPT_SECRET** | ✅ 独立密钥 + 旧密文重加密 |
| **Portal / z-index** | ✅ overlay 迁 `getThemePortalRoot` + 常量收口 |

### G31–G45 交付摘要

| ID | 主题 | 要点 |
|----|------|------|
| **G31–G39** | 运镜 / token / fun_inpaint / Hunyuan / Seedance 框架 / AudioGen | 见 HANDOFF |
| **新 G40** | ReActor 出图换脸 | `use_reactor` + `buffalo_l` |
| **G45** | ReActor 视频逐帧 | 独立帧工作流；探针 PASS |
| **Phase4–7** | Prompt GPU 探针 | Phase4–6 全绿；Phase7 换脸复测通过 |

---

## 环境快照

| 项 | 值 |
|----|-----|
| **pytest 基线** | **114 passed** |
| **实例** | AutoDL 269 机 · RTX 4090 24GB |
| **磁盘** | `/root/autodl-tmp` **300G** · 已用 **~270G** · 剩余约 **31G** |
| **服务** | ComfyUI `:8000` · 后端 `:7788` · Nginx `:6006`（Supervisor） |

### 已启用模型

| 模型 ID | 说明 |
|---------|------|
| `flux-dev` | 文生图主力 |
| `flux-pulid` | 人物一致性（PuLID）+ 可选 ReActor 换脸 |
| `hidream` | 文生图备选 |
| `wan-2.6` | 文生视频 T2V |
| `wan-i2v` | 图生视频 / FLF2V |
| `wan-fun-inpaint` | 首尾帧 Fun Inpaint（G34） |
| `ltx2-fp4` | LTX-2 fp4（Phase5 GPU 探针已绿） |
| `video-enhance-seedvr2` | 画质增强 |
| `hunyuan-video` | **enabled=True**；重负载；建议高级选项，避免与 Wan/PuLID 同卡叠跑 |

---

## 待排期

- **Seedance Key（G46）**：**最后再说 / 不排期**（框架已就绪）
- **主观质量表（G47）**
- **百炼 qwen-max/turbo 免费额度**：仅 plus 可用

~~G42 SD1.5~~ · ~~media_access~~ · ~~api_key 加密~~ · ~~Portal/z-index~~ · ~~G44 assets~~ · ~~G45 视频换脸~~ · ~~G40 出图换脸~~ · ~~Phase4–7~~

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
