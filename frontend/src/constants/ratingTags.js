export const RATING_TAG_OTHER = "其他"

export const IMAGE_RATING_TAGS = [
  "人物崩坏",
  "脸崩",
  "比例怪",
  "风格不对",
  "不符合描述",
  "画质差",
  RATING_TAG_OTHER,
]

export const VIDEO_RATING_TAGS = [
  "动作不自然",
  "运镜差",
  "穿模抖动",
  "风格不对",
  "不符合描述",
  "画质差",
  RATING_TAG_OTHER,
]

export function ratingTagsForTaskType(taskType) {
  if (taskType === "video") return VIDEO_RATING_TAGS
  return IMAGE_RATING_TAGS
}
