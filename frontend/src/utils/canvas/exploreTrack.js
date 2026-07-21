import { buildActiveChain } from "./agentPipeline"

/** 主链 script-table 及其交付轨关联节点 id 集合 */
export function getDeliveryNodeIds(nodes, edges = []) {
  const chain = buildActiveChain(nodes, edges)
  const scriptId = chain?.script?.id
  if (!scriptId) return new Set()

  const ids = new Set([scriptId])
  const script = chain.script
  const rows = script?.data?.rows || []

  for (const row of rows) {
    if (row.directImageGenNodeId) ids.add(row.directImageGenNodeId)
    if (row.directVideoGenNodeId) ids.add(row.directVideoGenNodeId)
    if (row.videoGenNodeId) ids.add(row.videoGenNodeId)
    if (row.beatCardNodeId) ids.add(row.beatCardNodeId)
    for (const kf of row.keyframes || []) {
      if (kf?.imageGenNodeId) ids.add(kf.imageGenNodeId)
    }
  }

  for (const e of edges || []) {
    if (e.source === scriptId) ids.add(e.target)
    if (e.target === scriptId) ids.add(e.source)
  }

  for (const n of nodes || []) {
    if (n.data?.scriptTableRef?.nodeId === scriptId) ids.add(n.id)
  }

  return ids
}

/** image-gen / video-gen 不在主链交付集合上则为试稿节点（未写入分镜交付轨） */
export function isExploreNode(node, nodes, edges = []) {
  if (!node) return false
  const type = node.type
  if (type !== "image-gen" && type !== "video-gen") return false
  const delivery = getDeliveryNodeIds(nodes, edges)
  return !delivery.has(node.id)
}

/** 试稿 image-gen 节点可取用的结果图 URL */
export function getExploreImageUrl(node) {
  const d = node?.data || {}
  if (d.imageUrl) return d.imageUrl
  const results = d.results
  if (Array.isArray(results) && results.length > 0) {
    const first = results[0]
    if (typeof first === "string") return first
    if (first?.imageUrl) return first.imageUrl
    if (first?.url) return first.url
  }
  if (d.uploadedImage) return d.uploadedImage
  return null
}
