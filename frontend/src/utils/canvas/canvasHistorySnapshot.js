import { sanitizeNodeDataForPersist } from "../../components/canvas/videoReferenceHelpers"
import { pickOutlineNodeFields } from "./nodeCompose"
import {
  normalizeCanvasNode,
  normalizeOutlineNode,
  normalizeTextResponseNode,
} from "./nodeNormalize"

const STRIP_DATA_KEYS = new Set([
  "onUpdate",
  "onDelete",
  "onDisconnectIncoming",
  "onApplyVideoReference",
  "onStopGeneration",
  "composeNodeData",
  "composeOutlineNodeData",
  "connectOutlineFromResponse",
  "onGenerateScreenplay",
  "onGenerateShotScript",
  "onGenerateScriptTable",
  "onImportScriptTable",
  "onMigrateShotScript",
  "onRetry",
])

function stripRuntimeData(data) {
  if (!data || typeof data !== "object") return {}
  const out = { ...data }
  STRIP_DATA_KEYS.forEach((k) => {
    delete out[k]
  })
  return sanitizeNodeDataForPersist(out)
}

/** 可 JSON 化的画布快照（不含函数引用） */
export function serializeCanvasSnapshot(nodes, edges) {
  const cleanNodes = (nodes || []).map((n) => {
    const restData = stripRuntimeData(n.data)
    return normalizeTextResponseNode({
      ...n,
      data: restData,
      selected: false,
      dragging: false,
    })
  })
  return {
    nodes: cleanNodes,
    edges: (edges || []).map((e) => ({ ...e, selected: false })),
  }
}

export function snapshotKey(snapshot) {
  return JSON.stringify(snapshot)
}

/** 从快照恢复节点/边，并重新注入运行时 handlers */
export function restoreCanvasSnapshot(snapshot, ctx) {
  const {
    setNodes,
    setEdges,
    buildData,
    buildOutlineData,
    textRetryRef,
    zIndexCounterRef,
  } = ctx
  const savedNodes = snapshot?.nodes || []
  const savedEdges = snapshot?.edges || []

  const restoredNodes = savedNodes.map((n) => {
    const base = normalizeCanvasNode(n)
    const cleanData = stripRuntimeData(base.data)
    if (base.type === "outline") {
      const outlineFields = pickOutlineNodeFields(cleanData)
      return {
        ...normalizeOutlineNode(base),
        data: {
          ...outlineFields,
          ...buildOutlineData(outlineFields),
        },
      }
    }
    return {
      ...base,
      data: {
        ...cleanData,
        ...buildData(cleanData),
        ...(base.type === "text-response"
          ? { onRetry: (id) => textRetryRef?.current?.(id) }
          : {}),
      },
    }
  })

  const maxZ = restoredNodes.reduce(
    (max, n) => Math.max(max, n.zIndex ?? n.data?.zIndex ?? n.style?.zIndex ?? 0),
    0
  )
  if (zIndexCounterRef) zIndexCounterRef.current = maxZ
  setNodes(restoredNodes)
  setEdges(savedEdges)
}
