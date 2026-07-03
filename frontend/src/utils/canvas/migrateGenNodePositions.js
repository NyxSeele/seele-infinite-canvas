import {
  computeScriptTableGenX,
  computeScriptTableShotY,
  SCRIPT_TABLE_TO_IMAGE_GAP,
} from "./nodeHelpers"

const LEGACY_SCRIPT_TABLE_WIDTH = 1360
const TOLERANCE = 24
const GEN_NODE_TYPES = new Set(["image-gen", "video-gen", "script-beat-card"])

/**
 * 启发式迁移：仅当 X 符合旧公式 table.x + 1360 + gap 时才重定位到新公式。
 */
export function migrateGenNodePositions(nodes) {
  if (!Array.isArray(nodes) || nodes.length === 0) {
    return { nodes, migratedCount: 0 }
  }

  const tables = nodes.filter((n) => n.type === "script-table")
  if (tables.length === 0) {
    return { nodes, migratedCount: 0 }
  }

  let migratedCount = 0
  const next = nodes.map((node) => {
    if (!GEN_NODE_TYPES.has(node.type)) return node

    for (const table of tables) {
      const oldX = (table.position?.x || 0) + LEGACY_SCRIPT_TABLE_WIDTH + SCRIPT_TABLE_TO_IMAGE_GAP
      const newX = computeScriptTableGenX(table)
      if (Math.abs((node.position?.x || 0) - oldX) > TOLERANCE) continue

      const tableY = table.position?.y || 0
      let rowMatched = false
      for (let row = 0; row < 80; row += 1) {
        const expectedY = computeScriptTableShotY(table, row)
        if (Math.abs((node.position?.y || 0) - expectedY) <= TOLERANCE) {
          rowMatched = true
          break
        }
      }
      if (!rowMatched && node.type !== "script-beat-card") continue
      if (!rowMatched && node.type === "script-beat-card") {
        const yDiff = Math.abs((node.position?.y || 0) - (tableY + 300))
        if (yDiff > 400) continue
      }

      if (Math.abs((node.position?.x || 0) - newX) <= 1) return node
      migratedCount += 1
      return {
        ...node,
        position: { ...node.position, x: newX },
      }
    }
    return node
  })

  return { nodes: next, migratedCount }
}
