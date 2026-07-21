import {
  matchCastRefsInPrompt,
  normalizeCastLibrary,
  pickCastFaceUrl,
  pickCastReferenceUrls,
  resolveCastRefsForRow,
} from "./castLibrary"
import { normalizeSceneLibrary } from "./sceneLibrary"
import { scriptRowText } from "./scriptTableKeyframes"

/** 角色库：排除历史误写入 cast_library 的场景条目 */
export function characterCastLibrary(castLibrary = []) {
  return normalizeCastLibrary(castLibrary, { requireImage: false }).filter((c) => c.type !== "scene")
}

export function resolveCharacterRefsForRow(row, castLibrary = [], globalAssets = []) {
  const assets = (globalAssets || []).filter((a) => a?.kind !== "scene")
  return resolveCastRefsForRow(row, characterCastLibrary(castLibrary), assets)
}

export function resolveSceneRefsForRow(row, sceneLibrary = []) {
  const lib = normalizeSceneLibrary(sceneLibrary, { requireImage: false })
  if (!lib.length) return []

  const seen = new Set()
  const out = []
  const push = (item) => {
    if (!item?.id || seen.has(item.id)) return
    seen.add(item.id)
    out.push(item)
  }

  const locId = row.locationId || row.location_id
  if (locId) {
    const hit = lib.find((s) => s.id === locId)
    if (hit) push(hit)
  }

  const text = scriptRowText(row)
  for (const item of matchCastRefsInPrompt(text, lib)) {
    push(item)
  }

  return out.filter((s) => s.imageUrl)
}

export function extractIdentityIdsFromCast(matchedCast = []) {
  return [...new Set(matchedCast.map((c) => c.identityId).filter(Boolean))]
}

export function buildEntityRefAudit(matchedCast = []) {
  return matchedCast.map((c) => ({
    identityId: c.identityId || null,
    name: c.name || "",
    urls: pickCastReferenceUrls(c),
  }))
}

export function isMissingIdentityApiError(err) {
  const detail = err?.response?.data?.detail
  if (detail && typeof detail === "object" && detail.code === "missing_identity") {
    return detail
  }
  return null
}

/**
 * 收集本镜应注入的参考图 URL（角色 + 场景）
 */
export function collectEntityReferenceUrls(
  row,
  { castLibrary = [], sceneLibrary = [], globalAssets = [] } = {},
  { maxCharacters = 3, maxScenes = 1 } = {}
) {
  const characters = resolveCharacterRefsForRow(row, castLibrary, globalAssets)
  const scenes = resolveSceneRefsForRow(row, sceneLibrary)
  const charUrls = []
  const seen = new Set()
  for (const c of characters) {
    for (const url of pickCastReferenceUrls(c, { max: maxCharacters })) {
      if (seen.has(url)) continue
      seen.add(url)
      charUrls.push(url)
      if (charUrls.length >= maxCharacters) break
    }
    if (charUrls.length >= maxCharacters) break
  }
  const sceneUrls = scenes.map((s) => s.imageUrl).filter(Boolean).slice(0, maxScenes)
  return [...charUrls, ...sceneUrls]
}

/** 与分镜表相连的 character-card 节点 → prompt compile 用 character_refs */
export function collectConnectedCharacterRefs(nodes = [], edges = [], nodeId) {
  if (!nodeId) return []
  const byId = new Map((nodes || []).map((n) => [n.id, n]))
  const refs = []
  const seen = new Set()

  for (const edge of edges || []) {
    let otherId = null
    if (edge.source === nodeId) otherId = edge.target
    else if (edge.target === nodeId) otherId = edge.source
    else continue

    const node = byId.get(otherId)
    if (node?.type !== "character-card") continue
    const name = (node.data?.name || "").trim()
    if (!name || seen.has(name)) continue
    seen.add(name)
    refs.push({
      name,
      appearance: (node.data?.appearance || "").trim(),
      identityId: node.data?.identityId || null,
    })
  }
  return refs
}

/** 与出图卡相连的 character-card 首张参考脸 URL（用于 flux-pulid） */
export function collectConnectedCharacterFaceUrl(nodes = [], edges = [], nodeId) {
  if (!nodeId) return null
  const byId = new Map((nodes || []).map((n) => [n.id, n]))
  for (const edge of edges || []) {
    let otherId = null
    if (edge.source === nodeId) otherId = edge.target
    else if (edge.target === nodeId) otherId = edge.source
    else continue
    const node = byId.get(otherId)
    if (node?.type !== "character-card") continue
    const face = pickCastFaceUrl({
      faceUrl: node.data?.faceUrl,
      imageUrl: node.data?.referenceImages?.[0],
    })
    if (face) return face
  }
  return null
}

export function mergeCharacterRefsForCompile(...groups) {
  const out = []
  const seen = new Set()
  for (const group of groups) {
    for (const ref of group || []) {
      const name = (ref?.name || "").trim()
      if (!name || seen.has(name)) continue
      seen.add(name)
      out.push({
        name,
        appearance: (ref?.appearance || ref?.desc || ref?.description || ref?.prompt || ref?.note || "").trim(),
        identityId: ref?.identityId || null,
      })
    }
  }
  return out
}

export function buildEntityThemeContext(row, castLibrary = [], sceneLibrary = [], globalAssets = []) {
  const chars = resolveCharacterRefsForRow(row, castLibrary, globalAssets)
  const scenes = resolveSceneRefsForRow(row, sceneLibrary)
  const parts = []
  for (const c of chars) {
    const desc = c.description ? `，${c.description}` : ""
    const idNote = c.identityId ? `（identity: ${c.identityId}）` : ""
    parts.push(`角色「${c.name}」${idNote}${desc}：跨镜头保持同一身份视觉一致`)
  }
  for (const s of scenes) {
    const desc = s.description ? `，${s.description}` : ""
    parts.push(`场景「${s.name}」${desc}：保持与场景参考图一致的空间与氛围`)
  }
  return parts.join("；")
}

export function buildScriptShotIdentityPayload(row, castLibrary = []) {
  const lib = characterCastLibrary(castLibrary)
  return {
    cast_library: lib.map((c) => ({
      id: c.id,
      name: c.name,
      type: c.type,
      identityId: c.identityId,
      faceUrl: c.faceUrl,
      threeViewUrl: c.threeViewUrl,
      costumeUrl: c.costumeUrl,
      imageUrl: c.imageUrl,
    })),
    identity_ids: row?.identityIds || [],
    row: {
      identityIds: row?.identityIds || [],
      promptMentions: row?.promptMentions || [],
      prompt: row?.prompt || row?.description || "",
      description: row?.description || row?.prompt || "",
    },
  }
}

export function formatMissingIdentityMessage(detail) {
  if (!detail) return "角色缺少 identity 或参考图"
  const names = (detail.names || []).join("、")
  return detail.message || (names ? `角色 ${names} 缺少 identity 或参考图` : "角色缺少 identity 或参考图")
}

export function resolveShotEntityRefs(row, castLibrary, sceneLibrary, globalAssets) {
  const matchedCast = resolveCharacterRefsForRow(row, castLibrary, globalAssets)
  const matchedScenes = resolveSceneRefsForRow(row, sceneLibrary)
  const entityRefUrls = collectEntityReferenceUrls(row, {
    castLibrary,
    sceneLibrary,
    globalAssets,
  })
  const charFaceUrls = matchedCast.map((c) => pickCastFaceUrl(c)).filter(Boolean)
  return {
    matchedCast,
    matchedScenes,
    entityRefUrls,
    charFaceUrls,
    identityIds: extractIdentityIdsFromCast(matchedCast),
    entityRefAudit: buildEntityRefAudit(matchedCast),
  }
}
