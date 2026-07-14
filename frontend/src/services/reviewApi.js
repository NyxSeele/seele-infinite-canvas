import api from "./api"

export async function publishReviewVideo(payload) {
  const res = await api.post("/api/review/videos", payload)
  return res.data
}

export async function listMyReviewVideos() {
  const res = await api.get("/api/review/videos/mine")
  return res.data || []
}

export async function unpublishReviewVideo(id) {
  const res = await api.delete(`/api/review/videos/${id}`)
  return res.data
}

export async function presignReviewVideoUpload({ filename, content_type, size_bytes }) {
  const res = await api.post("/api/review/presign-video", {
    filename,
    content_type,
    size_bytes,
  })
  return res.data
}

/** Rehost /api/view|/api/uploads (or pass through public URLs) for anonymous review. */
export async function importReviewVideoFromUrl(source_url) {
  const res = await api.post("/api/review/import-video", { source_url })
  return res.data
}

/** Upload cover to R2 (public URL for anonymous review pages). */
export async function uploadReviewThumbnail(file) {
  const form = new FormData()
  form.append("file", file)
  const res = await api.post("/api/review/upload-thumbnail", form, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  return res.data
}
