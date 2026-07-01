const NODE_SIZES = {
  "image-gen": { width: 300, height: 320 },
  "video-gen": { width: 440, height: 300 },
  "text-note": { width: 340, height: 240 },
  "text-response": { width: 500, height: 440 },
  "script-table": { width: 1120, height: 620 },
  "script-beat-card": { width: 920, height: 480 },
  outline: { width: 560, height: 460 },
  "shot-script": { width: 860, height: 540 },
}

const GAP_X = 64
const GAP_Y = 80
const MAX_ROW_WIDTH = 2720

function getNodeSize(node) {
  const fallback = NODE_SIZES[node.type] || { width: 320, height: 360 }
  const width = node.width ?? node.measured?.width ?? fallback.width
  const height = node.height ?? node.measured?.height ?? fallback.height
  return { width, height }
}

/** 视觉顺序：先上后下，同行从左到右 */
function compareVisual(a, b) {
  const dy = a.position.y - b.position.y
  if (Math.abs(dy) > 90) return dy
  return a.position.x - b.position.x
}

/**
 * 按连线拓扑 + 当前视觉位置排序（不用类型优先级，避免大纲跑到图片前）
 * Kahn 拓扑：同层节点按画布上的左右位置排列
 */
export function sortNodesByWorkflow(nodes, edges = []) {
  if (!nodes.length) return []

  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  const adj = new Map()
  const indegree = new Map(nodes.map((n) => [n.id, 0]))

  for (const e of edges || []) {
    if (!nodeById.has(e.source) || !nodeById.has(e.target)) continue
    if (!adj.has(e.source)) adj.set(e.source, [])
    adj.get(e.source).push(e.target)
    indegree.set(e.target, (indegree.get(e.target) || 0) + 1)
  }

  const queue = nodes
    .filter((n) => (indegree.get(n.id) || 0) === 0)
    .sort(compareVisual)

  const ordered = []
  const visited = new Set()

  while (queue.length > 0) {
    queue.sort(compareVisual)
    const node = queue.shift()
    if (!node || visited.has(node.id)) continue
    visited.add(node.id)
    ordered.push(node)

    for (const childId of adj.get(node.id) || []) {
      indegree.set(childId, (indegree.get(childId) || 0) - 1)
      if (indegree.get(childId) === 0) {
        const child = nodeById.get(childId)
        if (child) queue.push(child)
      }
    }
  }

  nodes
    .filter((n) => !visited.has(n.id))
    .sort(compareVisual)
    .forEach((n) => ordered.push(n))

  return ordered
}

function layoutInFlow(ordered) {
  let curX = 0
  let curY = 0
  let rowHeight = 0

  return ordered.map((node) => {
    const { width, height } = getNodeSize(node)
    if (curX > 0 && curX + width > MAX_ROW_WIDTH) {
      curX = 0
      curY += rowHeight + GAP_Y
      rowHeight = 0
    }
    const position = { x: curX, y: curY }
    curX += width + GAP_X
    rowHeight = Math.max(rowHeight, height)
    return { ...node, position }
  })
}

export function organizeCanvasNodes(nodes, edges = []) {
  if (!nodes?.length) return nodes
  const ordered = sortNodesByWorkflow(nodes, edges)
  return layoutInFlow(ordered)
}
