import { setMediaTicket } from "../utils/mediaTicket"
import { ensureMediaUrl } from "../utils/mediaTicket"
import { assertVideoUploadFile } from "../utils/uploadFileKind"
import { mediaClientFor } from "./mediaApi"

const UPLOAD_TIMEOUT_MS = 300_000

function uploadErrorMessage(err) {
  if (err?.code === "ECONNABORTED") {
    return "上传超时，请换较小的视频或检查网络后重试"
  }
  if (!err?.response) {
    return err?.message || "网络异常，视频未能上传"
  }
  const detail = err.response?.data?.detail
  if (typeof detail === "string") return detail
  return "视频上传失败，请重试"
}

/** 画布节点：写入上传视频 URL */
export function buildUploadedVideoNodePatch(meta) {
  return {
    videoUrl: meta.url,
    status: "completed",
    error: null,
    taskId: null,
    taskIds: null,
    pendingTrigger: null,
    videoSource: "upload",
    enhancedVideoUrl: null,
    lutVideoUrl: null,
    enhanceStatus: "idle",
  }
}

/** 上传视频并返回可持久化的 URL（/api/uploads/videos/... 或绝对 URL） */
export async function uploadVideoFile(file, { onProgress } = {}) {
  assertVideoUploadFile(file)
  const client = await mediaClientFor("canvas")
  const formData = new FormData()
  formData.append("file", file)
  const res = await client.post("/api/upload/video", formData, {
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
  const url = ensureMediaUrl(path)
  return { url, ...res.data }
}
