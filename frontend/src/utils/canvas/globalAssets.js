/** 全局资产库 → @ 提及 / 设定库条目 */

import { ensureMediaUrl } from "../mediaTicket"

export const ASSET_KIND_LABELS = {
  image: "图片",
  video: "视频",
  character: "人物",
  scene: "场景",
  /** @deprecated 旧数据兼容 */
  prop: "图片",
  other: "图片",
}

/** 素材库：图片 / 视频；主体库：人物 / 场景 */
export function normalizeAssetKind(kind) {
  if (kind === "video") return "video"
  if (kind === "character" || kind === "scene") return kind
  return "image"
}

export function isMaterialKind(kind) {
  const k = normalizeAssetKind(kind)
  return k === "image" || k === "video"
}

export function isSubjectKind(kind) {
  const k = normalizeAssetKind(kind)
  return k === "character" || k === "scene"
}

export function assetKindToCastType(kind) {
  return normalizeAssetKind(kind) === "scene" ? "scene" : "character"
}

export function normalizeUserAsset(raw) {
  if (!raw?.id || !raw?.name || !raw?.image_url) return null
  const kind = normalizeAssetKind(raw.kind)
  return {
    id: raw.id,
    name: String(raw.name).trim(),
    kind,
    imageUrl: raw.image_url,
    note: raw.note || "",
    sourceCanvasId: raw.source_canvas_id || null,
    sourceCanvasName: raw.source_canvas_name || null,
    sourceNodeId: raw.source_node_id || null,
    teamId: raw.team_id || null,
    teamName: raw.team_name || null,
    isTeam: !!raw.team_id,
    ownerId: raw.owner_id ?? null,
    ownerName: raw.owner_name || null,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  }
}

/** 供 MentionTextarea / 视频 @ 列表使用 */
export function assetToMentionItem(asset) {
  if (!asset) return null
  const kind = normalizeAssetKind(asset.kind)
  const mediaUrl = asset.imageUrl ? ensureMediaUrl(asset.imageUrl) : ""
  return {
    id: asset.id,
    nodeId: asset.id,
    type: kind === "video" ? "video" : "asset",
    name: asset.name,
    imageUrl: mediaUrl,
    thumbUrl: mediaUrl,
    image_index: 0,
    kind,
    source: "global",
    subtitle: ASSET_KIND_LABELS[kind] || "资产",
  }
}

/** 供分镜表 CastMentionPicker（与 castLibrary 条目形状兼容） */
export function assetToCastPickerItem(asset) {
  if (!asset) return null
  const kind = normalizeAssetKind(asset.kind)
  return {
    id: asset.id,
    name: asset.name,
    type: assetKindToCastType(kind),
    imageUrl: asset.imageUrl,
    source: "global",
    kind,
  }
}

export function mergeCastAndGlobalAssets(castLibrary = [], globalAssets = []) {
  const localNames = new Set(
    (castLibrary || []).map((c) => c.name?.trim().toLowerCase()).filter(Boolean)
  )
  const globals = (globalAssets || [])
    .filter((a) => isSubjectKind(a.kind))
    .map(assetToCastPickerItem)
    .filter(Boolean)
    .filter((g) => !localNames.has(g.name.toLowerCase()))
  return [...(castLibrary || []), ...globals]
}
