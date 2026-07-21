export const IMAGE_ACCEPT =
  "image/jpeg,image/png,image/webp,image/gif,.jpg,.jpeg,.png,.webp,.gif,.heic,.heif"

export const VIDEO_ACCEPT =
  "video/mp4,video/quicktime,.mp4,.mov,.m4v"

const VIDEO_EXT_RE = /\.(mp4|webm|mov|mkv|avi|m4v)$/i
const IMAGE_EXT_RE = /\.(jpe?g|png|webp|gif|heic|heif)$/i

export function isVideoFile(file) {
  if (!file) return false
  const type = (file.type || "").toLowerCase().split(";")[0].trim()
  if (type.startsWith("video/")) return true
  const name = file.name || ""
  if (VIDEO_EXT_RE.test(name)) return true
  // 部分移动端/微信导出视频为 octet-stream 或无扩展名
  if (!type || type === "application/octet-stream") {
    return VIDEO_EXT_RE.test(name)
  }
  return false
}

export function isImageFile(file) {
  if (!file) return false
  const type = (file.type || "").toLowerCase().split(";")[0].trim()
  if (type.startsWith("image/")) return true
  if (type.startsWith("video/")) return false
  return IMAGE_EXT_RE.test(file.name || "")
}

export function assertImageUploadFile(file) {
  if (!file) throw new Error("未选择文件")
  if (isVideoFile(file)) {
    throw new Error("所选文件是视频。上传视频请使用「上传视频」")
  }
  if (!isImageFile(file)) {
    throw new Error("不支持的文件格式，请上传 JPG/PNG/WebP/GIF 图片")
  }
}

export function assertVideoUploadFile(file) {
  if (!file) throw new Error("未选择文件")
  if (isImageFile(file) && !isVideoFile(file)) {
    throw new Error("所选文件是图片。上传图片请使用「上传图片」")
  }
  if (!isVideoFile(file)) {
    throw new Error("不支持的文件格式，请上传 MP4 或 MOV 视频")
  }
}
