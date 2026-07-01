function extFromUrl(url, fallback = "bin") {
  try {
    const path = new URL(url, window.location.origin).pathname
    const m = path.match(/\.([a-z0-9]+)$/i)
    return m ? m[1].toLowerCase() : fallback
  } catch {
    return fallback
  }
}

/** 下载远程媒体（走同源 /api/view 或 blob URL） */
export async function downloadMediaUrl(url, filenamePrefix = "media") {
  if (!url) return
  const res = await fetch(url, { credentials: "include" })
  if (!res.ok) {
    throw new Error(`下载失败 HTTP ${res.status}`)
  }
  const blob = await res.blob()
  const ext = extFromUrl(url, blob.type?.includes("video") ? "mp4" : "png")
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = objectUrl
  link.download = `${filenamePrefix}-${Date.now()}.${ext}`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(objectUrl)
}
