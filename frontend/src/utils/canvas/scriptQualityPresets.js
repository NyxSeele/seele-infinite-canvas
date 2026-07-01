/** 氛围与画质预设包（一键填入导演参数 + 画质描述） */
export const SCRIPT_QUALITY_PRESETS = [
  {
    id: "auto",
    name: "由模型自己选择",
    atmosphereNote: "",
    fields: {
      camera: "",
      movement: "",
      lighting: "",
      composition: "",
      colorGrade: "",
      lens: "",
      performance: "",
      soundDesign: "",
    },
  },
  {
    id: "cinematic",
    name: "电影感",
    atmosphereNote:
      "电影级画质，超写实，变形宽银幕感，浅景深，胶片颗粒，高对比，避免游戏 CG 感",
    fields: {
      camera: "电影感构图",
      movement: "稳定运镜",
      lighting: "自然光，侧逆光",
      composition: "三分法",
      colorGrade: "电影调色，适度饱和",
      lens: "变形宽银幕镜头感",
      performance: "",
      soundDesign: "环境音为主，无配乐",
    },
  },
  {
    id: "anime",
    name: "二次元",
    atmosphereNote: "日系动漫，赛璐璐，线条清晰，色彩明快，避免写实照片感",
    fields: {
      camera: "中景",
      movement: "固定",
      lighting: "平光",
      composition: "对称",
      colorGrade: "高饱和动漫色",
      lens: "动画镜头",
      soundDesign: "",
    },
  },
  {
    id: "retro_atomic",
    name: "复古原子朋克",
    atmosphereNote:
      "1960s 复古未来主义，原子朋克，暖黄与青蓝高对比，胶片质感，低饱和复古滤镜",
    fields: {
      camera: "广角低机位",
      movement: "跟拍",
      lighting: "强烈直射阳光，自然光晕",
      composition: "对角线构图",
      colorGrade: "60s 复古科幻色调",
      lens: "Panavision 电影镜头感",
      soundDesign: "环境音，无 BGM",
    },
  },
  {
    id: "documentary",
    name: "纪录片",
    atmosphereNote: "手持纪录片质感，自然光，真实皮肤纹理，轻微颗粒",
    fields: {
      camera: "中近景",
      movement: "手持轻微晃动",
      lighting: "自然光",
      composition: "过肩或环境留白",
      colorGrade: "中性真实",
      lens: "35mm 纪实感",
      soundDesign: "现场收音",
    },
  },
  {
    id: "commercial",
    name: "商业广告",
    atmosphereNote: "高质感商业广告，干净布光，高锐度，色彩饱满，画面通透",
    fields: {
      camera: "特写 / 产品镜头",
      movement: "慢速推轨",
      lighting: "柔光箱，轮廓光",
      composition: "中心构图",
      colorGrade: "明亮高饱和",
      lens: "浅景深产品镜头",
      soundDesign: "",
    },
  },
]

export function getQualityPreset(id) {
  return SCRIPT_QUALITY_PRESETS.find((p) => p.id === id) || null
}

/** 未指定画风或仍为旧默认 cinematic 时，回落到 auto */
export function withDefaultQualityPreset(row, defaultId = "auto") {
  if (!row || typeof row !== "object") return row
  const id = row.qualityPresetId
  if (id && id !== "cinematic" && id !== "") return row
  return applyQualityPresetToRow(row, defaultId)
}

export function withDefaultQualityPresetRows(rows, defaultId = "auto") {
  return (rows || []).map((row) => withDefaultQualityPreset(row, defaultId))
}

export function applyQualityPresetToRow(row, presetId) {
  const preset = getQualityPreset(presetId)
  if (!preset) return row
  if (presetId === "auto") {
    return {
      ...row,
      qualityPresetId: "auto",
      atmosphereNote: "",
      camera: "",
      movement: "",
      lighting: "",
      composition: "",
      colorGrade: "",
      lens: "",
      performance: "",
      soundDesign: "",
    }
  }
  return {
    ...row,
    qualityPresetId: presetId,
    atmosphereNote: preset.atmosphereNote,
    ...preset.fields,
  }
}
