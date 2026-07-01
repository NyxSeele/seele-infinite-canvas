import { useCallback, useState, useEffect } from "react"
import { useReactFlow, useStore } from "reactflow"
import { useCanvasStore } from "../../stores"
import { useLocale } from "../../utils/locale"

const IconRecenter = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
    <rect x="2.5" y="3" width="10" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
    <path d="M7.5 6.2v2.8M7.5 6.2L6 7.7M7.5 6.2l1.5 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="7.5" cy="7.5" r="2.8" stroke="currentColor" strokeWidth="1" strokeDasharray="1.5 1.5" opacity="0.55" />
  </svg>
)

const IconOrganize = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
    <rect x="2" y="2.5" width="4.5" height="4" rx="0.8" stroke="currentColor" strokeWidth="1.2" />
    <rect x="8.5" y="2.5" width="4.5" height="4" rx="0.8" stroke="currentColor" strokeWidth="1.2" />
    <rect x="2" y="8.5" width="4.5" height="4" rx="0.8" stroke="currentColor" strokeWidth="1.2" />
    <rect x="8.5" y="8.5" width="4.5" height="4" rx="0.8" stroke="currentColor" strokeWidth="1.2" />
    <path d="M6.5 4.5h2M6.5 10.5h2M4.5 6.5v2M10.5 6.5v2" stroke="currentColor" strokeWidth="1" strokeLinecap="round" opacity="0.7" />
  </svg>
)

const IconMinimap = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
    <rect x="2" y="2.5" width="11" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
    <rect x="4.5" y="5" width="4.5" height="3.5" rx="0.5" stroke="currentColor" strokeWidth="1.2" fill="currentColor" fillOpacity="0.15" />
    <path d="M2 5.5h11" stroke="currentColor" strokeWidth="0.8" opacity="0.35" />
    <path d="M2 9h11" stroke="currentColor" strokeWidth="0.8" opacity="0.35" />
  </svg>
)

const IconSnapGrid = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
    <path d="M2.5 5.5h10M2.5 9.5h10M5.5 2.5v10M9.5 2.5v10" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
  </svg>
)

export default function CanvasBottomToolbar({ onRecenterViewport, onOrganizeCanvas, readOnly = false }) {
  const { zoomTo } = useReactFlow()
  const viewportZoom = useStore((s) => s.transform[2])
  const snapToGrid = useCanvasStore((s) => s.snapToGrid)
  const toggleSnapToGrid = useCanvasStore((s) => s.toggleSnapToGrid)
  const minimapOpen = useCanvasStore((s) => s.minimapOpen)
  const toggleMinimap = useCanvasStore((s) => s.toggleMinimap)
  const { t } = useLocale()

  const [sliderVal, setSliderVal] = useState(Math.round((viewportZoom || 1) * 100))
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    if (!dragging) setSliderVal(Math.round(viewportZoom * 100))
  }, [viewportZoom, dragging])

  const applyZoom = useCallback((val) => {
    const clamped = Math.min(250, Math.max(15, val))
    setSliderVal(clamped)
    zoomTo(clamped / 100, { duration: 120 })
  }, [zoomTo])

  const handleRecenter = useCallback(() => {
    onRecenterViewport?.()
  }, [onRecenterViewport])

  const handleOrganize = useCallback(() => {
    if (readOnly) return
    onOrganizeCanvas?.()
  }, [readOnly, onOrganizeCanvas])

  return (
    <div
      className="cbt-bar nodrag nopan"
      onPointerDown={(e) => e.stopPropagation()}
    >
      <button
        className="cbt-btn"
        title={t("canvas.bottom.recenter")}
        onClick={handleRecenter}
      >
        <IconRecenter />
      </button>

      <button
        className="cbt-btn"
        title={t("canvas.bottom.organize")}
        disabled={readOnly}
        onClick={handleOrganize}
      >
        <IconOrganize />
      </button>

      <button
        className={`cbt-btn${minimapOpen ? " cbt-btn--active" : ""}`}
        title={minimapOpen ? t("canvas.bottom.minimapHide") : t("canvas.bottom.minimapShow")}
        onClick={toggleMinimap}
      >
        <IconMinimap />
      </button>

      <button
        className={`cbt-btn${snapToGrid ? " cbt-btn--active" : ""}`}
        title={snapToGrid ? t("canvas.bottom.snapOff") : t("canvas.bottom.snapOn")}
        onClick={toggleSnapToGrid}
        disabled={readOnly}
      >
        <IconSnapGrid />
      </button>

      <div className="cbt-sep" />

      <button
        className="cbt-zoom-step"
        onClick={() => applyZoom(sliderVal - 10)}
        title={t("canvas.bottom.zoomOut")}
      >−</button>

      <input
        type="range"
        min={15}
        max={250}
        value={sliderVal}
        className="cbt-slider nodrag nowheel"
        onMouseDown={() => setDragging(true)}
        onMouseUp={() => setDragging(false)}
        onTouchStart={() => setDragging(true)}
        onTouchEnd={() => setDragging(false)}
        onChange={(e) => applyZoom(Number(e.target.value))}
        title={t("canvas.bottom.zoomLevel", { val: sliderVal })}
      />

      <button
        className="cbt-zoom-step"
        onClick={() => applyZoom(sliderVal + 10)}
        title={t("canvas.bottom.zoomIn")}
      >+</button>

      <span
        className="cbt-zoom-pct"
        onClick={() => applyZoom(100)}
        title={t("canvas.bottom.zoomReset")}
      >{sliderVal}%</span>
    </div>
  )
}
