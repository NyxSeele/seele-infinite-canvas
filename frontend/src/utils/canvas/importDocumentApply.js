/** 导入 V2：大小镜头归并辅助（预览与分组编辑） */

export function identityGroups(microRows) {
  return (microRows || []).map((_, i) => [i])
}

export function flattenGroups(groups) {
  return (groups || []).flat()
}

export function splitGroupAt(groups, index) {
  if (!groups?.length || index <= 0) return groups || []
  const next = []
  for (const g of groups) {
    if (!g.includes(index)) {
      next.push(g)
      continue
    }
    if (g[0] === index) return groups
    const pos = g.indexOf(index)
    next.push(g.slice(0, pos))
    next.push(g.slice(pos))
  }
  return next.filter((g) => g.length > 0)
}

export function mergeGroupWithPrevious(groups, groupIndex) {
  if (!groups?.length || groupIndex <= 0 || groupIndex >= groups.length) return groups
  const next = [...groups]
  const merged = [...next[groupIndex - 1], ...next[groupIndex]]
  next.splice(groupIndex - 1, 2, merged)
  return next
}

export function previewMacroStats(microRows, groups) {
  const stats = {
    macroCount: groups?.length || 0,
    microCount: microRows?.length || 0,
    macros: [],
  }
  for (const g of groups || []) {
    const micros = g.map((i) => microRows[i]).filter(Boolean)
    const dur = micros.reduce((s, m) => s + (Number(m.duration) || 8), 0)
    stats.macros.push({
      duration: Math.round(dur * 10) / 10,
      beatCount: micros.length,
    })
  }
  return stats
}

export function findNodeIdBySheetName(nodes, sheetName) {
  for (const node of nodes || []) {
    const meta = node?.data?.importMeta
    if (meta?.sheetName === sheetName) return node.id
  }
  return null
}

export function mergeCanvasFromImportResponse(canvasData, setNodes, setEdges) {
  if (!canvasData || !setNodes || !setEdges) return
  setNodes(canvasData.nodes || [])
  setEdges(canvasData.edges || [])
}
