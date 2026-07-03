import { useCallback, useMemo } from "react"
import { useStore } from "reactflow"
import { useAssetStore } from "../../stores/assetStore"
import { assetToMentionItem } from "../../utils/canvas/globalAssets"
import { stripMediaTicket } from "../../utils/mediaTicket"
import { normalizePersistentImageUrl } from "./videoReferenceHelpers"
import {
  appendReferenceImage,
  getImageNodeImages,
} from "./videoReferenceHelpers"

/** 从 contenteditable 根节点序列化为纯文本 + mentions */
export function serializeMentionEditor(root) {
  if (!root) return { text: "", mentions: [] }
  const mentions = []
  const seen = new Set()
  let text = ""

  const walk = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      text += node.textContent
      return
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return
    if (node.classList?.contains("mention-token")) {
      const name = node.dataset.name || node.textContent.replace(/^@/, "")
      text += `@${name}`
      const id = node.dataset.id
      const imageIndex =
        node.dataset.imageIndex != null && node.dataset.imageIndex !== ""
          ? Number(node.dataset.imageIndex)
          : null
      const dedupeKey = `${id}:${imageIndex ?? 0}`
      if (id && !seen.has(dedupeKey)) {
        seen.add(dedupeKey)
        const entry = {
          id,
          type: node.dataset.type || "image",
          name,
        }
        if (imageIndex != null) {
          entry.image_index = imageIndex
        }
        mentions.push(entry)
      }
      return
    }
    node.childNodes.forEach(walk)
  }

  root.childNodes.forEach(walk)
  return { text, mentions }
}

/** 根据纯文本 + mentions 构建编辑器 DOM（按名称最长优先匹配，支持中文紧跟） */
export function renderMentionContent(root, text, mentions = []) {
  if (!root) return
  root.innerHTML = ""
  if (!text) return

  const list = (mentions || [])
    .filter((m) => m?.name)
    .sort((a, b) => String(b.name).length - String(a.name).length)

  let i = 0
  while (i < text.length) {
    const at = text.indexOf("@", i)
    if (at === -1) {
      root.appendChild(document.createTextNode(text.slice(i)))
      break
    }
    if (at > i) {
      root.appendChild(document.createTextNode(text.slice(i, at)))
    }

    let matched = null
    for (const m of list) {
      const token = `@${m.name}`
      if (
        text.slice(at, at + token.length).toLowerCase()
        === token.toLowerCase()
      ) {
        matched = m
        break
      }
    }

    if (matched) {
      root.appendChild(createMentionSpan(matched))
      i = at + `@${matched.name}`.length
      continue
    }

    const unknown = text.slice(at).match(/^@[^\s@]+/)
    if (unknown) {
      root.appendChild(document.createTextNode(unknown[0]))
      i = at + unknown[0].length
    } else {
      root.appendChild(document.createTextNode("@"))
      i = at + 1
    }
  }
}

export function createMentionSpan(meta) {
  const span = document.createElement("span")
  span.className = "mention-token"
  span.contentEditable = "false"
  span.dataset.id = meta.id
  span.dataset.type = meta.type || "image"
  span.dataset.name = meta.name
  if (meta.image_index != null) {
    span.dataset.imageIndex = String(meta.image_index)
  }
  if (meta.imageUrl) {
    span.dataset.imageUrl = meta.imageUrl
  }
  span.textContent = `@${meta.name}`
  return span
}

/** 光标前 @ 查询（支持输入框中间触发） */
export function getMentionQueryAtSelection(root) {
  const sel = window.getSelection()
  if (!sel?.rangeCount || !root) return null
  const range = sel.getRangeAt(0)
  if (!root.contains(range.startContainer)) return null

  const probe = range.cloneRange()
  probe.selectNodeContents(root)
  probe.setEnd(range.endContainer, range.endOffset)
  const before = probe.toString()
  const match = before.match(/@([^\s@]*)$/)
  if (!match) return null

  let anchorRect = null
  try {
    const caretRange = range.cloneRange()
    caretRange.collapse(true)
    const rects = caretRange.getClientRects()
    const rect = rects.length > 0 ? rects[0] : caretRange.getBoundingClientRect()
    if (rect && (rect.width || rect.height || rect.top || rect.left)) {
      anchorRect = {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
      }
    }
  } catch {
    /* ignore */
  }
  if (!anchorRect && root) {
    const er = root.getBoundingClientRect()
    anchorRect = {
      left: er.left,
      top: er.top,
      right: er.right,
      bottom: er.bottom,
      width: er.width,
      height: er.height,
    }
  }

  return {
    query: match[1],
    matchLength: match[0].length,
    anchorRect,
  }
}

/** 删除光标前 @ 查询段并插入 mention token */
export function insertMentionAtCaret(root, candidate) {
  const sel = window.getSelection()
  if (!sel?.rangeCount || !root) return

  const range = sel.getRangeAt(0)
  if (!root.contains(range.startContainer)) return

  const probe = range.cloneRange()
  probe.selectNodeContents(root)
  probe.setEnd(range.endContainer, range.endOffset)
  const before = probe.toString()
  const match = before.match(/@([^\s@]*)$/)
  if (!match) return

  const deleteRange = range.cloneRange()
  deleteRange.setStart(range.endContainer, range.endOffset - match[0].length)
  deleteRange.deleteContents()

  const span = createMentionSpan({
    id: candidate.id || candidate.nodeId,
    type: candidate.type,
    name: candidate.name,
    image_index: candidate.image_index ?? candidate.imageIndex,
    imageUrl: candidate.imageUrl || candidate.thumbUrl || "",
  })
  deleteRange.insertNode(span)
  const space = document.createTextNode("\u00a0")
  deleteRange.setStartAfter(span)
  deleteRange.collapse(true)
  deleteRange.insertNode(space)
  deleteRange.setStartAfter(space)
  deleteRange.collapse(true)
  sel.removeAllRanges()
  sel.addRange(deleteRange)
}

/** 将 @ 引用解析为画布参考图项（仅 image-gen） */
export function resolveMentionToRefItem(mention, getNode) {
  if (!mention?.id) return null
  const t = String(mention.type || "image").toLowerCase()
  if (t === "asset") {
    const asset = useAssetStore.getState().getAsset(mention.id)
    if (!asset?.imageUrl) return null
    return {
      nodeId: asset.id,
      imageIndex: 0,
      imageUrl: asset.imageUrl,
      label: asset.name,
      fromMention: true,
    }
  }
  if (typeof getNode !== "function") return null
  if (t !== "image" && t !== "image-gen") return null

  const node = getNode(mention.id)
  if (!node || node.type !== "image-gen") return null

  const images = getImageNodeImages(node)
  if (!images.length) return null

  const idx = mention.image_index ?? 0
  return (
    images.find((r) => r.imageIndex === idx)
    || images[idx]
    || images[0]
  )
}

/** 从 mentions 列表中移除指定引用，并同步清理 prompt 文本中的 @token */
export function removeMentionFromPrompt(text, mention) {
  if (!mention?.name) {
    return { text: text || "", mentions: [] }
  }
  const token = `@${mention.name}`
  const re = new RegExp(`${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\s|$)`, "g")
  const nextText = (text || "").replace(re, " ").replace(/\s+/g, " ").trim()
  return { text: nextText, mentionKey: `${mention.id}:${mention.image_index ?? 0}` }
}

export function filterMentionsAfterRefRemoved(mentions, refItem) {
  if (!refItem?.nodeId) return mentions || []
  const idx = refItem.imageIndex ?? 0
  return (mentions || []).filter(
    (m) => !(m.id === refItem.nodeId && (m.image_index ?? 0) === idx)
  )
}

/** 把 mentions 中的图片引用合并进参考图列表（去重、上限） */
export function mergeMentionRefsIntoReferenceImages(
  referenceImages,
  mentions,
  getNode,
  max = 5
) {
  return syncMentionRefsIntoReferenceImages(referenceImages, mentions, getNode, max)
}

/** 保留手动添加的参考图，并按当前 mentions 重建 @ 来源项 */
export function syncMentionRefsIntoReferenceImages(
  referenceImages,
  mentions,
  getNode,
  max = 5
) {
  const manual = (Array.isArray(referenceImages) ? referenceImages : []).filter(
    (r) => !r?.fromMention
  )
  let list = [...manual]
  for (const m of mentions || []) {
    const item = resolveMentionToRefItem(m, getNode)
    if (item) {
      list = appendReferenceImage(list, { ...item, fromMention: true }, max)
    }
  }
  return list
}

/** 把 mentions 中的图片引用合并进全能参考列表（去重、上限） */
export function mergeMentionRefsIntoFreeRefs(freeRefs, mentions, getNode, max = 5) {
  return syncFreeRefsWithMentions(freeRefs, mentions, getNode, max)
}

/** 保留手动添加的全能参考，并按当前 mentions 重建 @ 来源缩略图 */
export function syncFreeRefsWithMentions(freeRefs, mentions, getNode, max = 5) {
  const manual = (Array.isArray(freeRefs) ? freeRefs : []).filter(
    (r) => !r?.fromMention
  )
  let list = [...manual]
  for (const m of mentions || []) {
    const item = resolveMentionToRefItem(m, getNode)
    if (item) {
      list = appendReferenceImage(list, { ...item, fromMention: true }, max)
    }
  }
  return list
}

function collectCanvasMentionItems(nodeInternals, excludeNodeId) {
  const items = []
  nodeInternals.forEach((node) => {
          if (excludeNodeId && node.id === excludeNodeId) return
          const baseLabel =
            node.data?.label && String(node.data.label).trim()
              ? String(node.data.label).trim()
              : null

          if (node.type === "image-gen") {
            getImageNodeImages(node).forEach((ref) => {
              items.push({
                id: node.id,
                nodeId: node.id,
                type: "image",
                name: ref.label || baseLabel || "Image",
                imageUrl: ref.imageUrl,
                image_index: ref.imageIndex,
                thumbUrl: ref.imageUrl,
              })
            })
            return
          }

          if (node.type === "video-gen") {
            const videoUrl = node.data?.videoUrl
            if (!videoUrl) return
            items.push({
              id: node.id,
              nodeId: node.id,
              type: "video",
              name: baseLabel || "Video",
              thumbUrl: videoUrl,
            })
            return
          }

          if (node.type === "text-note") {
            const preview =
              node.data?.prompt ?? node.data?.content ?? ""
            items.push({
              id: node.id,
              nodeId: node.id,
              type: "text",
              name: baseLabel || "Text",
              preview: String(preview).slice(0, 80),
            })
            return
          }

          if (node.type === "text-response") {
            const preview = node.data?.content ?? ""
            if (!String(preview).trim()) return
            items.push({
              id: node.id,
              nodeId: node.id,
              type: "text",
              name: baseLabel || "Text",
              preview: String(preview).slice(0, 80),
            })
          }
        })
  return items
}

function mentionMediaKey(item) {
  const raw = item?.imageUrl || item?.thumbUrl || ""
  if (!raw) return null
  return normalizePersistentImageUrl(stripMediaTicket(raw))
}

/** 资产库优先；与资产库同图 / 同来源节点的画布项不重复出现 */
export function mergeMentionCandidates(globalItems, canvasItems, assets = []) {
  const assetUrls = new Set()
  const assetSourceNodeIds = new Set()

  for (const a of assets) {
    const url = mentionMediaKey({ imageUrl: a.imageUrl })
    if (url) assetUrls.add(url)
    if (a.sourceNodeId) assetSourceNodeIds.add(a.sourceNodeId)
  }

  const seenUrls = new Set(assetUrls)
  const seenSlots = new Set()
  const out = []

  for (const g of globalItems) {
    const url = mentionMediaKey(g)
    const slot = `${g.type}:${g.id}:${g.image_index ?? 0}`
    if (seenSlots.has(slot)) continue
    seenSlots.add(slot)
    if (url) seenUrls.add(url)
    out.push(g)
  }

  for (const c of canvasItems) {
    if (c.type === "text") {
      const slot = `text:${c.id}`
      if (seenSlots.has(slot)) continue
      seenSlots.add(slot)
      out.push(c)
      continue
    }
    if (c.nodeId && assetSourceNodeIds.has(c.nodeId)) continue
    const url = mentionMediaKey(c)
    if (url && seenUrls.has(url)) continue
    const slot = `${c.type}:${c.id}:${c.image_index ?? 0}`
    if (seenSlots.has(slot)) continue
    seenSlots.add(slot)
    if (url) seenUrls.add(url)
    out.push(c)
  }

  return out
}

export function useMentionableItems(excludeNodeId = null) {
  const assets = useAssetStore((s) => s.assets)
  const canvasItems = useStore(
    useCallback(
      (s) => collectCanvasMentionItems(s.nodeInternals, excludeNodeId),
      [excludeNodeId]
    )
  )
  return useMemo(() => {
    const globalItems = (assets || [])
      .map(assetToMentionItem)
      .filter(Boolean)
    return mergeMentionCandidates(globalItems, canvasItems, assets)
  }, [assets, canvasItems])
}
