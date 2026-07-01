import {
  matchCastRefsInPrompt,
  normalizeCastLibrary,
  resolveCastRefsForRow,
} from "./castLibrary"
import { normalizeSceneLibrary } from "./sceneLibrary"
import { scriptRowText } from "./scriptTableKeyframes"

/** 角色库：排除历史误写入 cast_library 的场景条目 */
export function characterCastLibrary(castLibrary = []) {
  return normalizeCastLibrary(castLibrary).filter((c) => c.type !== "scene")
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
  const charUrls = characters.map((c) => c.imageUrl).filter(Boolean).slice(0, maxCharacters)
  const sceneUrls = scenes.map((s) => s.imageUrl).filter(Boolean).slice(0, maxScenes)
  return [...charUrls, ...sceneUrls]
}

export function buildEntityThemeContext(row, castLibrary = [], sceneLibrary = [], globalAssets = []) {
  const chars = resolveCharacterRefsForRow(row, castLibrary, globalAssets)
  const scenes = resolveSceneRefsForRow(row, sceneLibrary)
  const parts = []
  for (const c of chars) {
    const desc = c.description ? `，${c.description}` : ""
    parts.push(`角色「${c.name}」${desc}：保持与设定参考图一致的视觉特征`)
  }
  for (const s of scenes) {
    const desc = s.description ? `，${s.description}` : ""
    parts.push(`场景「${s.name}」${desc}：保持与场景参考图一致的空间与氛围`)
  }
  return parts.join("；")
}
