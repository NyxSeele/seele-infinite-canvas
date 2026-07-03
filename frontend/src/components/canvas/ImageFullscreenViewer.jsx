import { useState, useEffect, useRef, useCallback } from "react"
import { createPortal } from "react-dom"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import "./GenerationCardNode.css"

const MIN_SCALE = 0.5
const MAX_SCALE = 6

export default function ImageFullscreenViewer({ src, onClose }) {
  const [imgPos, setImgPos] = useState({ x: 0, y: 0 })
  const [scale, setScale] = useState(1)
  const [dragging, setDragging] = useState(false)
  const dragStart = useRef({ mx: 0, my: 0, ix: 0, iy: 0 })
  const wrapperRef = useRef(null)

  const resetView = useCallback(() => {
    setImgPos({ x: 0, y: 0 })
    setScale(1)
  }, [])

  const closeFullscreen = useCallback(() => {
    resetView()
    setDragging(false)
    onClose()
  }, [onClose, resetView])

  useEffect(() => {
    if (!src) return
    document.body.classList.add("image-fullscreen-open")
    const onKey = (e) => {
      if (e.key === "Escape") closeFullscreen()
    }
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.classList.remove("image-fullscreen-open")
    }
  }, [src, closeFullscreen])

  useEffect(() => {
    if (!dragging) return
    const onMove = (e) => {
      e.stopPropagation()
      setImgPos({
        x: dragStart.current.ix + e.clientX - dragStart.current.mx,
        y: dragStart.current.iy + e.clientY - dragStart.current.my,
      })
    }
    const onUp = (e) => {
      e.stopPropagation()
      setDragging(false)
    }
    window.addEventListener("mousemove", onMove)
    window.addEventListener("mouseup", onUp)
    return () => {
      window.removeEventListener("mousemove", onMove)
      window.removeEventListener("mouseup", onUp)
    }
  }, [dragging])

  const handleWheel = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()

    setScale((prevScale) => {
      const nextScale = Math.min(
        MAX_SCALE,
        Math.max(MIN_SCALE, prevScale - e.deltaY * 0.001)
      )
      if (nextScale === prevScale) return prevScale

      const ratio = nextScale / prevScale
      const dx = e.clientX - window.innerWidth / 2
      const dy = e.clientY - window.innerHeight / 2

      setImgPos((prev) => ({
        x: prev.x - (dx - prev.x) * (ratio - 1),
        y: prev.y - (dy - prev.y) * (ratio - 1),
      }))

      return nextScale
    })
  }, [])

  useEffect(() => {
    if (!src) return
    const el = wrapperRef.current
    if (!el) return
    el.addEventListener("wheel", handleWheel, { passive: false })
    return () => el.removeEventListener("wheel", handleWheel)
  }, [src, handleWheel])

  if (!src) return null

  const wrapperTransform = `translate(calc(-50% + ${imgPos.x}px), calc(-50% + ${imgPos.y}px)) scale(${scale})`

  return createPortal(
    <div className="image-viewer" onMouseDown={(e) => e.stopPropagation()}>
      <div
        ref={wrapperRef}
        className="image-viewer__wrapper"
        style={{
          transform: wrapperTransform,
          transition: dragging ? "none" : "transform 0.08s ease-out",
          cursor: dragging ? "grabbing" : "grab",
        }}
        onMouseDown={(e) => {
          if (e.button !== 0) return
          e.stopPropagation()
          setDragging(true)
          dragStart.current = {
            mx: e.clientX,
            my: e.clientY,
            ix: imgPos.x,
            iy: imgPos.y,
          }
        }}
      >
        <img
          src={src}
          alt=""
          draggable={false}
          onDoubleClick={(e) => {
            e.stopPropagation()
            resetView()
          }}
        />
        <button
          type="button"
          className="image-viewer__close nodrag nopan"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation()
            closeFullscreen()
          }}
        >
          ×
        </button>
      </div>
    </div>,
    getThemePortalRoot()
  )
}
