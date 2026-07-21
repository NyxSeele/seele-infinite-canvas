import { setMediaTicket } from "../utils/mediaTicket"
import { ensureMediaUrl } from "../utils/mediaTicket"
import { mediaClientFor } from "./mediaApi"

export const AUDIO_ACCEPT =
  "audio/mpeg,audio/wav,audio/mp4,audio/ogg,audio/flac,.mp3,.wav,.m4a,.ogg,.flac"

/** 上传参考音频，返回带 ticket 的 /api/uploads/audio/... URL */
export async function uploadAudioFile(file) {
  const client = await mediaClientFor("canvas")
  const formData = new FormData()
  formData.append("file", file)
  const res = await client.post("/api/upload/audio", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  const url = res.data?.url
  if (!url) throw new Error("上传失败：未返回 URL")
  if (res.data?.media_ticket) {
    setMediaTicket(res.data.media_ticket, res.data.expires_at)
  }
  return ensureMediaUrl(url)
}
