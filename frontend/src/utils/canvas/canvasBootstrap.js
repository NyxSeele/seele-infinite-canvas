const BOOTSTRAP_PREFIX = "canvas-bootstrap:"

export function setCanvasBootstrap(projectId, payload) {
  if (!projectId || !payload) return
  try {
    sessionStorage.setItem(`${BOOTSTRAP_PREFIX}${projectId}`, JSON.stringify(payload))
  } catch {
    /* ignore */
  }
}

export function consumeCanvasBootstrap(projectId) {
  if (!projectId) return null
  const key = `${BOOTSTRAP_PREFIX}${projectId}`
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    sessionStorage.removeItem(key)
    return JSON.parse(raw)
  } catch {
    sessionStorage.removeItem(key)
    return null
  }
}

export function buildScriptCanvasData(content, title = "我的剧本") {
  const text = String(content || "").trim()
  return {
    nodes: [
      {
        id: `text-note-${Date.now()}`,
        type: "text-note",
        position: { x: 120, y: 160 },
        zIndex: 1,
        data: {
          content: text,
          textMode: "screenplay",
          label: "剧本",
          zIndex: 1,
        },
      },
    ],
    edges: [],
    project_name: title.slice(0, 64) || "我的剧本",
  }
}
