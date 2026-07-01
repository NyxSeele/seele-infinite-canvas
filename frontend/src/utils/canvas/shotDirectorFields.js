/** 分镜导演级参数字段（分镜提示词卡 + 分镜表共用） */
export const SHOT_DIRECTOR_FIELDS = [
  { key: "camera", label: "景别", placeholder: "全景 / 中景 / 特写" },
  { key: "movement", label: "运镜", placeholder: "固定 / 推轨 / 横摇" },
  { key: "lighting", label: "光影", placeholder: "侧光 / 逆光 / 霓虹" },
  { key: "composition", label: "构图", placeholder: "三分法 / 对称 / 过肩" },
  { key: "colorGrade", label: "色调", placeholder: "冷青 / 暖黄 / 高对比" },
  { key: "lens", label: "镜头", placeholder: "35mm / 浅景深 / 广角" },
  { key: "performance", label: "表演", placeholder: "情绪 / 肢体 / 视线" },
  { key: "soundDesign", label: "声音", placeholder: "环境音 / 对白 / 配乐" },
]

export function pickShotDirectorFields(shot = {}) {
  const out = {}
  for (const { key } of SHOT_DIRECTOR_FIELDS) {
    const v = shot[key]
    if (v != null && String(v).trim()) out[key] = String(v).trim()
  }
  return out
}

export function shotDirectorSummary(shot = {}) {
  return SHOT_DIRECTOR_FIELDS.filter(({ key, label }) => shot[key]?.trim())
    .map(({ key, label }) => `${label}：${shot[key].trim()}`)
    .join(" · ")
}

export function appendDirectorFieldsToDescription(description, shot = {}) {
  const base = String(description || "").trim()
  const extras = SHOT_DIRECTOR_FIELDS.map(({ key, label }) => {
    const v = shot[key]?.trim()
    return v ? `${label}：${v}` : ""
  }).filter(Boolean)
  if (!extras.length) return base
  if (!base) return extras.join("；")
  return `${base}；${extras.join("；")}`
}
