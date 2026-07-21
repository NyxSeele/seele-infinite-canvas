import {
  matchCastRefsInPrompt,
  normalizeCastLibrary,
  normalizeCastLibraryEntry,
  slugIdentityId,
  stripCastImagesFromCompositionRefs,
} from "./castLibrary"
import {
  keyframeText,
  shotPromptText,
  syncRowFromKeyframes,
} from "./scriptTableKeyframes"

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

function rowContextText(row, segment) {
  return [
    shotPromptText(row),
    row.description,
    row.characters,
    row.scene,
    row.location,
    segment?.title,
    segment?.description,
  ]
    .filter(Boolean)
    .join(" ")
}

function mergeCastMentions(existing = [], castItems = []) {
  const mentions = [...existing]
  const seen = new Set(mentions.map((m) => m.id || m.name))
  for (const cast of castItems) {
    if (seen.has(cast.id) || seen.has(cast.name)) continue
    seen.add(cast.id)
    mentions.push({ id: cast.id, type: "cast", name: cast.name })
  }
  return mentions
}

/** 在名称首次出现处插入 @名称，而非追加到文末 */
function insertMentionAtFirstOccurrence(text, castItems) {
  let result = (text || "").trim()
  if (!result || !castItems?.length) return result

  for (const cast of castItems) {
    const name = cast.name?.trim()
    if (!name) continue
    if (new RegExp(`@${escapeRegExp(name)}(?=\\s|$|[，。！？,.;；])`, "i").test(result)) {
      continue
    }
    const nameRe = new RegExp(escapeRegExp(name))
    const idx = result.search(nameRe)
    if (idx === -1) continue
    result = `${result.slice(0, idx)}@${name}${result.slice(idx + name.length)}`
  }
  return result
}

function syncKeyframeWithCast(kf, rowContext, castItems) {
  const kfText = keyframeText(kf) || rowContext
  const matched = matchCastRefsInPrompt(kfText, castItems)
  if (!matched.length) return kf
  const promptMentions = mergeCastMentions(kf.promptMentions, matched)
  const prompt = insertMentionAtFirstOccurrence(kf.prompt || kf.description, matched)
  return {
    ...kf,
    prompt,
    description: prompt || kf.description,
    promptMentions,
  }
}

/**
 * 设定库变更后，自动把相关镜头/分镜格与设定关联（@ 提及 + 参考图）
 */
export function applyCastLibraryAutoLink(rows, segments, castLibrary) {
  const lib = normalizeCastLibrary(castLibrary)
  if (!lib.length || !Array.isArray(rows) || rows.length === 0) return rows

  const segById = new Map((segments || []).map((s) => [s.id, s]))

  const linked = rows.map((row) => {
    const segment = segById.get(row.segmentId)
    const context = rowContextText(row, segment)
    const matched = matchCastRefsInPrompt(context, lib)
    if (!matched.length) return row

    const prompt = insertMentionAtFirstOccurrence(shotPromptText(row), matched)
    const promptMentions = mergeCastMentions(row.promptMentions, matched)
    const identityIds = [
      ...new Set([
        ...(row.identityIds || []),
        ...matched.map((m) => m.identityId).filter(Boolean),
      ]),
    ]

    const keyframes = (row.keyframes || []).map((kf) =>
      syncKeyframeWithCast(kf, context, matched)
    )

    return syncRowFromKeyframes({
      ...row,
      prompt,
      description: prompt,
      promptMentions,
      identityIds,
      keyframes,
    })
  })

  return stripCastImagesFromCompositionRefs(linked, lib)
}

/** CharacterCard 更新后，按 assetId / 名称同步分镜表 castLibrary 条目 */
export function mergeCastEntryFromCharacterCard(castLibrary = [], cardData = {}) {
  const name = String(cardData.name || "").trim()
  if (!name) return castLibrary

  const faceUrl = cardData.faceUrl || cardData.referenceImages?.[0] || cardData.imageUrl || null
  const patch = normalizeCastLibraryEntry({
    name,
    type: "character",
    identityId: cardData.identityId || slugIdentityId(name),
    faceUrl,
    threeViewUrl: cardData.threeViewUrl || null,
    costumeUrl: cardData.costumeUrl || null,
    imageUrl: faceUrl,
    description: cardData.appearance || cardData.description || "",
    assetId: cardData.assetId,
    globalAssetId: cardData.globalAssetId,
  })
  if (!patch) return castLibrary

  const lib = [...(castLibrary || [])]
  const idx = lib.findIndex(
    (c) =>
      (cardData.assetId && c.assetId === cardData.assetId)
      || (cardData.globalAssetId && c.globalAssetId === cardData.globalAssetId)
      || String(c.name || "").toLowerCase() === name.toLowerCase()
  )
  if (idx >= 0) {
    lib[idx] = { ...lib[idx], ...patch, id: lib[idx].id }
  }
  return lib
}

export function syncCastLibraryOnScriptTables(setNodes, cardData) {
  if (!cardData?.name) return
  setNodes((ns) =>
    ns.map((n) => {
      if (n.type !== "script-table") return n
      const nextLib = mergeCastEntryFromCharacterCard(n.data?.castLibrary, cardData)
      if (nextLib === n.data?.castLibrary) return n
      return { ...n, data: { ...n.data, castLibrary: nextLib } }
    })
  )
}
