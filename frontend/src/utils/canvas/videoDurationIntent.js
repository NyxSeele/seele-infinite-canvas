/** 从用户创意文案解析目标成片时长（秒） */

const MIN_TARGET_SEC = 15
const MAX_TARGET_SEC = 15 * 60

export function parseTargetDurationSec(text) {
  const s = String(text || "")
  if (!s.trim()) return null

  const minMatch = s.match(/(\d+(?:\.\d+)?)\s*(?:分钟|分|min(?:ute)?s?)/i)
  if (minMatch) {
    const sec = Math.round(Number(minMatch[1]) * 60)
    if (sec > 0) return clampTarget(sec)
  }

  const secMatch = s.match(/(\d+(?:\.\d+)?)\s*(?:秒钟|秒|s(?:ec(?:ond)?s?)?)(?!\s*(?:一|每)?镜)/i)
  if (secMatch) {
    const sec = Math.round(Number(secMatch[1]))
    if (sec >= 10) return clampTarget(sec)
  }

  const shortMatch = s.match(/(\d+)\s*秒(?:的)?(?:短)?片/)
  if (shortMatch) {
    return clampTarget(Number(shortMatch[1]))
  }

  return null
}

export function clampTarget(sec) {
  const n = Math.round(Number(sec) || 0)
  if (n <= 0) return null
  return Math.min(MAX_TARGET_SEC, Math.max(MIN_TARGET_SEC, n))
}

export function formatDurationSec(sec) {
  const n = Number(sec) || 0
  if (n <= 0) return "—"
  if (n < 60) return `${n} 秒`
  const m = Math.floor(n / 60)
  const r = n % 60
  if (r === 0) return `${m} 分钟`
  return `${m} 分 ${r} 秒`
}

export function sumRowDurations(rows = []) {
  return (rows || []).reduce((s, r) => s + (Number(r.duration) || 0), 0)
}

/** 沿画布连线向上游查找目标成片时长 */
export function findUpstreamTargetDuration(nodes, edges, startNodeId) {
  const visited = new Set()
  const walk = (nodeId) => {
    if (!nodeId || visited.has(nodeId)) return null
    visited.add(nodeId)
    const node = (nodes || []).find((n) => n.id === nodeId)
    if (!node) return null
    const d = node.data?.targetVideoDurationSec
    if (d) return clampTarget(d)
    const fromIdea = parseTargetDurationSec(node.data?.sourceIdea || node.data?.idea || "")
    if (fromIdea) return fromIdea
    if (node.type === "text-response" || node.type === "text-note") {
      const t = parseTargetDurationSec(node.data?.content || node.data?.text || "")
      if (t) return t
    }
    const incoming = (edges || []).filter((e) => e.target === nodeId)
    for (const e of incoming) {
      const up = walk(e.source)
      if (up) return up
    }
    return null
  }
  return walk(startNodeId)
}
