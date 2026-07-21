import { makeEmptyScriptRow } from "./scriptTableRowFactory"
import { pickShotDirectorFields } from "./shotDirectorFields"
import { formatScreenplayParagraphs } from "./textFormat"
function sortScriptRows(rows) {
  return [...(rows || [])].sort(
    (a, b) => (a.shotNumber ?? 0) - (b.shotNumber ?? 0)
  )
}

export function makeSegmentId() {
  return `seg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

/** 规范化 API / 旧节点上的片段结构 */
export function normalizeScriptSegments(segments) {
  if (!Array.isArray(segments)) return []
  return segments.map((seg, i) => ({
    id: (seg?.id || `seg-${i + 1}`).toString(),
    title: (seg?.title || "").trim() || `片段 ${i + 1}`,
    description: (seg?.description || "").trim(),
    duration: Number(seg?.duration) || 0,
  }))
}

/** 从 generate-shots 的 segments 生成 { segments, rows } */
export function segmentsToScriptPayload(rawSegments) {
  const segments = []
  const rows = []
  let shotNum = 1

  for (let si = 0; si < (rawSegments || []).length; si += 1) {
    const seg = rawSegments[si]
    const segId = (seg?.id || `seg-${si + 1}`).toString()
    segments.push({
      id: segId,
      title: (seg?.title || "").trim() || `片段 ${si + 1}`,
      description: (seg?.description || "").trim(),
      duration: Number(seg?.duration) || 0,
    })

    for (const shot of seg?.shots || []) {
      const row = makeEmptyScriptRow(shotNum)
      const prompt = formatScreenplayParagraphs((shot?.prompt || "").trim())
      const director = pickShotDirectorFields(shot)
      rows.push({
        ...row,
        segmentId: segId,
        shotNumber: shotNum,
        duration: shot.duration ?? 8,
        ...director,
        prompt,
        description: prompt,
      })
      shotNum += 1
    }
  }

  return { segments, rows }
}

/** 从 rows 反推 segments（旧数据无 segments 时） */
export function inferSegmentsFromRows(rows) {
  const sorted = sortScriptRows(rows)
  const segOrder = []
  const segMap = new Map()

  for (const row of sorted) {
    const sid = row.segmentId || "_default"
    if (!segMap.has(sid)) {
      segMap.set(sid, {
        id: sid === "_default" ? makeSegmentId() : sid,
        title: row.segmentTitle || "",
        description: row.segmentDescription || "",
        duration: 0,
      })
      segOrder.push(sid)
    }
  }

  return segOrder.map((sid) => {
    const seg = segMap.get(sid)
    const segRows = sorted.filter((r) => (r.segmentId || "_default") === sid)
    const duration = segRows.reduce((sum, r) => sum + (Number(r.duration) || 0), 0)
    return {
      ...seg,
      id: sid === "_default" ? seg.id : sid,
      duration: seg.duration || duration,
    }
  })
}

export function resolveScriptTableSegments(rows, segments) {
  const norm = normalizeScriptSegments(segments)
  if (norm.length > 0) return norm
  if (Array.isArray(rows) && rows.length > 0) return inferSegmentsFromRows(rows)
  return []
}

/** 大纲下游已连接的分镜表（直连或经旧 shot-script） */
export function findScriptTableForOutline(outlineNodeId, nodes, edges) {
  const list = nodes || []
  const es = edges || []
  const outline = list.find((n) => n.id === outlineNodeId)
  if (outline?.data?.linkedScriptTableId) {
    const linked = list.find((n) => n.id === outline.data.linkedScriptTableId)
    if (linked?.type === "script-table") return linked.id
  }

  for (const e of es) {
    if (e.source !== outlineNodeId) continue
    const target = list.find((n) => n.id === e.target)
    if (target?.type === "script-table") return target.id
    if (target?.type === "shot-script") {
      const tableEdge = es.find((te) => te.source === target.id)
      const table = list.find((n) => n.id === tableEdge?.target)
      if (table?.type === "script-table") return table.id
    }
  }
  return null
}

/** 简单/专业模式共用的「片段头 + 镜」列表 */
export function buildGroupedShotList(rows, segments) {
  const sorted = sortScriptRows(rows)
  const normSegs = resolveScriptTableSegments(sorted, segments)

  if (normSegs.length === 0) {
    return sorted.map((row) => ({ kind: "row", row }))
  }

  const rowsBySeg = new Map()
  for (const row of sorted) {
    const sid = row.segmentId || normSegs[0]?.id || "_default"
    if (!rowsBySeg.has(sid)) rowsBySeg.set(sid, [])
    rowsBySeg.get(sid).push(row)
  }

  const items = []
  const placed = new Set()

  for (const seg of normSegs) {
    const segRows = rowsBySeg.get(seg.id) || []
    if (seg.title || seg.description || segRows.length > 0) {
      items.push({ kind: "segment", segment: seg })
    }
    for (const row of segRows) {
      items.push({ kind: "row", row })
      placed.add(row.id)
    }
  }

  for (const row of sorted) {
    if (!placed.has(row.id)) {
      items.push({ kind: "row", row })
    }
  }

  return items
}

export function patchSegmentInList(segments, segmentId, patch) {
  return normalizeScriptSegments(
    (segments || []).map((s) => (s.id === segmentId ? { ...s, ...patch } : s))
  )
}
