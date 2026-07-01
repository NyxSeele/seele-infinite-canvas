import { addEdge } from "reactflow"
import {
  aggregateRowStatus,
  applyBeatsToRow,
  asKeyframeArray,
  keyframeText,
  redistributeKeyframeTimes,
  rowDirectImageReady,
  rowDirectVideoReady,
  rowHasBeatPrompts,
  rowStoryboardReady,
  rowVideoReady,
  shotPromptText,
  syncRowFromKeyframes,
} from "./scriptTableKeyframes"
import {
  makeId,
  computeBeatCardPosition,
} from "./nodeHelpers"

export const BEAT_CARD_NODE_TYPE = "script-beat-card"
export { BEAT_CARD_WIDTH, computeBeatCardPosition } from "./nodeHelpers"
export const KEYFRAME_COUNT_WARN_THRESHOLD = 5

export function beatCardStoryboardReady(beatCardData) {
  if (!beatCardData) return false
  return rowStoryboardReady({ keyframes: beatCardData.keyframes || [] })
}

export function beatCardVideoReady(beatCardData, nodes = []) {
  if (!beatCardData?.videoGenNodeId) return false
  return rowVideoReady({ videoGenNodeId: beatCardData.videoGenNodeId }, nodes)
}

export function beatCardHasBeatPrompts(beatCardData) {
  if (!beatCardData) return false
  return rowHasBeatPrompts({
    beatsSplitAt: beatCardData.beatsSplitAt,
    keyframes: beatCardData.keyframes || [],
  })
}

export { rowDirectImageReady, rowDirectVideoReady }

export function getBeatCardNode(nodes, beatCardNodeId) {
  if (!beatCardNodeId) return null
  return (nodes || []).find((n) => n.id === beatCardNodeId && n.type === BEAT_CARD_NODE_TYPE) || null
}

export function getBeatCardForRow(nodes, scriptTableNodeId, rowId) {
  return (nodes || []).find(
    (n) =>
      n.type === BEAT_CARD_NODE_TYPE
      && n.data?.scriptTableRef?.nodeId === scriptTableNodeId
      && n.data?.scriptTableRef?.rowId === rowId
  ) || null
}

export function normalizeBeatCardData(data = {}) {
  const keyframes = asKeyframeArray(data.keyframes).map((kf, i) => ({
    ...kf,
    index: kf.index ?? i,
  }))
  return {
    ...data,
    keyframes,
    status: data.status || aggregateRowStatus(keyframes),
    error: data.error ?? keyframes.find((k) => k.error)?.error ?? null,
  }
}

export function syncBeatCardFromKeyframes(beatCardData) {
  const keyframes = asKeyframeArray(beatCardData?.keyframes)
  const lastWithResult = [...keyframes].reverse().find((k) => k.resultUrl)
  return {
    ...beatCardData,
    keyframes,
    status: aggregateRowStatus(keyframes),
    resultUrl: lastWithResult?.resultUrl ?? beatCardData?.resultUrl ?? null,
    error: keyframes.find((k) => k.error)?.error ?? beatCardData?.error ?? null,
  }
}

/** 打开画布时：行内 keyframes 迁入独立节拍卡片 */
export function migrateCanvasBeatCards(nodes, edges) {
  let nextNodes = [...(nodes || [])]
  let nextEdges = [...(edges || [])]
  let changed = false

  for (const tableNode of [...nextNodes]) {
    if (tableNode.type !== "script-table" || !Array.isArray(tableNode.data?.rows)) continue

    const rows = tableNode.data.rows
    const sorted = [...rows].sort((a, b) => (a.shotNumber ?? 0) - (b.shotNumber ?? 0))
    const nextRows = rows.map((row) => {
      if (row.beatCardNodeId) {
        const existing = getBeatCardNode(nextNodes, row.beatCardNodeId)
        if (existing) {
          return { ...row, keyframes: [] }
        }
      }

      const inlineKfs = row.keyframes || []
      const hasInlineBeats =
        inlineKfs.length > 0
        && (
          row.beatsSplitAt
          || inlineKfs.some((kf) => keyframeText(kf) || kf.resultUrl || kf.imageGenNodeId)
        )

      if (!hasInlineBeats) {
        return {
          ...row,
          beatCardNodeId: row.beatCardNodeId ?? null,
          keyframes: [],
          directImageGenNodeId: row.directImageGenNodeId ?? row.imageGenNodeId ?? null,
          directResultUrl: row.directResultUrl ?? (inlineKfs.length === 0 ? row.resultUrl : null) ?? null,
          directStatus: row.directStatus ?? (inlineKfs.length === 0 ? row.status : null) ?? "idle",
          directVideoGenNodeId: row.directVideoGenNodeId ?? null,
        }
      }

      let beatCardId = row.beatCardNodeId
      if (!beatCardId || !getBeatCardNode(nextNodes, beatCardId)) {
        beatCardId = makeId(BEAT_CARD_NODE_TYPE)
        const rowIndex = sorted.findIndex((r) => r.id === row.id)
        const beatCardNode = {
          id: beatCardId,
          type: BEAT_CARD_NODE_TYPE,
          position: computeBeatCardPosition(tableNode, Math.max(0, rowIndex)),
          data: normalizeBeatCardData({
            scriptTableRef: { nodeId: tableNode.id, rowId: row.id },
            shotNumber: row.shotNumber,
            keyframes: redistributeKeyframeTimes({ ...row, keyframes: inlineKfs }).keyframes,
            beatsSplitAt: row.beatsSplitAt,
            beatsSplitSource: row.beatsSplitSource,
            videoGenNodeId: row.videoGenNodeId ?? null,
            status: aggregateRowStatus(inlineKfs),
          }),
        }
        nextNodes.push(beatCardNode)
        nextEdges = addEdge(
          {
            id: `e-${tableNode.id}-${beatCardId}-migrate`,
            source: tableNode.id,
            target: beatCardId,
            sourceHandle: "src-right",
            targetHandle: "tgt",
            type: "ghost",
            animated: false,
          },
          nextEdges
        )
        changed = true
      }

      return {
        ...row,
        beatCardNodeId: beatCardId,
        keyframes: [],
        videoGenNodeId: null,
        directImageGenNodeId: row.directImageGenNodeId ?? null,
        directResultUrl: row.directResultUrl ?? null,
        directStatus: row.directStatus ?? "idle",
        directVideoGenNodeId: row.directVideoGenNodeId ?? null,
        resultUrl: row.directResultUrl ?? null,
        status: row.directStatus ?? "idle",
      }
    })

    if (JSON.stringify(nextRows) !== JSON.stringify(rows)) {
      changed = true
      nextNodes = nextNodes.map((n) =>
        n.id === tableNode.id
          ? { ...n, data: { ...n.data, rows: nextRows } }
          : n
      )
    }
  }

  return changed ? { nodes: nextNodes, edges: nextEdges } : { nodes, edges }
}

export function buildBeatCardCreatePayload(scriptTableNode, row, rowIndex) {
  const beatCardId = makeId(BEAT_CARD_NODE_TYPE)
  return {
    beatCardId,
    node: {
      id: beatCardId,
      type: BEAT_CARD_NODE_TYPE,
      position: computeBeatCardPosition(scriptTableNode, rowIndex),
      data: normalizeBeatCardData({
        scriptTableRef: { nodeId: scriptTableNode.id, rowId: row.id },
        shotNumber: row.shotNumber,
        keyframes: [],
        beatsSplitAt: null,
        beatsSplitSource: null,
        videoGenNodeId: null,
        status: "idle",
      }),
    },
  }
}

export function applyBeatsToBeatCard(beatCardData, beats) {
  const pseudoRow = { ...beatCardData, duration: beatCardData.duration || 8 }
  const next = applyBeatsToRow(pseudoRow, beats)
  return syncBeatCardFromKeyframes({
    ...beatCardData,
    keyframes: next.keyframes,
    beatsSplitAt: next.beatsSplitAt,
    beatsSplitSource: next.beatsSplitSource,
  })
}

export function rowHasGeneratableDirectContent(row) {
  return Boolean(shotPromptText(row))
}
