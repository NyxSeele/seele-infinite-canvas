import { addEdge } from "reactflow"
import { buildActiveChain } from "./agentPipeline"

/** 主链 script-table 节点（与 Pipeline 侧栏同源） */
export function getActiveScriptTable(nodes, edges = []) {
  const chain = buildActiveChain(nodes, edges)
  return chain?.script || null
}

/** 解析生成节点在主链分镜表中的镜号下标（0-based），解析不到返回 null */
export function resolveStoryboardShotIndex({
  genNodeId,
  scriptTableRef,
  scriptTable,
}) {
  const rows = scriptTable?.data?.rows || []
  if (scriptTableRef?.rowId) {
    const idx = rows.findIndex((r) => r.id === scriptTableRef.rowId)
    if (idx >= 0) return idx
  }
  if (genNodeId) {
    const idx = rows.findIndex(
      (r) =>
        r.directImageGenNodeId === genNodeId
        || r.directVideoGenNodeId === genNodeId
        || r.videoGenNodeId === genNodeId
    )
    if (idx >= 0) return idx
  }
  return null
}

/**
 * 将试稿 image-gen 采纳到分镜直连图，并绑定交付轨（URL + directImageGenNodeId + scriptTableRef + edge）
 */
export function promoteExploreToStoryboard({
  nodes,
  setNodes,
  setEdges,
  scriptTableId,
  rowIndex,
  imageGenNodeId,
  imageUrl,
}) {
  const scriptNode = nodes.find((n) => n.id === scriptTableId)
  const rows = scriptNode?.data?.rows || []
  const row = rows[rowIndex]
  if (!row || !imageUrl || !imageGenNodeId || !scriptTableId) return false

  const rowId = row.id

  setNodes((nds) =>
    nds.map((n) => {
      if (n.id === scriptTableId) {
        const nextRows = (n.data?.rows || []).map((r, i) =>
          i !== rowIndex
            ? r
            : {
                ...r,
                directResultUrl: imageUrl,
                resultUrl: imageUrl,
                directStatus: "completed",
                status: "completed",
                directImageGenNodeId: imageGenNodeId,
              }
        )
        return { ...n, data: { ...n.data, rows: nextRows } }
      }
      if (n.id === imageGenNodeId) {
        return {
          ...n,
          data: {
            ...n.data,
            scriptTableRef: {
              nodeId: scriptTableId,
              rowId,
              lane: "direct",
            },
          },
        }
      }
      return n
    })
  )

  if (setEdges) {
    setEdges((es) => {
      const exists = es.some(
        (e) =>
          (e.source === scriptTableId && e.target === imageGenNodeId)
          || (e.source === imageGenNodeId && e.target === scriptTableId)
      )
      if (exists) return es
      return addEdge(
        {
          id: `e-${scriptTableId}-${imageGenNodeId}-${Date.now()}`,
          source: scriptTableId,
          target: imageGenNodeId,
          sourceHandle: "src-right",
          targetHandle: "tgt",
          type: "ghost",
          animated: false,
        },
        es
      )
    })
  }

  return true
}
