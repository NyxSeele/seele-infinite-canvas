import { characterCastLibrary, resolveSceneRefsForRow } from "./entityRefs"
import { normalizeSceneLibrary } from "./sceneLibrary"
import { SHOT_DIRECTOR_FIELDS } from "./shotDirectorFields"
import {
  formatKeyframeTimeRange,
  keyframeText,
  redistributeKeyframeTimes,
  shotPromptText,
} from "./scriptTableKeyframes"
import { formatStyleForPrompt } from "./styleReferenceFormat"

function entityLines(castLibrary, sceneLibrary, row) {
  const chars = characterCastLibrary(castLibrary)
  const scenes = row
    ? resolveSceneRefsForRow(row, sceneLibrary)
    : normalizeSceneLibrary(sceneLibrary, { requireImage: false })
  const lines = []
  for (const c of chars) {
    lines.push(`- 人物「${c.name}」：保持与设定参考图一致的视觉特征`)
  }
  for (const s of scenes) {
    lines.push(`- 场景「${s.name}」：保持与场景参考图一致的空间与氛围`)
  }
  return lines.length ? lines.join("\n") : "（未绑定设定库，可在提示词中用 @ 引用）"
}

function directorBlock(row, styleReference = null) {
  const lines = SHOT_DIRECTOR_FIELDS.map(({ key, label }) => {
    const v = row[key]?.trim()
    return v ? `${label}：${v}` : ""
  }).filter(Boolean)
  if (row.atmosphereNote?.trim()) {
    lines.unshift(`画质风格：${row.atmosphereNote.trim()}`)
  }
  const styleBlock = formatStyleForPrompt(styleReference)
  if (styleBlock) {
    lines.push(styleBlock)
  }
  return lines.length ? lines.join("\n") : "（未填写，可在工具栏应用画质预设）"
}

function framesBlock(row, keyframeId) {
  const rowNorm = redistributeKeyframeTimes(row)
  const kfs = rowNorm.keyframes || []
  const targets = keyframeId
    ? kfs.filter((k) => k.id === keyframeId)
    : kfs

  if (!targets.length) return "（暂无分镜格）"

  return targets
    .map((kf, i) => {
      const time = formatKeyframeTimeRange(kf)
      const text = keyframeText(kf) || "（待填写本格画面）"
      return [
        `分镜${i + 1}（${time}）${kf.label ? ` · ${kf.label}` : ""}`,
        text,
      ].join("\n")
    })
    .join("\n\n")
}

/**
 * 规则版三层 prompt 包（小云雀式结构）
 */
export function buildShotPromptPackage(row, castLibrary = [], options = {}) {
  const { keyframeId = null, sceneLibrary = [], styleReference = null } = options
  const rowNorm = redistributeKeyframeTimes(row)
  const shot = shotPromptText(rowNorm)
  const sound = rowNorm.soundNote?.trim() || "无背景音乐，保留必要环境音效"

  const basic = [
    "【基础设定】",
    `镜号：${rowNorm.shotNumber ?? 1} · 时长：${rowNorm.duration ?? 8} 秒`,
    shot ? `剧情/主体：${shot}` : "剧情/主体：（待填写整镜剧情）",
    entityLines(castLibrary, sceneLibrary, rowNorm),
    `声音：${sound}`,
  ].join("\n")

  const atmosphere = ["【氛围与画质】", directorBlock(rowNorm, styleReference)].join("\n")

  const frames = ["【画面内容】", framesBlock(rowNorm, keyframeId)].join("\n")

  const fullText = `${basic}\n\n${atmosphere}\n\n${frames}`

  let apiDescription = shot
  if (keyframeId) {
    const kf = (rowNorm.keyframes || []).find((k) => k.id === keyframeId)
    if (kf) {
      const frame = keyframeText(kf)
      const time = formatKeyframeTimeRange(kf)
      apiDescription = [shot, frame && `【${time} ${kf.label || "本格"}】${frame}`]
        .filter(Boolean)
        .join("；")
    }
  } else {
    const parts = (rowNorm.keyframes || [])
      .map((kf) => {
        const t = keyframeText(kf)
        if (!t) return ""
        return `【${formatKeyframeTimeRange(kf)} ${kf.label || "格"}】${t}`
      })
      .filter(Boolean)
    if (parts.length) {
      apiDescription = [shot, ...parts].filter(Boolean).join("；")
    }
  }

  return {
    basic,
    atmosphere,
    frames,
    fullText,
    apiDescription: apiDescription.trim(),
  }
}
