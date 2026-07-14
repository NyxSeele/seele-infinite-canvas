/** 画布图像/视频卡片：按宽高比计算预览尺寸 */

export function parseAspectParts(ratioStr) {
  const parts = String(ratioStr || "1:1").split(":").map(Number)
  if (parts.length === 2 && parts[0] > 0 && parts[1] > 0) {
    return { rw: parts[0], rh: parts[1] }
  }
  return { rw: 1, rh: 1 }
}

export function ratioStringFromDimensions(width, height) {
  const w = Math.max(1, Math.round(Number(width) || 1))
  const h = Math.max(1, Math.round(Number(height) || 1))
  const gcd = (a, b) => (b ? gcd(b, a % b) : a)
  const g = gcd(w, h)
  return `${Math.round(w / g)}:${Math.round(h / g)}`
}

export function cssAspectRatio(ratioStr) {
  const { rw, rh } = parseAspectParts(ratioStr)
  return `${rw} / ${rh}`
}

/**
 * 短边固定，长边按比例拉伸。
 * 图像默认 shortSide=280；视频 16:9 用 225 → 400×225。
 */
export function sizeForAspectRatio(ratioStr, shortSide = 280) {
  const { rw, rh } = parseAspectParts(ratioStr)
  if (rw >= rh) {
    return {
      width: Math.round((shortSide * rw) / rh),
      height: shortSide,
    }
  }
  return {
    width: shortSide,
    height: Math.round((shortSide * rh) / rw),
  }
}

export function normalizeClarityLabel(value, fallback = "720P") {
  const raw = String(value || "").trim().toUpperCase().replace("×", "x")
  if (!raw) return fallback
  if (raw === "480" || raw === "720" || raw === "1080") return `${raw}P`
  if (raw === "480P" || raw === "720P" || raw === "1080P") return raw
  if (raw === "2K") return "720P"
  if (raw === "3K") return "1080P"
  if (/^\d+x\d+$/i.test(raw)) return fallback
  return fallback
}

export const DEFAULT_IMAGE_CARD_RATIO = "1:1"
export const DEFAULT_VIDEO_CARD_RATIO = "16:9"

/** 卡片预览尺寸用比例 */
export function cardDisplayRatio(data, kind = "image") {
  const hasResults = Array.isArray(data?.results) && data.results.some(Boolean)
  const isUploadOnly =
    kind === "image"
    && data?.uploadedImage
    && !hasResults
    && !data?.imageUrl

  // 纯上传态：卡片必须跟上传图真实比例走，不能被旧 cardDisplayRatio / imgRatio 挡住
  if (isUploadOnly) {
    if (data?.uploadAspectRatio) return data.uploadAspectRatio
    if (data?.cardDisplayRatio) return data.cardDisplayRatio
    return DEFAULT_IMAGE_CARD_RATIO
  }

  if (data?.cardDisplayRatio) return data.cardDisplayRatio
  if (kind === "video" && data?.videoUrl && data?.vidRatio) return data.vidRatio
  if (kind === "image" && (data?.imageUrl || hasResults) && data?.imgRatio) {
    return data.imgRatio
  }
  return kind === "video" ? DEFAULT_VIDEO_CARD_RATIO : DEFAULT_IMAGE_CARD_RATIO
}
