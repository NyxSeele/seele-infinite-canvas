/** 分镜表节点查找与画风迁移工具 */

import { migrateContentStyleToPreset, normalizeQualityPresetId } from "./scriptQualityPresets"

export function findScriptTableNode(nodes) {
  if (!Array.isArray(nodes)) return null
  return nodes.find((n) => n.type === "script-table") || null
}

/** 行级有效画风：行 preset 优先，否则表默认 */
export function getEffectiveQualityPresetId(row, tableData = {}) {
  const rowId = (row?.qualityPresetId || "").trim()
  if (rowId && rowId !== "") return rowId
  const tableId = migrateTableDefaultQualityPresetId(tableData)
  return tableId || "auto"
}

/** 视频卡画风：节点自身 preset 优先，否则分镜表默认 */
export function resolveVideoQualityPresetId(videoData = {}, tableData = null) {
  const own = (videoData?.qualityPresetId || "").trim()
  if (own) return normalizeQualityPresetId(own)
  if (tableData) return migrateTableDefaultQualityPresetId(tableData)
  return "auto"
}

/** 图像卡画风：与视频卡相同（卡片 qualityPresetId > 分镜表 defaultQualityPresetId） */
export const resolveImageQualityPresetId = resolveVideoQualityPresetId

/** 表级默认画风（含旧 contentStyle 迁移） */
export function migrateTableDefaultQualityPresetId(tableData = {}) {
  const defaultId = tableData?.defaultQualityPresetId
  return migrateContentStyleToPreset(tableData?.contentStyle, defaultId)
}
