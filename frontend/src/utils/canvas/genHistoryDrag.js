export const GEN_HISTORY_DRAG_MIME = "application/x-aistudio-gen-history"
export const ASSET_DRAG_MIME = "application/x-aistudio-asset"

export function packGenHistoryDrag(item) {
  return JSON.stringify({
    type: item.type || "image-gen",
    resultUrl: item.resultUrl || "",
    prompt: item.prompt || "",
  })
}

export function packAssetDrag(asset) {
  return JSON.stringify({
    imageUrl: asset.imageUrl || "",
    name: asset.name || "",
    kind: asset.kind || "other",
  })
}

export function parseGenHistoryDrag(raw) {
  if (!raw) return null
  try {
    const data = JSON.parse(raw)
    if (!data?.resultUrl) return null
    return data
  } catch {
    return null
  }
}

export function parseAssetDrag(raw) {
  if (!raw) return null
  try {
    const data = JSON.parse(raw)
    if (!data?.imageUrl) return null
    return data
  } catch {
    return null
  }
}

export function hasFlyoutDrag(e) {
  const types = [...(e.dataTransfer?.types || [])]
  return types.includes(GEN_HISTORY_DRAG_MIME) || types.includes(ASSET_DRAG_MIME)
}

export function parseFlyoutDrop(e) {
  const history = parseGenHistoryDrag(
    e.dataTransfer.getData(GEN_HISTORY_DRAG_MIME)
  )
  if (history) return { source: "history", ...history }
  const asset = parseAssetDrag(e.dataTransfer.getData(ASSET_DRAG_MIME))
  if (asset) return { source: "asset", ...asset }
  return null
}
