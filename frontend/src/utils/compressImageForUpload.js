/** 上传前压缩：缩小体积加快 Tunnel 传输；返回宽高供画布按比例展示。 */
import { ratioStringFromDimensions } from "./canvas/aspectRatioLayout"
import { isVideoFile } from "./uploadFileKind"

const DEFAULT_MAX_EDGE = 1280
const R2_MAX_EDGE = 2048
const JPEG_QUALITY = 0.8
const WEBP_QUALITY = 0.82
/** 小于此体积且长边已够短则跳过压缩 */
const DEFAULT_SKIP_BELOW_BYTES = 380 * 1024
const R2_SKIP_BELOW_BYTES = 2 * 1024 * 1024

export function isHeicFile(file) {
  const type = (file.type || "").toLowerCase()
  const name = (file.name || "").toLowerCase()
  return (
    type.includes("heic")
    || type.includes("heif")
    || /\.heic$/.test(name)
    || /\.heif$/.test(name)
  )
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("toBlob failed"))),
      type,
      quality,
    )
  })
}

async function encodeCanvas(canvas) {
  const jpeg = await canvasToBlob(canvas, "image/jpeg", JPEG_QUALITY)
  try {
    const webp = await canvasToBlob(canvas, "image/webp", WEBP_QUALITY)
    if (webp.size < jpeg.size * 0.88) {
      return { blob: webp, type: "image/webp", ext: ".webp" }
    }
  } catch {
    /* WebP 不可用则回退 JPEG */
  }
  return { blob: jpeg, type: "image/jpeg", ext: ".jpg" }
}

/**
 * @returns {{ file: File, width: number, height: number, aspectRatio: string, compressed: boolean }}
 */
export async function prepareImageForUpload(file, options = {}) {
  const maxEdge = options.maxEdge ?? DEFAULT_MAX_EDGE
  const skipBelowBytes = options.skipBelowBytes ?? DEFAULT_SKIP_BELOW_BYTES
  if (!file || !(file instanceof File)) {
    return {
      file,
      width: 1,
      height: 1,
      aspectRatio: "1:1",
      compressed: false,
    }
  }

  if (isVideoFile(file)) {
    throw new Error("所选文件是视频。上传视频请使用「上传视频」")
  }

  if (isHeicFile(file)) {
    return {
      file,
      width: 0,
      height: 0,
      aspectRatio: "",
      compressed: false,
    }
  }

  const type = (file.type || "").toLowerCase()
  const name = (file.name || "").toLowerCase()
  const looksLikeImage =
    type.startsWith("image/")
    || /\.(jpe?g|png|webp|gif)$/.test(name)
  if (!looksLikeImage) {
    return {
      file,
      width: 1,
      height: 1,
      aspectRatio: "1:1",
      compressed: false,
    }
  }

  let bitmap
  try {
    bitmap = await createImageBitmap(file)
    const { width, height } = bitmap
    if (!width || !height) {
      return {
        file,
        width: 1,
        height: 1,
        aspectRatio: "1:1",
        compressed: false,
      }
    }

    const longestEdge = Math.max(width, height)
    const needsResize = longestEdge > maxEdge
    const needsCompress = needsResize || file.size > skipBelowBytes
    if (!needsCompress) {
      return {
        file,
        width,
        height,
        aspectRatio: ratioStringFromDimensions(width, height),
        compressed: false,
      }
    }

    const scale = needsResize ? maxEdge / longestEdge : 1
    const w = Math.max(1, Math.round(width * scale))
    const h = Math.max(1, Math.round(height * scale))
    const canvas = document.createElement("canvas")
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext("2d")
    if (!ctx) {
      return {
        file,
        width,
        height,
        aspectRatio: ratioStringFromDimensions(width, height),
        compressed: false,
      }
    }
    ctx.drawImage(bitmap, 0, 0, w, h)
    const encoded = await encodeCanvas(canvas)
    if (!encoded.blob || encoded.blob.size >= file.size * 0.95) {
      return {
        file,
        width,
        height,
        aspectRatio: ratioStringFromDimensions(width, height),
        compressed: false,
      }
    }
    const base = (file.name || "upload").replace(/\.[^.]+$/, "") || "upload"
    return {
      file: new File([encoded.blob], `${base}${encoded.ext}`, {
        type: encoded.type,
        lastModified: file.lastModified,
      }),
      width: w,
      height: h,
      aspectRatio: ratioStringFromDimensions(w, h),
      compressed: true,
    }
  } catch {
    return {
      file,
      width: 0,
      height: 0,
      aspectRatio: "",
      compressed: false,
    }
  } finally {
    bitmap?.close?.()
  }
}

/** R2 直传前：大图压缩到 2048 边长内，保留宽高供 register-image 上报 */
export async function prepareImageForR2Direct(file) {
  return prepareImageForUpload(file, {
    maxEdge: R2_MAX_EDGE,
    skipBelowBytes: R2_SKIP_BELOW_BYTES,
  })
}

/** @deprecated 使用 prepareImageForUpload */
export async function compressImageForUpload(file) {
  const prep = await prepareImageForUpload(file)
  return prep.file
}
