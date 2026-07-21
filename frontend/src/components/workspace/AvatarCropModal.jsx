import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import { useCanvasStore } from "../../stores"
import { useLocale } from "../../utils/locale"
import { useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import { Z_AVATAR_CROP } from "../../utils/zIndexLayers"
import "../../pages/Canvas.css"
import "./AvatarCropModal.css"

const VIEW = 300
const OUTPUT = 512
const MIN_SCALE = 1
const MAX_SCALE = 4

function getBaseScale(naturalW, naturalH) {
  return Math.max(VIEW / naturalW, VIEW / naturalH)
}

function getDrawSize(naturalW, naturalH, scale) {
  const baseScale = getBaseScale(naturalW, naturalH)
  return {
    baseScale,
    drawW: naturalW * baseScale * scale,
    drawH: naturalH * baseScale * scale,
  }
}

function clampOffset(x, y, drawW, drawH) {
  let nextX = x
  let nextY = y
  if (drawW > VIEW) {
    const maxX = (drawW - VIEW) / 2
    nextX = Math.max(-maxX, Math.min(maxX, nextX))
  } else {
    nextX = 0
  }
  if (drawH > VIEW) {
    const maxY = (drawH - VIEW) / 2
    nextY = Math.max(-maxY, Math.min(maxY, nextY))
  } else {
    nextY = 0
  }
  return { x: nextX, y: nextY }
}

export default function AvatarCropModal({ open, imageSrc, onConfirm, onCancel }) {
  const { t } = useLocale()
  const theme = useCanvasStore((s) => s.theme)
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [ready, setReady] = useState(false)

  const imageRef = useRef(null)
  const naturalRef = useRef({ w: 0, h: 0 })
  const canvasRef = useRef(null)
  const dragLayerRef = useRef(null)
  const dragRef = useRef(null)
  const offsetRef = useRef(offset)
  const scaleRef = useRef(scale)
  const { mounted, closing } = useOverlayMount(open && Boolean(imageSrc))

  offsetRef.current = offset
  scaleRef.current = scale

  const paint = useCallback(() => {
    const canvas = canvasRef.current
    const img = imageRef.current
    const ns = naturalRef.current
    if (!canvas || !img || ns.w <= 0) return

    const dpr = window.devicePixelRatio || 1
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const { drawW, drawH } = getDrawSize(ns.w, ns.h, scaleRef.current)
    const drawX = (VIEW - drawW) / 2 + offsetRef.current.x
    const drawY = (VIEW - drawH) / 2 + offsetRef.current.y

    canvas.width = VIEW * dpr
    canvas.height = VIEW * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.fillStyle = "#111"
    ctx.fillRect(0, 0, VIEW, VIEW)
    ctx.drawImage(img, drawX, drawY, drawW, drawH)
  }, [])

  useEffect(() => {
    if (!open || !imageSrc) return undefined
    setScale(1)
    setOffset({ x: 0, y: 0 })
    setReady(false)
    imageRef.current = null
    naturalRef.current = { w: 0, h: 0 }

    const img = new Image()
    const onReady = () => {
      const w = img.naturalWidth || 1
      const h = img.naturalHeight || 1
      imageRef.current = img
      naturalRef.current = { w, h }
      const { drawW, drawH } = getDrawSize(w, h, 1)
      const nextOffset = clampOffset(0, 0, drawW, drawH)
      offsetRef.current = nextOffset
      scaleRef.current = 1
      setOffset(nextOffset)
      setScale(1)
      setReady(true)
    }
    img.onload = onReady
    img.onerror = () => setReady(false)
    img.src = imageSrc
    if (img.complete) onReady()

    return () => {
      img.onload = null
      img.onerror = null
    }
  }, [open, imageSrc])

  useEffect(() => {
    if (!ready) return
    paint()
  }, [ready, scale, offset, paint])

  const applyOffset = useCallback((x, y, drawW, drawH) => {
    const next = clampOffset(x, y, drawW, drawH)
    offsetRef.current = next
    setOffset(next)
    paint()
  }, [paint])

  const applyScale = useCallback((nextScale) => {
    const ns = naturalRef.current
    const clamped = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale))
    if (ns.w <= 0) {
      scaleRef.current = clamped
      setScale(clamped)
      return
    }
    const { drawW, drawH } = getDrawSize(ns.w, ns.h, clamped)
    scaleRef.current = clamped
    setScale(clamped)
    const next = clampOffset(offsetRef.current.x, offsetRef.current.y, drawW, drawH)
    offsetRef.current = next
    setOffset(next)
    paint()
  }, [paint])

  const handlePointerDown = (e) => {
    if (!ready) return
    e.preventDefault()
    e.stopPropagation()
    e.currentTarget.setPointerCapture(e.pointerId)
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      baseX: offsetRef.current.x,
      baseY: offsetRef.current.y,
    }
  }

  const handlePointerMove = useCallback((e) => {
    if (!dragRef.current || dragRef.current.pointerId !== e.pointerId) return
    const ns = naturalRef.current
    const { drawW, drawH } = getDrawSize(ns.w, ns.h, scaleRef.current)
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    applyOffset(
      dragRef.current.baseX + dx,
      dragRef.current.baseY + dy,
      drawW,
      drawH,
    )
  }, [applyOffset])

  const handlePointerUp = useCallback((e) => {
    if (!dragRef.current || dragRef.current.pointerId !== e.pointerId) return
    dragRef.current = null
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      /* ignore */
    }
  }, [])

  const handleWheel = useCallback((e) => {
    if (!ready) return
    e.preventDefault()
    e.stopPropagation()
    const factor = e.deltaY > 0 ? 0.92 : 1.08
    applyScale(scaleRef.current * factor)
  }, [applyScale, ready])

  useEffect(() => {
    const el = dragLayerRef.current
    if (!open || !el) return undefined
    el.addEventListener("wheel", handleWheel, { passive: false })
    return () => el.removeEventListener("wheel", handleWheel)
  }, [open, handleWheel])

  const handleConfirm = () => {
    const ns = naturalRef.current
    const img = imageRef.current
    if (!img || ns.w <= 0) return
    const sc = scaleRef.current
    const off = offsetRef.current
    const { drawW, drawH } = getDrawSize(ns.w, ns.h, sc)
    const drawX = (VIEW - drawW) / 2 + off.x
    const drawY = (VIEW - drawH) / 2 + off.y
    const ratio = OUTPUT / VIEW

    const canvas = document.createElement("canvas")
    canvas.width = OUTPUT
    canvas.height = OUTPUT
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    ctx.fillStyle = "#111"
    ctx.fillRect(0, 0, OUTPUT, OUTPUT)
    ctx.beginPath()
    ctx.arc(OUTPUT / 2, OUTPUT / 2, OUTPUT / 2, 0, Math.PI * 2)
    ctx.closePath()
    ctx.clip()
    ctx.drawImage(img, drawX * ratio, drawY * ratio, drawW * ratio, drawH * ratio)
    onConfirm?.(canvas.toDataURL("image/jpeg", 0.92))
  }

  if (!mounted || !imageSrc) return null

  const overlayClasses = overlayClassNames({
    mounted,
    closing,
    open: open && Boolean(imageSrc),
    base: `acm-backdrop ws-overlay-root rf-page--${theme}`,
    enterClass: open && !closing ? "motion-modal-overlay-in" : "",
    exitClass: closing ? "motion-modal-overlay-out" : "",
  })

  const modalClasses = overlayClassNames({
    mounted,
    closing,
    open: open && Boolean(imageSrc),
    base: "acm-modal",
    enterClass: open && !closing ? "motion-modal-in" : "",
    exitClass: closing ? "motion-modal-out" : "",
  })

  return createPortal(
    <div
      className={overlayClasses}
      style={{ zIndex: Z_AVATAR_CROP }}
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onCancel?.()
      }}
    >
      <div className={modalClasses} onPointerDown={(e) => e.stopPropagation()}>
        <header className="acm-head">
          <h3>{t("profile.cropAvatar")}</h3>
          <button type="button" className="acm-close" onClick={onCancel} aria-label={t("profile.close")}>×</button>
        </header>
        <div className="acm-viewport">
          <canvas ref={canvasRef} className="acm-canvas" width={VIEW} height={VIEW} />
          {!ready && <div className="acm-loading" aria-hidden />}
          <div className="acm-mask" aria-hidden />
          <div
            ref={dragLayerRef}
            className="acm-drag-layer"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
          />
        </div>
        <label className="acm-zoom">
          <span>{t("profile.cropZoom")}</span>
          <input
            type="range"
            min={MIN_SCALE}
            max={MAX_SCALE}
            step="0.01"
            value={scale}
            onChange={(e) => applyScale(Number(e.target.value))}
          />
        </label>
        <p className="acm-hint">{t("profile.cropHint")}</p>
        <footer className="acm-foot">
          <button type="button" className="acm-btn acm-btn--ghost" onClick={onCancel}>{t("profile.cropCancel")}</button>
          <button type="button" className="acm-btn acm-btn--primary" onClick={handleConfirm} disabled={!ready}>
            {t("profile.cropConfirm")}
          </button>
        </footer>
      </div>
    </div>,
    getThemePortalRoot()
  )
}
