import { useCallback, useEffect } from "react"
import { useCanvasStore } from "../../stores"

const DRAG_THRESHOLD = 8

/**
 * 从飞出面板按住拖动到画布放置节点（比 HTML5 DnD 更可靠）
 */
export function useCanvasDragPlace({
  createNode,
  setSelectedNodeId,
  raiseNodeToFront,
}) {
  const session = useCanvasStore((s) => s.dragPlaceSession)
  const setDragPlaceSession = useCanvasStore((s) => s.setDragPlaceSession)

  const placeOnCanvas = useCallback(
    (payload, clientX, clientY) => {
      const screenPos = { x: clientX, y: clientY }
      let id
      const cardLabel = payload.title || payload.name || ""
      if (payload.kind === "video") {
        id = createNode("video-gen", screenPos, {
          prompt: payload.prompt || "",
          label: cardLabel || "Video",
          status: "completed",
          videoUrl: payload.mediaUrl,
          completedAt: Date.now(),
        })
      } else {
        id = createNode("image-gen", screenPos, {
          prompt: payload.prompt || "",
          label: cardLabel || "Image",
          status: "completed",
          uploadedImage: payload.mediaUrl,
          imageSource: payload.source || "flyout",
          completedAt: Date.now(),
        })
      }
      setSelectedNodeId(id)
      raiseNodeToFront(id)
    },
    [createNode, setSelectedNodeId, raiseNodeToFront]
  )

  const beginDragPlace = useCallback(
    (payload, e) => {
      if (!payload?.mediaUrl) return
      e.preventDefault()
      e.stopPropagation()
      setDragPlaceSession({
        kind: payload.kind || "image",
        mediaUrl: payload.mediaUrl,
        title: payload.title || payload.name || "",
        prompt: payload.prompt || "",
        name: payload.name || "",
        previewUrl: payload.previewUrl || payload.mediaUrl,
        source: payload.source || "flyout",
        x: e.clientX,
        y: e.clientY,
        active: true,
      })
    },
    [setDragPlaceSession]
  )

  const getCardPointerHandlers = useCallback(
    (payload) => ({
      onPointerDown(e) {
        if (e.button !== 0 || !payload?.mediaUrl) return
        e.stopPropagation()
        const sx = e.clientX
        const sy = e.clientY
        let started = false
        const onMove = (ev) => {
          if (started) return
          if (Math.hypot(ev.clientX - sx, ev.clientY - sy) >= DRAG_THRESHOLD) {
            started = true
            beginDragPlace(payload, ev)
            cleanup()
          }
        }
        const onUp = () => cleanup()
        const cleanup = () => {
          window.removeEventListener("pointermove", onMove)
          window.removeEventListener("pointerup", onUp)
        }
        window.addEventListener("pointermove", onMove)
        window.addEventListener("pointerup", onUp)
      },
      onDoubleClick(e) {
        e.stopPropagation()
        e.preventDefault()
      },
    }),
    [beginDragPlace]
  )

  useEffect(() => {
    if (!session?.active) return undefined

    const onMove = (e) => {
      const cur = useCanvasStore.getState().dragPlaceSession
      if (!cur?.active) return
      setDragPlaceSession({ ...cur, x: e.clientX, y: e.clientY })
    }

    const onUp = (e) => {
      const s = useCanvasStore.getState().dragPlaceSession
      if (!s?.active) return
      const el = document.elementFromPoint(e.clientX, e.clientY)
      const blocked = el?.closest(
        ".ghf-flyout, .alf-flyout, .clt-toolbar, .clt-add-menu, .nb-banner"
      )
      const onCanvas = el?.closest(".react-flow__pane, .rf-page")
      if (!blocked && onCanvas) {
        placeOnCanvas(s, e.clientX, e.clientY)
      }
      setDragPlaceSession(null)
    }

    const onKey = (ev) => {
      if (ev.key === "Escape") setDragPlaceSession(null)
    }

    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
    window.addEventListener("keydown", onKey)
    return () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
      window.removeEventListener("keydown", onKey)
    }
  }, [session?.active, placeOnCanvas, setDragPlaceSession])

  return { session, getCardPointerHandlers }
}
