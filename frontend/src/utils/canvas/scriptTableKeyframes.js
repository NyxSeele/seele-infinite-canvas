/** 分镜表：镜头行 + 多格关键帧 */

export const MAX_SHOT_DURATION = 15

export const KEYFRAME_LABEL_PRESETS = ["起幅", "推进", "高潮", "落幅"]

export function clampShotDuration(sec) {
  const n = Number(sec) || 8
  return Math.min(MAX_SHOT_DURATION, Math.max(1, n))
}

export function makeKeyframeId() {
  return `kf-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

/** 保障分镜格列表始终为数组（兼容脏数据或非数组 keyframes） */
export function asKeyframeArray(value) {
  return Array.isArray(value) ? value : []
}

export function makeEmptyKeyframe(index = 0, label) {
  const preset = KEYFRAME_LABEL_PRESETS[index]
  return {
    id: makeKeyframeId(),
    index,
    label: label || preset || `格${index + 1}`,
    timeStart: 0,
    timeEnd: 0,
    prompt: "",
    description: "",
    promptEn: "",
    promptMentions: [],
    /** @deprecated 节拍格构图参考已下线；保留字段仅供历史 canvas_data 读取 */
    referenceImage: null,
    resultUrl: null,
    status: "idle",
    builtPrompt: null,
    compiledPromptPackage: null,
    negativePrompt: null,
    imageGenNodeId: null,
    error: null,
  }
}

/** 将镜头时长均分到各分镜格 */
export function redistributeKeyframeTimes(row) {
  const duration = clampShotDuration(row?.duration)
  const kfs = [...asKeyframeArray(row?.keyframes)]
  if (kfs.length === 0) return row

  const step = duration / kfs.length
  const nextKfs = kfs.map((kf, i) => {
    const start = Math.round(i * step * 10) / 10
    const end =
      i === kfs.length - 1
        ? duration
        : Math.round((i + 1) * step * 10) / 10
    return {
      ...kf,
      index: i,
      timeStart: start,
      timeEnd: end,
    }
  })

  return { ...row, keyframes: nextKfs }
}

export function formatKeyframeTimeRange(kf) {
  const start = Number(kf?.timeStart) || 0
  const end = Number(kf?.timeEnd) || 0
  if (end > start) return `${start}s–${end}s`
  return `${start}s`
}

export function keyframeCountForDuration(durationSec = 8) {
  const d = clampShotDuration(durationSec)
  if (d <= 4) return 2
  if (d <= 9) return 3
  return 4
}

export function defaultKeyframesForDuration(durationSec = 8) {
  const count = keyframeCountForDuration(durationSec)
  return Array.from({ length: count }, (_, i) => makeEmptyKeyframe(i))
}

/** 按镜时长调整分镜格数量并均分时间（简单模式改时长用） */
/** 将 LLM 拆分的 beats 写入行内 keyframes */
export function applyBeatsToRow(row, beats = []) {
  if (!Array.isArray(beats) || beats.length === 0) return row
  const existing = row.keyframes || []
  const keyframes = beats.map((beat, i) => {
    const prev = existing[i] || {}
    return {
      ...makeEmptyKeyframe(i, beat.label),
      ...prev,
      id: prev.id || makeKeyframeId(),
      index: i,
      label: beat.label || prev.label || `格${i + 1}`,
      timeStart: Number(beat.time_start ?? beat.timeStart) || 0,
      timeEnd: Number(beat.time_end ?? beat.timeEnd) || 0,
      prompt: beat.prompt || beat.prompt_zh || "",
      description: beat.prompt || beat.prompt_zh || "",
      promptEn: beat.prompt_en || beat.promptEn || "",
      actionNote: beat.action_note || beat.actionNote || "",
      status: "idle",
      error: null,
      resultUrl: null,
      imageGenNodeId: null,
      compiledPromptPackage: null,
    }
  })
  return syncRowFromKeyframes({
    ...row,
    duration: clampShotDuration(row.duration),
    keyframes,
    beatsSplitAt: Date.now(),
  })
}

export function rowStoryboardReady(row) {
  const kfs = row?.keyframes || []
  return kfs.length > 0 && kfs.every((kf) => kf.status === "completed" && kf.resultUrl)
}

/** 镜头视频是否已生成完成（以 video-gen 节点状态为准，失败/生成中均视为未完成） */
export function rowVideoReady(row, nodes = []) {
  const vid = row?.videoGenNodeId
  if (!vid) return false
  const list = Array.isArray(nodes) ? nodes : []
  const node = list.find((n) => n.id === vid && n.type === "video-gen")
  if (!node) return false
  const status = node.data?.status
  if (status === "failed") return false
  return status === "completed" && Boolean(node.data?.videoUrl)
}

export function rowHasBeatPrompts(row) {
  if (row?.beatsSplitAt) return true
  const kfs = row?.keyframes || []
  if (kfs.length === 0) return false
  return kfs.some((kf) => keyframeText(kf) || keyframeApiText(kf))
}

export function syncRowKeyframesToDuration(row) {
  const duration = clampShotDuration(row?.duration)
  const targetCount = keyframeCountForDuration(duration)
  let kfs = [...(row?.keyframes || [])]

  if (kfs.length < targetCount) {
    while (kfs.length < targetCount) {
      kfs.push(makeEmptyKeyframe(kfs.length))
    }
  } else if (kfs.length > targetCount) {
    kfs = kfs.slice(0, targetCount).map((kf, i) => ({ ...kf, index: i }))
  } else {
    kfs = kfs.map((kf, i) => ({ ...kf, index: i }))
  }

  return redistributeKeyframeTimes(
    syncRowFromKeyframes({ ...row, duration, keyframes: kfs })
  )
}

export function keyframeText(kf) {
  return (kf?.prompt || kf?.description || "").trim()
}

/** 图像/视频 API 用英文描述；无英文时回退中文 */
export function keyframeApiText(kf) {
  return (kf?.promptEn || kf?.prompt_en || keyframeText(kf) || "").trim()
}

export function shotPromptText(row) {
  return (row?.prompt || row?.description || "").trim()
}

/** 单格生成用的完整描述：整镜剧情 + 本格画面 + 导演参数在外层拼接 */
export function keyframeGenerationText(row, keyframe) {
  const parts = []
  const shot = shotPromptText(row)
  const frame = keyframeText(keyframe)
  if (shot) parts.push(shot)
  if (frame && frame !== shot) parts.push(`【${keyframe.label || "本格"}】${frame}`)
  else if (frame && !shot) parts.push(frame)
  return parts.join("；")
}

/** 出图/出视频 API 用：优先英文节拍与描述 */
export function keyframeGenerationApiText(row, keyframe) {
  const parts = []
  const shot = shotPromptText(row)
  const frame = keyframeApiText(keyframe)
  if (shot && !frame) parts.push(shot)
  if (frame && frame !== shot) parts.push(`[${keyframe.label || "frame"}] ${frame}`)
  else if (frame && !shot) parts.push(frame)
  return parts.join("; ")
}

export function aggregateRowStatus(keyframes = []) {
  const list = keyframes || []
  if (list.length === 0) return "idle"
  if (list.some((k) => k.status === "generating")) return "generating"
  if (list.some((k) => k.status === "failed")) return "failed"
  if (list.every((k) => k.status === "completed" && k.resultUrl)) return "completed"
  if (list.some((k) => k.status === "completed")) return "completed"
  return "idle"
}

export function syncRowFromKeyframes(row) {
  const keyframes = asKeyframeArray(row.keyframes)
  const lastWithResult = [...keyframes].reverse().find((k) => k.resultUrl)
  return {
    ...row,
    status: aggregateRowStatus(keyframes),
    resultUrl: lastWithResult?.resultUrl ?? row.resultUrl ?? null,
    error: keyframes.find((k) => k.error)?.error ?? row.error ?? null,
  }
}

/**
 * 大分镜行规范化：默认不含节拍格（节拍在 script-beat-card 节点）。
 * 行内 keyframes 仅作迁移前暂存，由 migrateCanvasBeatCards 迁入节拍卡片。
 */
export function normalizeScriptRow(row) {
  if (!row || typeof row !== "object") return row

  const beatCardNodeId = row.beatCardNodeId ?? null
  const inlineKeyframes = asKeyframeArray(row.keyframes)

  const directImageGenNodeId =
    row.directImageGenNodeId ?? (inlineKeyframes.length === 0 ? row.imageGenNodeId : null) ?? null
  const directResultUrl =
    row.directResultUrl ?? (inlineKeyframes.length === 0 ? row.resultUrl : null) ?? null
  const directStatus =
    row.directStatus ?? (inlineKeyframes.length === 0 ? row.status : null) ?? "idle"
  const directVideoGenNodeId = row.directVideoGenNodeId ?? null

  if (inlineKeyframes.length > 0 && !beatCardNodeId) {
    return redistributeKeyframeTimes(
      syncRowFromKeyframes({
        ...row,
        beatCardNodeId,
        directImageGenNodeId,
        directResultUrl,
        directStatus,
        directVideoGenNodeId,
        keyframes: inlineKeyframes.map((kf, i) => ({
          ...makeEmptyKeyframe(i),
          ...kf,
          index: kf.index ?? i,
        })),
      })
    )
  }

  return {
    ...row,
    duration: clampShotDuration(row.duration ?? 8),
    beatCardNodeId,
    keyframes: [],
    directImageGenNodeId,
    directResultUrl,
    directStatus,
    directVideoGenNodeId,
    resultUrl: directResultUrl,
    status: directStatus,
    error: row.error ?? null,
  }
}

export function normalizeScriptRows(rows) {
  return (rows || []).map(normalizeScriptRow)
}

/** 合并镜头与所有格的 @ 提及 */
export function allPromptMentionsForRow(row) {
  const list = [...(row?.promptMentions || [])]
  for (const kf of row?.keyframes || []) {
    for (const m of kf.promptMentions || []) {
      if (!list.some((x) => x.id === m.id && x.name === m.name)) {
        list.push(m)
      }
    }
  }
  return list
}

/** 供连贯上下文：整镜文案（含各格摘要） */
export function scriptRowText(row) {
  const shot = shotPromptText(row)
  const frames = (row?.keyframes || [])
    .map((kf) => {
      const t = keyframeText(kf)
      if (!t) return ""
      const time = formatKeyframeTimeRange(kf)
      return `${kf.label || "格"}(${time}): ${t}`
    })
    .filter(Boolean)
  if (!shot && frames.length === 0) return ""
  if (!frames.length) return shot
  if (!shot) return frames.join("；")
  return `${shot}（${frames.join("；")}）`
}

export function rowHasGeneratableContent(row) {
  return Boolean(shotPromptText(row))
}

export function rowDirectImageReady(row) {
  return row?.directStatus === "completed" && Boolean(row?.directResultUrl)
}

/** 大分镜直连视频是否已完成 */
export function rowDirectVideoReady(row, nodes = []) {
  const vid = row?.directVideoGenNodeId
  if (!vid) return false
  return rowVideoReady({ videoGenNodeId: vid }, nodes)
}

export function getLastKeyframeResult(row) {
  const kfs = row?.keyframes || []
  for (let i = kfs.length - 1; i >= 0; i -= 1) {
    if (kfs[i].resultUrl) return kfs[i].resultUrl
  }
  return row?.resultUrl || null
}

export function getPreviousKeyframeInRow(row, keyframeId) {
  const kfs = row?.keyframes || []
  const idx = kfs.findIndex((k) => k.id === keyframeId)
  if (idx <= 0) return null
  return kfs[idx - 1]
}
