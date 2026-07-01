const STORAGE_KEY = "canvas-prompt-expanded"

const DEFAULT = { text: false, image: false, video: false }

function readPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT }
    const parsed = JSON.parse(raw)
    return {
      text: Boolean(parsed.text),
      image: Boolean(parsed.image),
      video: Boolean(parsed.video),
    }
  } catch {
    return { ...DEFAULT }
  }
}

export function getPromptExpanded(variant) {
  if (!variant || !(variant in DEFAULT)) return false
  return readPrefs()[variant]
}

export function setPromptExpanded(variant, expanded) {
  if (!variant || !(variant in DEFAULT)) return
  const next = { ...readPrefs(), [variant]: Boolean(expanded) }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    /* ignore */
  }
}
