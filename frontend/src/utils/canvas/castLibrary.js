import { stripMediaTicket } from "../mediaTicket"
import { allPromptMentionsForRow, scriptRowText } from "./scriptTableKeyframes"
import { assetKindToCastType } from "./globalAssets"

function normImageUrl(url) {
  if (!url) return ""
  return stripMediaTicket(url) || String(url)
}

export function makeCastRefId() {
  return `cast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

/** Velora 自有 identity 约定：{slugName}_{variant} */
export function slugIdentityId(name, variant = "default") {
  const base = String(name || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w\u4e00-\u9fff-]/g, "")
  return `${base || "char"}_${variant}`
}

/** 参考图优先级：threeView > face > costume > imageUrl */
export function pickCastReferenceUrls(entry, { max = 3 } = {}) {
  if (!entry) return []
  const slots = ["threeViewUrl", "faceUrl", "costumeUrl", "imageUrl"]
  const seen = new Set()
  const out = []
  for (const key of slots) {
    const url = normImageUrl(entry[key])
    if (url && !seen.has(url)) {
      seen.add(url)
      out.push(url)
    }
  }
  return out.slice(0, max)
}

export function pickCastFaceUrl(entry) {
  const face = normImageUrl(entry?.faceUrl)
  if (face) return face
  return normImageUrl(entry?.imageUrl) || null
}

export function castEntryHasReferenceImage(entry) {
  return pickCastReferenceUrls(entry, { max: 1 }).length > 0
}

export function normalizeCastLibraryEntry(item) {
  if (!item || !String(item.name || "").trim()) return null
  const name = String(item.name).trim()
  const faceUrl = normImageUrl(item.faceUrl) || normImageUrl(item.imageUrl) || null
  const threeViewUrl = normImageUrl(item.threeViewUrl) || null
  const costumeUrl = normImageUrl(item.costumeUrl) || null
  const imageUrl = faceUrl || threeViewUrl || costumeUrl || normImageUrl(item.imageUrl) || null
  const identityId =
    String(item.identityId || item.identity_id || "").trim() || slugIdentityId(name)
  return {
    id: item.id || makeCastRefId(),
    name,
    type: item.type === "scene" ? "scene" : "character",
    identityId,
    faceUrl,
    threeViewUrl,
    costumeUrl,
    imageUrl,
    description: item.description ? String(item.description).trim() : "",
    pendingImage: !castEntryHasReferenceImage({ faceUrl, threeViewUrl, costumeUrl, imageUrl }),
    lastUsedAt: item.lastUsedAt != null ? Number(item.lastUsedAt) : null,
    useCount: Number(item.useCount) || 0,
    ...(item.globalAssetId ? { globalAssetId: item.globalAssetId } : {}),
    ...(item.assetId ? { assetId: item.assetId } : {}),
  }
}

export function normalizeCastLibrary(list, { requireImage = true } = {}) {
  const entries = (Array.isArray(list) ? list : [])
    .map(normalizeCastLibraryEntry)
    .filter(Boolean)
  return requireImage ? entries.filter((e) => castEntryHasReferenceImage(e)) : entries
}

/**
 * 从提示词中匹配设定库名称（支持 @名称、【名称】、直接包含名称）
 */
export function matchCastRefsInPrompt(prompt, castLibrary = []) {
  const text = String(prompt || "")
  if (!text || !castLibrary.length) return []
  const matched = []
  const seen = new Set()
  for (const item of castLibrary) {
    const name = item.name?.trim()
    if (!name || seen.has(name)) continue
    const patterns = [
      new RegExp(`@${escapeRegExp(name)}`, "i"),
      new RegExp(`【${escapeRegExp(name)}】`),
      new RegExp(`\\[${escapeRegExp(name)}\\]`),
    ]
    if (patterns.some((re) => re.test(text)) || text.includes(name)) {
      matched.push(item)
      seen.add(name)
    }
  }
  return matched
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

function globalAssetsAsCastEntries(globalAssets = []) {
  const names = new Set()
  return (globalAssets || [])
    .filter((a) => a?.name && a?.imageUrl)
    .map((a) => ({
      id: a.id,
      name: String(a.name).trim(),
      type: assetKindToCastType(a.kind),
      imageUrl: a.imageUrl,
      faceUrl: a.imageUrl,
      identityId: slugIdentityId(a.name),
      global: true,
    }))
    .filter((item) => {
      const key = item.name.toLowerCase()
      if (names.has(key)) return false
      names.add(key)
      return true
    })
}

/** 合并 @ 提及与文本匹配，得到本镜关联的设定项（含全局资产库） */
export function resolveCastRefsForRow(row, castLibrary = [], globalAssets = []) {
  const local = normalizeCastLibrary(castLibrary, { requireImage: false })
  const localNames = new Set(local.map((c) => c.name.toLowerCase()))
  const globals = globalAssetsAsCastEntries(globalAssets).filter(
    (g) => !localNames.has(g.name.toLowerCase())
  )
  const lib = [...local, ...globals]
  if (!lib.length) return []

  const seen = new Set()
  const out = []

  const push = (item) => {
    const key = item?.identityId || item?.id
    if (!key || seen.has(key)) return
    seen.add(key)
    out.push(item)
  }

  const rowIdentityIds = row?.identityIds || row?.identity_ids || []
  for (const iid of rowIdentityIds) {
    const idStr = String(iid || "").trim()
    if (!idStr) continue
    const hit = lib.find((c) => c.identityId === idStr || c.id === idStr)
    if (hit) push(hit)
  }

  for (const m of allPromptMentionsForRow(row)) {
    const hit = lib.find((c) => c.id === m.id || c.name === m.name)
    if (hit) push(hit)
  }

  const text = scriptRowText(row)
  for (const item of matchCastRefsInPrompt(text, lib)) {
    push(item)
  }

  return out
}

/** 从文本中解析与设定库匹配的 @ 提及（用于高亮渲染） */
export function resolveCastMentionsInText(text, castLibrary = [], globalAssets = []) {
  const lib = [
    ...normalizeCastLibrary(castLibrary, { requireImage: false }),
    ...(globalAssets || [])
      .filter((a) => a?.name && a?.imageUrl)
      .map((a) => ({
        id: a.id,
        name: a.name,
        type: a.kind === "scene" ? "scene" : "character",
        imageUrl: a.imageUrl,
        identityId: slugIdentityId(a.name),
        source: "global",
      })),
  ]
  const mentions = []
  const seen = new Set()
  const raw = String(text || "")
  for (const item of lib) {
    const name = item.name?.trim()
    if (!name || seen.has(item.id)) continue
    const re = new RegExp(`@${escapeRegExp(name)}`, "i")
    if (re.test(raw)) {
      seen.add(item.id)
      mentions.push({
        id: item.id,
        type: item.source === "global" ? "asset" : "cast",
        name: item.name,
        identityId: item.identityId,
      })
    }
  }
  return mentions
}

/** 删除设定库条目时：仅去掉 @ 包裹，保留名称文字 */
export function unwrapCastRefsFromText(text, castItem) {
  const name = castItem?.name?.trim()
  if (!name || !text) return { text: text || "", unwrapped: false }
  const atRe = new RegExp(`@${escapeRegExp(name)}`, "gi")
  const next = String(text).replace(atRe, name)
  return { text: next, unwrapped: next !== text }
}

/** 构图参考图不应自动使用设定库图片；清除与设定库 URL 相同的参考图 */
export function stripCastImagesFromCompositionRefs(rows, castLibrary = []) {
  const castUrls = new Set()
  for (const c of normalizeCastLibrary(castLibrary, { requireImage: false })) {
    for (const url of pickCastReferenceUrls(c, { max: 4 })) {
      castUrls.add(url)
    }
  }
  if (!castUrls.size || !Array.isArray(rows)) return rows

  const isCastUrl = (url) => castUrls.has(normImageUrl(url))

  return rows.map((row) => ({
    ...row,
    referenceImage: isCastUrl(row.referenceImage) ? null : row.referenceImage,
    keyframes: (row.keyframes || []).map((kf) => ({
      ...kf,
      referenceImage: isCastUrl(kf.referenceImage) ? null : kf.referenceImage,
    })),
  }))
}

export function removeCastRefsFromText(text, castItem) {
  const name = castItem?.name?.trim()
  if (!name || !text) return { text: text || "", removed: false }
  const atRe = new RegExp(
    `@${escapeRegExp(name)}(?=\\s|$|[，。！？,.;；])`,
    "gi"
  )
  let next = String(text).replace(atRe, "").replace(/\s{2,}/g, " ").trim()
  const hadPlain = next.includes(name)
  if (hadPlain && !atRe.test(text)) {
    next = next.replace(new RegExp(escapeRegExp(name), "g"), "").replace(/\s{2,}/g, " ").trim()
  }
  return { text: next, removed: atRe.test(text) || hadPlain }
}

export function stripCastFromRow(row, removedCastItems = []) {
  if (!removedCastItems.length) return row
  const removedIds = new Set(removedCastItems.map((c) => c.id))
  const removedNames = new Set(removedCastItems.map((c) => c.name))
  const removedIdentityIds = new Set(
    removedCastItems.map((c) => c.identityId).filter(Boolean)
  )

  let prompt = row.prompt || row.description || ""
  let promptMentions = (row.promptMentions || []).filter(
    (m) => !removedIds.has(m.id) && !removedNames.has(m.name)
  )
  let identityIds = (row.identityIds || []).filter((iid) => !removedIdentityIds.has(iid))
  for (const item of removedCastItems) {
    const r = unwrapCastRefsFromText(prompt, item)
    prompt = r.text
  }

  const keyframes = (row.keyframes || []).map((kf) => {
    let kp = kf.prompt || kf.description || ""
    let km = (kf.promptMentions || []).filter(
      (m) => !removedIds.has(m.id) && !removedNames.has(m.name)
    )
    for (const item of removedCastItems) {
      kp = unwrapCastRefsFromText(kp, item).text
    }
    return {
      ...kf,
      prompt: kp,
      description: kp,
      promptMentions: km,
    }
  })

  return {
    ...row,
    prompt,
    description: prompt,
    promptMentions,
    identityIds,
    keyframes,
  }
}

export function stripRemovedCastFromRows(rows, removedCastItems = []) {
  if (!removedCastItems.length) return rows
  return rows.map((row) => stripCastFromRow(row, removedCastItems))
}

export function buildCastThemeContext(castLibrary = []) {
  const list = normalizeCastLibrary(castLibrary, { requireImage: false })
  if (!list.length) return ""
  return list
    .map((item) => {
      const kind = item.type === "scene" ? "场景" : "角色"
      const desc = item.description ? `，${item.description}` : ""
      const idNote = item.identityId ? `（identity: ${item.identityId}）` : ""
      const visual = castEntryHasReferenceImage(item)
        ? "保持与设定参考图一致的视觉特征"
        : "（待配图，以文字描述为准）"
      return `${kind}「${item.name}」${idNote}${desc}：${visual}`
    })
    .join("；")
}
