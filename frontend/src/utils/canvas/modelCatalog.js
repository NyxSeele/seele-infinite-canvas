import { preferredModelForMode } from "./videoModelCompat"

/** UI 生成方式 → catalog recommended_modes 键 */
export const VID_MODE_TO_REC_KEY = {
  文生: "t2v",
  参考: "i2v",
  首尾帧: "keyframe",
}

/**
 * 前端展示 catalog：不依赖 API 是否已重启，保证星标与小白向简述一致。
 * summary 不写步数、fp、T2V 等技术词。
 */
export const MODEL_DISPLAY = {
  // ── 图像 ──
  "qwen-image": {
    summary: "输入文字，生成图片",
    recommended: true,
    sort_rank: 10,
  },
  "qwen-image-edit": {
    summary: "上传图片，按描述修改",
    sort_rank: 20,
  },
  hidream: {
    summary: "另一种画面风格",
    sort_rank: 30,
  },
  "flux-pulid": {
    summary: "让角色长相保持一致",
    recommended: true,
    sort_rank: 25,
  },
  "qwen-image-restore": {
    summary: "修复老旧模糊的照片",
    sort_rank: 60,
  },
  "qwen-image-material": {
    summary: "把画面材质换成另一张图",
    sort_rank: 70,
  },
  sdxl: {
    summary: "经典文生图",
    sort_rank: 90,
  },
  "jimeng-5.0-lite": {
    summary: "云端出图",
    sort_rank: 100,
  },
  // ── 视频 ──
  "ltx2-fp4": {
    summary: "开源文/图生视频（实验向）；人物戏请用参考图，默认关音频",
    recommended_modes: ["i2v", "t2v"],
    sort_rank: 40,
  },
  "wan-i2v": {
    summary: "首尾两张图生成过渡视频（推荐图生）",
    recommended: true,
    recommended_modes: ["keyframe"],
    sort_rank: 15,
  },
  "wan-2.6": {
    summary: "只用文字生成视频",
    recommended: true,
    recommended_modes: ["t2v"],
    sort_rank: 10,
  },
  "ltx23-i2av": {
    summary: "生成带声音的视频",
    sort_rank: 35,
  },
  "wan-fun-inpaint": {
    summary: "首尾帧专用",
    sort_rank: 45,
  },
  "ltx-video": {
    summary: "轻量文生视频",
    sort_rank: 90,
  },
  "seedance-2.0": {
    summary: "云端生成视频",
    sort_rank: 100,
  },
  // ── 文本 ──
  "qwen-plus": {
    summary: "写作与剧本扩写",
    recommended: true,
    sort_rank: 10,
  },
  "qwen-turbo": {
    summary: "写作扩写，回复更快",
    sort_rank: 20,
  },
  "qwen-max": {
    summary: "写作扩写，效果更好",
    sort_rank: 30,
  },
}

function recKeyForVidMode(vidMode) {
  if (!vidMode) return null
  return VID_MODE_TO_REC_KEY[vidMode] || null
}

/** 合并 API 模型与前端展示 catalog */
export function enrichModel(model) {
  if (!model?.id) return model
  const cat = MODEL_DISPLAY[model.id]
  if (!cat) return model
  return {
    ...model,
    summary: cat.summary || model.summary,
    recommended: cat.recommended ?? model.recommended ?? false,
    recommended_modes: cat.recommended_modes ?? model.recommended_modes ?? [],
    sort_rank: cat.sort_rank ?? model.sort_rank ?? 100,
  }
}

export function enrichModels(models = []) {
  return (models || []).map(enrichModel)
}

/**
 * 当前上下文下该模型是否显示推荐星标。
 * @param {object} model
 * @param {{ vidMode?: string, category?: string }} opts
 */
export function isModelRecommended(model, { vidMode } = {}) {
  const m = enrichModel(model)
  if (!m?.id) return false
  const modes = m.recommended_modes || []
  const recKey = recKeyForVidMode(vidMode)
  if (recKey && modes.length > 0) {
    return modes.includes(recKey)
  }
  return Boolean(m.recommended)
}

/**
 * 展示用排序：sort_rank → 推荐优先 → 名称。
 */
export function sortModelsForDisplay(models = [], { vidMode } = {}) {
  const list = enrichModels(models)
  list.sort((a, b) => {
    const rankA = Number(a.sort_rank ?? 100)
    const rankB = Number(b.sort_rank ?? 100)
    if (rankA !== rankB) return rankA - rankB
    const recA = isModelRecommended(a, { vidMode }) ? 0 : 1
    const recB = isModelRecommended(b, { vidMode }) ? 0 : 1
    if (recA !== recB) return recA - recB
    const nameA = (a.display_name || a.id || "").toLowerCase()
    const nameB = (b.display_name || b.id || "").toLowerCase()
    return nameA.localeCompare(nameB, "zh-CN")
  })
  return list
}

/**
 * 挑选默认模型：推荐项 → 视频模式偏好 → 列表首项。
 */
export function pickDefaultModel(models = [], { vidMode, category } = {}) {
  const sorted = sortModelsForDisplay(models, { vidMode })
  if (!sorted.length) return null

  const recommended = sorted.find((m) => isModelRecommended(m, { vidMode }))
  if (recommended?.id) return recommended.id

  if (category === "video" || vidMode) {
    const preferred = preferredModelForMode(vidMode || "文生", sorted)
    if (preferred) return preferred
  }

  return sorted[0]?.id || null
}
