/** 首字母大写（其余不变） */
export function capitalizeFirst(str) {
  const s = String(str || "").trim()
  if (!s) return s
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** 每个单词首字母大写（按空格/连字符分词） */
export function titleCaseWords(str) {
  const s = String(str || "").trim()
  if (!s) return s
  return s
    .split(/(\s+|[-_])/)
    .map((part) => {
      if (!part || /^[\s\-_]+$/.test(part)) return part
      return capitalizeFirst(part)
    })
    .join("")
}

/**
 * 长剧本正文自动分段：在句号/问号/叹号后换行，避免整段挤在一起
 */
export function formatScreenplayParagraphs(text) {
  const raw = String(text || "").trim()
  if (!raw) return raw
  if (raw.includes("\n\n")) return raw
  const withBreaks = raw.replace(
    /([。！？!?])\s*(?=[^\s。！？!?\n])/g,
    "$1\n\n"
  )
  return withBreaks
    .split(/\n{3,}/)
    .map((p) => p.trim())
    .filter(Boolean)
    .join("\n\n")
}
