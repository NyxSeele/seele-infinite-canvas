/**
 * 粘贴剧本 / 意图 gate 阈值（仅文本卡前端路径）。
 * 后端规则兜底 confidence=0.82、LLM 缺省 0.75 不在此列。
 */

/** 横幅与弹窗共用的「像剧本」置信度门槛 */
export const SCREENPLAY_CONFIDENCE_THRESHOLD = 0.6

/** 文本卡内联横幅：达到此字数后才调 classify */
export const PASTE_HINT_MIN = 400

/** 文本卡点「生成」时触发意图 gate 的最低字数 */
export const TEXT_CLASSIFY_MIN = 200

/** 文本卡：低置信度时长文仍弹确认窗 */
export const TEXT_CONFIRM_MIN = 120

export function isScreenplayLike(result) {
  if (!result || result.intent !== "screenplay") return false
  return (Number(result.confidence) || 0) >= SCREENPLAY_CONFIDENCE_THRESHOLD
}
