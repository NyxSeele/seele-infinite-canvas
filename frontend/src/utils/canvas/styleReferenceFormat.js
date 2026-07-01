/** 镜头级风格参考 → prompt 文本（与后端 format_style_for_prompt 对齐） */

export function formatStyleForPrompt(ref) {
  if (!ref || typeof ref !== "object") return ""
  const color = String(ref.color_tone || "").trim()
  const lighting = String(ref.lighting || "").trim()
  const shotLang = String(ref.shot_language || "").trim()
  const parts = [color, lighting, shotLang].filter(Boolean)
  let block = ""
  if (parts.length) {
    block = `[风格参考：${parts.join("，")}]`
  }
  const keywords = Array.isArray(ref.style_keywords)
    ? ref.style_keywords.map((k) => String(k).trim()).filter(Boolean)
    : []
  if (keywords.length) {
    const kwText = keywords.join(", ")
    block = block ? `${block} ${kwText}` : kwText
  }
  return block
}

export function appendStyleReferenceToDescription(description, styleRef) {
  const block = formatStyleForPrompt(styleRef)
  const base = String(description || "").trim()
  if (!block) return base
  if (!base) return block
  return `${block}\n\n${base}`
}

export function styleReferenceSummary(ref) {
  if (!ref) return ""
  const summary = String(ref.display_summary || "").trim()
  if (summary) return summary
  const keywords = Array.isArray(ref.style_keywords) ? ref.style_keywords : []
  if (keywords.length) return keywords.slice(0, 4).join(" · ")
  return formatStyleForPrompt(ref).slice(0, 80)
}
