# 画风预设统一方案

> 修订日期：2026-07-02  
> 状态：已实施  
> 取代：原「任务一 · 写实电影内容风格预设」中新建 `contentStyle` 的设计

---

## 背景

面向 3 分钟量级真人写实 AI 短片，需要：

1. 在 prompt 层注入写实电影级正/负向关键词；
2. 在画质增强推荐中针对写实内容调参（如 `input_noise_scale=0.15`）；
3. 保持全片视觉风格一致。

**错误路径（已回滚）**：新建项目级「内容风格」(`contentStyle`)，并在分镜表工具栏 + 图像卡 PromptBar 双入口展示。

**正确路径（当前）**：扩展现有 **画风预设** (`SCRIPT_QUALITY_PRESETS` / `qualityPresetId`)，在一个入口完成导演参数 + prompt suffix + 增强策略映射。

---

## 产品原则

### 单一入口

| 能力 | 唯一 UI 位置 | 数据 |
|------|-------------|------|
| 画风 / 视觉风格 | 分镜表「默认画风」+ 镜头卡「画风」 | `defaultQualityPresetId` + 行级 `qualityPresetId` |
| 参考视频画风 | 视频卡「风格参考」弹窗 | `styleReference` on video-gen |
| LUT 色调 | 分镜表「色调风格」 | `lutPreset` 等 |

### 明确不做

- 不新建「内容风格」字段 (`contentStyle`)
- 图像卡 PromptBar **不加**画风下拉
- 不把「风格参考上传」与「画风预设」合并

---

## 画风预设

后端单一来源：[`backend/services/quality_presets.py`](../services/quality_presets.py)  
前端 UI 与导演参数：[`frontend/src/utils/canvas/scriptQualityPresets.js`](../../frontend/src/utils/canvas/scriptQualityPresets.js)

| preset id | 名称 | enhanceProfile |
|-----------|------|----------------|
| `auto` | 由模型自己选择 | generic |
| `cinematic` | 电影感 | cinematic |
| `documentary` | 纪录片 | cinematic |
| `commercial` | 商业广告 | generic |
| `anime` | 二次元 | generic |
| `retro_atomic` | 复古原子朋克 | generic |
| `dark_drama` | 暗调戏剧 | cinematic |
| `urban_noir` | 冷峻都市 | cinematic |
| `vintage_film` | 胶片年代 | cinematic |

### 有效 preset 解析

```
effectivePresetId = row.qualityPresetId || table.defaultQualityPresetId || "auto"
```

- **build-shot**：行级 effective preset 注入 suffix
- **画质增强 recommend-params**：表级 `defaultQualityPresetId`

### 数据迁移

旧画布 `contentStyle === "photorealistic_cinema"` 且 `defaultQualityPresetId === "auto"` → 迁移为 `cinematic`。  
分镜表 mount 时一次性清除 `contentStyle` 字段。

---

## 生成链路

- **画风预设**：模板，填导演参数 + 英文 tag
- **风格参考**：单镜头可选，从参考视频提取关键词追加到视频 prompt
- 两者可同时生效

---

## 相关文件

| 层 | 文件 |
|----|------|
| 后端 preset | `backend/services/quality_presets.py` |
| Prompt 注入 | `backend/services/prompt_builder.py` |
| 画质增强 | `backend/services/video_enhance_recommend.py` |
| 画布读取 | `backend/services/canvas_style_ref.py` → `get_script_table_default_quality_preset` |
| 前端 preset | `frontend/src/utils/canvas/scriptQualityPresets.js` |
| 节点工具 | `frontend/src/utils/canvas/scriptTableNode.js` |
| 分镜生成 | `frontend/src/hooks/canvas/useScriptTableGenerate.js` |
