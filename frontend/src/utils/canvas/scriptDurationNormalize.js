import { clampShotDuration, syncRowKeyframesToDuration } from "./scriptTableKeyframes"
import { clampTarget } from "./videoDurationIntent"

const MIN_SHOT_SEC = 4
const MAX_SHOT_SEC = 15

export function sumSegmentShotDuration(segments = []) {
  let total = 0
  for (const seg of segments || []) {
    for (const shot of seg.shots || []) {
      total += Number(shot.duration) || 0
    }
  }
  return total
}

/** 将分镜提示词镜头时长缩放/裁剪到目标总时长 */
export function normalizeSegmentsToTargetDuration(segments, targetSec) {
  const target = clampTarget(targetSec)
  if (!target || !Array.isArray(segments) || segments.length === 0) {
    return { segments, warning: null }
  }

  const flat = []
  for (let si = 0; si < segments.length; si += 1) {
    const seg = segments[si]
    for (let ji = 0; ji < (seg.shots || []).length; ji += 1) {
      flat.push({ si, ji, shot: seg.shots[ji] })
    }
  }
  if (flat.length === 0) return { segments, warning: null }

  let total = flat.reduce((s, x) => s + (Number(x.shot.duration) || MIN_SHOT_SEC), 0)
  let warning = null

  const maxShots = Math.floor(target / MIN_SHOT_SEC)
  if (flat.length > maxShots) {
    warning = `镜头数（${flat.length}）超过 ${formatTarget(target)} 可容纳上限（约 ${maxShots} 镜），已保留前 ${maxShots} 镜并合并时长。建议在「分镜提示词」重新生成或减少场景。`
    const kept = new Set(flat.slice(0, maxShots).map((x) => `${x.si}:${x.ji}`))
    const nextSegments = segments.map((seg, si) => ({
      ...seg,
      shots: (seg.shots || []).filter((_, ji) => kept.has(`${si}:${ji}`)),
    }))
    return normalizeSegmentsToTargetDuration(nextSegments, target)
  }

  if (total <= target + 1 && total >= target - 1) {
    return { segments, warning }
  }

  const scale = target / Math.max(total, 1)
  for (const item of flat) {
    const raw = Number(item.shot.duration) || MIN_SHOT_SEC
    item.shot.duration = clampShotDuration(
      Math.max(MIN_SHOT_SEC, Math.min(MAX_SHOT_SEC, Math.round(raw * scale)))
    )
  }

  total = flat.reduce((s, x) => s + (Number(x.shot.duration) || MIN_SHOT_SEC), 0)
  let guard = 0
  while (total > target && guard < 500) {
    guard += 1
    const candidate = flat
      .filter((x) => (Number(x.shot.duration) || 0) > MIN_SHOT_SEC)
      .sort((a, b) => (Number(b.shot.duration) || 0) - (Number(a.shot.duration) || 0))[0]
    if (!candidate) break
    candidate.shot.duration -= 1
    total -= 1
  }
  guard = 0
  while (total < target && guard < 500) {
    guard += 1
    const candidate = flat
      .filter((x) => (Number(x.shot.duration) || 0) < MAX_SHOT_SEC)
      .sort((a, b) => (Number(a.shot.duration) || 0) - (Number(b.shot.duration) || 0))[0]
    if (!candidate) break
    candidate.shot.duration += 1
    total += 1
  }

  const nextSegments = segments.map((seg, si) => ({
    ...seg,
    shots: (seg.shots || []).map((shot, ji) => {
      const hit = flat.find((x) => x.si === si && x.ji === ji)
      return hit ? { ...shot, duration: hit.shot.duration } : shot
    }),
    duration: (seg.shots || []).reduce((s, sh) => s + (Number(sh.duration) || 0), 0),
  }))

  if (Math.abs(total - target) > 2) {
    warning =
      warning
      || `已按目标时长 ${formatTarget(target)} 调整各镜时长（当前合计约 ${total} 秒）。`
  }

  return { segments: nextSegments, warning }
}

function formatTarget(sec) {
  if (sec < 60) return `${sec} 秒`
  return `${Math.round(sec / 60)} 分钟`
}

export function normalizeRowsToTargetDuration(rows, targetSec) {
  const target = clampTarget(targetSec)
  if (!target || !rows?.length) return { rows, warning: null }

  let list = rows.map((r) => ({ ...r }))
  let warning = null
  const maxShots = Math.floor(target / MIN_SHOT_SEC)

  if (list.length > maxShots) {
    warning = `共 ${list.length} 镜超过目标时长可容纳的约 ${maxShots} 镜，已保留前 ${maxShots} 镜。`
    list = list.slice(0, maxShots).map((r, i) => ({ ...r, shotNumber: i + 1 }))
  }

  let total = list.reduce((s, r) => s + (Number(r.duration) || MIN_SHOT_SEC), 0)
  if (total <= 0) total = list.length * MIN_SHOT_SEC

  const scale = target / total
  list = list.map((r) => {
    const d = Math.max(
      MIN_SHOT_SEC,
      Math.min(MAX_SHOT_SEC, Math.round((Number(r.duration) || MIN_SHOT_SEC) * scale))
    )
    return syncRowKeyframesToDuration({ ...r, duration: d })
  })

  total = list.reduce((s, r) => s + (Number(r.duration) || 0), 0)
  let guard = 0
  while (total > target && guard < 400) {
    guard += 1
    const idx = list.reduce((best, r, i) => {
      if ((r.duration || 0) <= MIN_SHOT_SEC) return best
      if (best < 0 || (list[best].duration || 0) < (r.duration || 0)) return i
      return best
    }, -1)
    if (idx < 0) break
    list[idx] = syncRowKeyframesToDuration({ ...list[idx], duration: list[idx].duration - 1 })
    total -= 1
  }

  return { rows: list, warning }
}
