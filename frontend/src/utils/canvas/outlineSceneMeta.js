import { SHOT_DIRECTOR_FIELDS } from "./shotDirectorFields"

const SNAKE_TO_CAMEL = {
  color_grade: "colorGrade",
  sound_design: "soundDesign",
}

export function normalizeOutlineScene(scene = {}) {
  const s = { ...scene }
  for (const [snake, camel] of Object.entries(SNAKE_TO_CAMEL)) {
    if (!s[camel] && s[snake]) s[camel] = s[snake]
  }
  return s
}

function readSceneField(scene, key) {
  if (key === "colorGrade") return (scene.colorGrade || scene.color_grade || "").trim()
  if (key === "soundDesign") return (scene.soundDesign || scene.sound_design || "").trim()
  return (scene[key] || "").trim()
}

/** 大纲场景可展示的元信息（有内容才显示） */
export function outlineSceneMetaEntries(scene = {}) {
  const s = normalizeOutlineScene(scene)
  const entries = []

  const ts = (s.time_start || s.timeStart || "").trim()
  const te = (s.time_end || s.timeEnd || "").trim()
  if (ts || te) {
    const value = ts && te ? `${ts} – ${te}` : ts || te
    entries.push({ key: "timeRange", label: "时间", value, field: "time_start" })
  }

  if (s.characters?.trim()) {
    entries.push({ key: "characters", label: "人物", value: s.characters.trim(), field: "characters" })
  }
  if (s.mood?.trim()) {
    entries.push({ key: "mood", label: "氛围", value: s.mood.trim(), field: "mood" })
  }

  for (const { key, label } of SHOT_DIRECTOR_FIELDS) {
    const v = readSceneField(s, key)
    if (v) entries.push({ key, label, value: v, field: key })
  }

  return entries
}

export function patchSceneMetaField(scene, field, value) {
  if (field === "time_start") {
    const parts = String(value || "").split(/[–\-—~至]/).map((s) => s.trim())
    return {
      ...scene,
      time_start: parts[0] || "",
      time_end: parts[1] || scene.time_end || "",
    }
  }
  return { ...scene, [field]: value }
}
