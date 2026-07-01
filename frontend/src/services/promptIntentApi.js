import api from "./api"
import {
  isScreenplayLike,
  PASTE_HINT_MIN,
  SCREENPLAY_CONFIDENCE_THRESHOLD,
  TEXT_CONFIRM_MIN,
} from "../utils/canvas/promptIntentConfig"

/**
 * @param {string} text
 * @param {{ context?: 'text'|'image'|'video', currentTextMode?: string }} options
 */
export async function classifyPromptIntent(text, options = {}) {
  const res = await api.post("/api/prompt/classify-intent", {
    text: text.trim(),
    context: options.context || "text",
    current_text_mode: options.currentTextMode || null,
  })
  return res.data
}

/** 是否需要在生成前弹出确认（仅文本卡） */
export function shouldConfirmIntent(result, { textMode, promptLength }) {
  if (!result) return false
  const conf = Number(result.confidence) || 0
  const warnings = result.warnings || []
  if (warnings.length > 0) return true
  if (isScreenplayLike(result) && textMode !== "screenplay") return true
  if (promptLength >= PASTE_HINT_MIN) return true
  if (conf < SCREENPLAY_CONFIDENCE_THRESHOLD && promptLength >= TEXT_CONFIRM_MIN) return true
  return false
}
