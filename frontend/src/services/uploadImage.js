import api, { API_BASE } from "./api"
import {
  getUploadCapabilities,
  mediaClientFor,
  shouldUseMediaBase,
} from "./mediaApi"
import { setMediaTicket } from "../utils/mediaTicket"
import {
  isHeicFile,
  prepareImageForR2Direct,
  prepareImageForUpload,
} from "../utils/compressImageForUpload"
import { ratioStringFromDimensions, sizeForAspectRatio } from "../utils/canvas/aspectRatioLayout"
import { encodePublicMediaUrl } from "../utils/encodePublicMediaUrl"
import { assertImageUploadFile } from "../utils/uploadFileKind"
import { ensureMediaUrl } from "../utils/mediaTicket"
import {
  fetchR2PublicBase,
  rememberR2PublicBaseFromUrl,
  resolveCanvasR2MediaUrl,
} from "../utils/r2MediaUrl"
import { uploadToPresignedUrl } from "./teamFilesApi"

const UPLOAD_TIMEOUT_MS = 120_000
const R2_PUT_TIMEOUT_MS = 180_000

export function isBlobUrl(url) {
  return typeof url === "string" && url.startsWith("blob:")
}

function isDataUrl(url) {
  return typeof url === "string" && url.startsWith("data:")
}

function uploadErrorMessage(err) {
  if (err?.code === "ECONNABORTED") {
    return "上传超时，请换较小的图片或检查网络后重试"
  }
  if (!err?.response) {
    if (err?.message?.includes("HTTP")) return err.message
    if (err?.message?.includes("上传")) return err.message
    return "网络异常，图片未能上传（请检查网络或刷新后重试）"
  }
  const detail = err.response?.data?.detail
  if (typeof detail === "string") return detail
  return "图片上传失败，请重试"
}

function resolveUploadMeta(prep, data) {
  const width = Number(data?.width) || prep.width || 0
  const height = Number(data?.height) || prep.height || 0
  const aspectRatio =
    data?.aspect_ratio
    || prep.aspectRatio
    || (width && height ? ratioStringFromDimensions(width, height) : "1:1")
  return { width, height, aspectRatio }
}

function normalizeUploadedUrl(path) {
  if (!path) return path
  if (path.startsWith("http")) return ensureMediaUrl(path)
  const sameOrigin = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`
  return ensureMediaUrl(sameOrigin)
}

/** 仅当后端明确返回 R2 不可用时才走 Tunnel 回退 */
function shouldFallbackToServerUpload(err) {
  const status = err?.response?.status
  return status === 503 || status === 502
}

async function postImageFile(file, { onProgress } = {}) {
  const client = await mediaClientFor("canvas")
  const formData = new FormData()
  formData.append("file", file)
  const res = await client.post("/api/upload/image", formData, {
    timeout: UPLOAD_TIMEOUT_MS,
    onUploadProgress: onProgress
      ? (event) => {
          if (!event.total) return
          onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
        }
      : undefined,
  })
  const path = res.data?.url
  if (!path) throw new Error("上传未返回 url")
  if (res.data?.media_ticket) {
    setMediaTicket(res.data.media_ticket, res.data.expires_at)
  }
  return { res, url: normalizeUploadedUrl(path) }
}

async function uploadImageViaR2Direct(file, { onProgress, onPhase, width, height } = {}) {
  const contentType = (file.type || "application/octet-stream").split(";")[0].trim()
  const presignRes = await api.post("/api/upload/presign-image", {
    filename: file.name || "image.jpg",
    content_type: contentType || "image/jpeg",
    size_bytes: file.size,
  })
  const { upload_url: uploadUrl, key, content_type: signedType } = presignRes.data
  await uploadToPresignedUrl(uploadUrl, file, signedType, onProgress, R2_PUT_TIMEOUT_MS)
  const registerBody = {
    key,
    content_type: signedType,
    filename: file.name || null,
  }
  if (width > 0 && height > 0) {
    registerBody.width = width
    registerBody.height = height
  }
  const registerRes = await api.post(
    "/api/upload/register-image",
    registerBody,
    { timeout: UPLOAD_TIMEOUT_MS },
  )
  const data = registerRes.data
  const url = encodePublicMediaUrl(data.url)
  rememberR2PublicBaseFromUrl(url)
  return {
    url,
    width: data.width,
    height: data.height,
    aspectRatio: data.aspect_ratio || ratioStringFromDimensions(data.width, data.height),
  }
}

/** 画布节点：写入上传图 URL + 真实宽高比，并同步卡片占位尺寸 */
export function buildUploadedImageNodePatch(meta) {
  const ratio =
    meta.aspectRatio
    || (meta.width && meta.height ? ratioStringFromDimensions(meta.width, meta.height) : "")
    || "1:1"
  const { width, height } = sizeForAspectRatio(ratio)
  return {
    uploadedImage: meta.url,
    uploadAspectRatio: ratio,
    cardDisplayRatio: ratio,
    cardWidth: width,
    cardHeight: height,
    imageSource: "upload",
    status: "input",
    error: null,
    imageUrl: null,
    results: [],
  }
}

/** 上传图片并返回 URL + 宽高比（画布上传用；local 优先 AutoDL 公网，否则 R2 直传） */
export async function uploadImageFileWithMeta(file, { onProgress, onPhase } = {}) {
  assertImageUploadFile(file)
  await getUploadCapabilities()

  if (isHeicFile(file)) {
    onPhase?.("prepare")
    const prep = await prepareImageForUpload(file)
    try {
      onPhase?.("upload")
      const { res, url } = await postImageFile(prep.file, { onProgress })
      const meta = resolveUploadMeta(prep, res.data)
      return { url, ...meta }
    } catch (err) {
      const msg = uploadErrorMessage(err)
      const wrapped = new Error(msg)
      wrapped.cause = err
      wrapped.response = err?.response
      throw wrapped
    }
  }

  if (shouldUseMediaBase("canvas")) {
    onPhase?.("prepare")
    const prep = await prepareImageForUpload(file, {
      maxEdge: 2048,
      skipBelowBytes: 2 * 1024 * 1024,
    })
    try {
      onPhase?.("upload")
      const { res, url } = await postImageFile(prep.file, { onProgress })
      const meta = resolveUploadMeta(prep, res.data)
      return { url, ...meta }
    } catch (err) {
      const msg = uploadErrorMessage(err)
      const wrapped = new Error(msg)
      wrapped.cause = err
      wrapped.response = err?.response
      throw wrapped
    }
  }

  try {
    onPhase?.("prepare")
    const prep = await prepareImageForR2Direct(file)
    onPhase?.("upload")
    return await uploadImageViaR2Direct(prep.file, {
      onProgress,
      onPhase,
      width: prep.width,
      height: prep.height,
    })
  } catch (err) {
    if (!shouldFallbackToServerUpload(err)) {
      const msg = uploadErrorMessage(err)
      const wrapped = new Error(msg)
      wrapped.cause = err
      wrapped.response = err?.response
      throw wrapped
    }
  }

  onPhase?.("prepare")
  const prep = await prepareImageForUpload(file)
  try {
    onPhase?.("upload")
    const { res, url } = await postImageFile(prep.file, { onProgress })
    const meta = resolveUploadMeta(prep, res.data)
    return { url, ...meta }
  } catch (err) {
    const msg = uploadErrorMessage(err)
    const wrapped = new Error(msg)
    wrapped.cause = err
    wrapped.response = err?.response
    throw wrapped
  }
}

/** 将 data:/blob: 参考图上传为 http URL，避免 POST body 过大或 431 */
export async function resolveReferenceUrlForApi(url) {
  if (!url || typeof url !== "string") return null
  const trimmed = url.trim()
  if (!trimmed) return null
  if (trimmed.startsWith("http") && !isDataUrl(trimmed)) {
    rememberR2PublicBaseFromUrl(trimmed)
    const resolved = resolveCanvasR2MediaUrl(trimmed)
    if (resolved.startsWith("http")) {
      try {
        const parsed = new URL(resolved)
        if (parsed.pathname.startsWith("/api/uploads/") || parsed.pathname.startsWith("/uploads/")) {
          return parsed.pathname.split("?")[0]
        }
      } catch {
        /* keep resolved */
      }
      return resolved
    }
    try {
      const parsed = new URL(trimmed)
      if (parsed.pathname.startsWith("/api/uploads/") || parsed.pathname.startsWith("/uploads/")) {
        return parsed.pathname.split("?")[0]
      }
    } catch {
      /* keep original */
    }
    return trimmed
  }
  if (!isDataUrl(trimmed) && !isBlobUrl(trimmed)) {
    await fetchR2PublicBase(api)
    const resolved = resolveCanvasR2MediaUrl(trimmed)
    if (resolved.startsWith("http")) return resolved
    return trimmed
  }

  const res = await fetch(trimmed)
  const blob = await res.blob()
  const ext = blob.type?.includes("png") ? "png" : "jpg"
  const file = new File([blob], `ref.${ext}`, { type: blob.type || "image/jpeg" })
  const { url: uploaded } = await uploadImageFileWithMeta(file)
  return uploaded
}

export async function dataUrlToFile(dataUrl, filename = "avatar.jpg") {
  const res = await fetch(dataUrl)
  const blob = await res.blob()
  const ext = blob.type?.includes("png") ? "png" : "jpg"
  return new File([blob], filename.replace(/\.[^.]+$/, `.${ext}`), {
    type: blob.type || "image/jpeg",
  })
}

/** 上传图片，返回可持久化的绝对 URL（禁止 blob:） */
export async function uploadImageFile(file, { onProgress } = {}) {
  const { url } = await uploadImageFileWithMeta(file, { onProgress })
  return url
}
