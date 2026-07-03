import { useState, useRef, useCallback, useEffect, useLayoutEffect } from "react"
import { createPortal } from "react-dom"
import { useStore } from "reactflow"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_REF_HOVER } from "../../utils/zIndexLayers"
import CanvasImageQuickPicker from "./CanvasImageQuickPicker"

const sp = (e) => e.stopPropagation()

const PANEL_EST_W = 296
const PANEL_EST_H = 160
const HOVER_CLOSE_DELAY_MS = 150

function clampPanelPos(anchorRect) {
  const margin = 8
  const vw = window.innerWidth
  const vh = window.innerHeight
  let left = anchorRect.left
  let top = anchorRect.bottom

  if (left + PANEL_EST_W > vw - margin) {
    left = Math.max(margin, vw - PANEL_EST_W - margin)
  }
  if (left < margin) left = margin

  if (top + PANEL_EST_H > vh - margin) {
    top = anchorRect.top - PANEL_EST_H
  }
  if (top < margin) top = margin

  return { left, top }
}

/** 鼠标坐标是否在触发器、面板或二者之间的 bridge 区域内 */
function isPointerInsideRef(triggerRef, panelRef, clientX, clientY) {
  const hit = document.elementFromPoint(clientX, clientY)
  if (triggerRef.current?.contains(hit) || panelRef.current?.contains(hit)) {
    return true
  }

  const btn = triggerRef.current
  const panel = panelRef.current

  for (const node of [btn, panel]) {
    if (!node) continue
    const r = node.getBoundingClientRect()
    if (
      clientX >= r.left
      && clientX <= r.right
      && clientY >= r.top
      && clientY <= r.bottom
    ) {
      return true
    }
  }

  if (btn && panel) {
    const br = btn.getBoundingClientRect()
    const pr = panel.getBoundingClientRect()
    const bridgeLeft = Math.min(br.left, pr.left)
    const bridgeRight = Math.max(br.right, pr.right)

    if (pr.top >= br.bottom) {
      if (
        clientX >= bridgeLeft
        && clientX <= bridgeRight
        && clientY >= br.bottom
        && clientY <= pr.top
      ) {
        return true
      }
    } else if (br.top >= pr.bottom) {
      if (
        clientX >= bridgeLeft
        && clientX <= bridgeRight
        && clientY >= pr.bottom
        && clientY <= br.top
      ) {
        return true
      }
    }
  }

  return false
}

/**
 * 悬停/点击展开快捷选图面板（Portal + 跟随锚点视口坐标）
 * 画布/表单内选图一律 click；hover 仅用于非阻塞预览场景。
 */
export default function AddRefHoverPanel({
  buttonClassName = "nb-ref-btn add-ref-btn nodrag nopan",
  buttonContent,
  showUpload = true,
  trigger = "click",
  excludeNodeId = null,
  disabled = false,
  onQuickSelect,
  onCanvasPick,
  onUpload,
  assetEntries = [],
  onAssetPick,
}) {
  const btnRef = useRef(null)
  const panelRef = useRef(null)
  const hoverCloseTimerRef = useRef(null)
  const [showRefPanel, setShowRefPanel] = useState(false)
  const [panelPos, setPanelPos] = useState({ left: 0, top: 0 })
  const viewportTransform = useStore((s) => s.transform)

  const updatePanelPos = useCallback(() => {
    const btn = btnRef.current
    if (!btn) return
    const rect = btn.getBoundingClientRect()
    setPanelPos(clampPanelPos(rect))
  }, [])

  const cancelHoverClose = useCallback(() => {
    if (hoverCloseTimerRef.current) {
      clearTimeout(hoverCloseTimerRef.current)
      hoverCloseTimerRef.current = null
    }
  }, [])

  const scheduleHoverClose = useCallback(() => {
    if (trigger !== "hover") return
    cancelHoverClose()
    hoverCloseTimerRef.current = setTimeout(() => {
      setShowRefPanel(false)
      hoverCloseTimerRef.current = null
    }, HOVER_CLOSE_DELAY_MS)
  }, [trigger, cancelHoverClose])

  useLayoutEffect(() => {
    if (showRefPanel) updatePanelPos()
  }, [showRefPanel, updatePanelPos, viewportTransform])

  useEffect(() => {
    if (!showRefPanel) return undefined
    const onResize = () => updatePanelPos()
    window.addEventListener("resize", onResize)
    window.addEventListener("scroll", onResize, true)
    return () => {
      window.removeEventListener("resize", onResize)
      window.removeEventListener("scroll", onResize, true)
    }
  }, [showRefPanel, updatePanelPos])

  useEffect(() => {
    if (!showRefPanel) return undefined

    const onPointerDown = (e) => {
      const path = e.composedPath?.() || []
      const inside =
        (btnRef.current && path.includes(btnRef.current))
        || (panelRef.current && path.includes(panelRef.current))
        || isPointerInsideRef(btnRef, panelRef, e.clientX, e.clientY)
      if (!inside) setShowRefPanel(false)
    }

    document.addEventListener("pointerdown", onPointerDown, true)
    return () => document.removeEventListener("pointerdown", onPointerDown, true)
  }, [showRefPanel])

  useEffect(() => {
    if (!showRefPanel || trigger !== "hover") return undefined
    const handler = (e) => {
      if (!isPointerInsideRef(btnRef, panelRef, e.clientX, e.clientY)) {
        scheduleHoverClose()
      } else {
        cancelHoverClose()
      }
    }
    const timer = setTimeout(() => {
      document.addEventListener("mousemove", handler)
    }, 100)
    return () => {
      clearTimeout(timer)
      document.removeEventListener("mousemove", handler)
    }
  }, [showRefPanel, trigger, scheduleHoverClose, cancelHoverClose])

  useEffect(() => () => cancelHoverClose(), [cancelHoverClose])

  const openPanel = useCallback(() => {
    updatePanelPos()
    cancelHoverClose()
    setShowRefPanel(true)
  }, [updatePanelPos, cancelHoverClose])

  const closePanel = useCallback(() => {
    cancelHoverClose()
    setShowRefPanel(false)
  }, [cancelHoverClose])

  const handleTriggerEnter = useCallback(() => {
    if (disabled) return
    if (trigger === "hover") openPanel()
  }, [disabled, trigger, openPanel])

  const handleTriggerLeave = useCallback(() => {
    if (trigger === "hover") scheduleHoverClose()
  }, [trigger, scheduleHoverClose])

  const handleTriggerClick = useCallback(
    (e) => {
      sp(e)
      if (disabled) return
      if (trigger === "click") {
        setShowRefPanel((v) => {
          if (!v) updatePanelPos()
          return !v
        })
      }
    },
    [disabled, trigger, updatePanelPos]
  )

  const handlePanelEnter = useCallback(() => {
    if (trigger === "hover") {
      cancelHoverClose()
      openPanel()
    }
  }, [trigger, cancelHoverClose, openPanel])

  const handlePanelLeave = useCallback(() => {
    if (trigger === "hover") scheduleHoverClose()
  }, [trigger, scheduleHoverClose])

  const handleQuickSelect = useCallback(
    (item) => {
      closePanel()
      onQuickSelect?.(item)
    },
    [closePanel, onQuickSelect]
  )

  const handleBrowseCanvas = useCallback(() => {
    closePanel()
    onCanvasPick?.()
  }, [closePanel, onCanvasPick])

  const handleUpload = useCallback(
    (file) => {
      closePanel()
      onUpload?.(file)
    },
    [closePanel, onUpload]
  )

  const handleAssetPick = useCallback(
    (asset) => {
      closePanel()
      onAssetPick?.(asset)
    },
    [closePanel, onAssetPick]
  )

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className={`${buttonClassName}${disabled ? " add-ref-btn--disabled" : ""}`}
        disabled={disabled}
        onPointerDown={sp}
        onMouseEnter={handleTriggerEnter}
        onMouseLeave={handleTriggerLeave}
        onClick={handleTriggerClick}
      >
        {buttonContent}
      </button>
      {showRefPanel &&
        createPortal(
          <div
            ref={panelRef}
            className="add-ref-panel-anchor nodrag nopan"
            style={{
              position: "fixed",
              left: panelPos.left,
              top: panelPos.top,
              zIndex: Z_REF_HOVER,
            }}
            onPointerDown={sp}
            onMouseEnter={handlePanelEnter}
            onMouseLeave={handlePanelLeave}
          >
            <CanvasImageQuickPicker
              excludeNodeId={excludeNodeId}
              showUpload={showUpload}
              onSelect={handleQuickSelect}
              onBrowseCanvas={handleBrowseCanvas}
              onUpload={showUpload ? handleUpload : undefined}
              assetEntries={assetEntries}
              onAssetPick={onAssetPick ? handleAssetPick : undefined}
            />
          </div>,
          getThemePortalRoot()
        )}
    </>
  )
}

/**
 * 任意 DOM 锚点上的点击选图（首尾帧槽位等）
 */
export function RefPickAnchor({
  className = "",
  children,
  showUpload = false,
  excludeNodeId = null,
  onQuickSelect,
  onCanvasPick,
  onUpload,
  assetEntries = [],
  onAssetPick,
}) {
  const anchorRef = useRef(null)
  const panelRef = useRef(null)
  const [showRefPanel, setShowRefPanel] = useState(false)
  const [panelPos, setPanelPos] = useState({ left: 0, top: 0 })
  const viewportTransform = useStore((s) => s.transform)

  const updatePanelPos = useCallback(() => {
    const el = anchorRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setPanelPos(clampPanelPos(rect))
  }, [])

  useLayoutEffect(() => {
    if (showRefPanel) updatePanelPos()
  }, [showRefPanel, updatePanelPos, viewportTransform])


  useEffect(() => {
    if (!showRefPanel) return undefined
    const onPointerDown = (e) => {
      const path = e.composedPath?.() || []
      const inside =
        (anchorRef.current && path.includes(anchorRef.current))
        || (panelRef.current && path.includes(panelRef.current))
      if (!inside) setShowRefPanel(false)
    }
    document.addEventListener("pointerdown", onPointerDown, true)
    return () => document.removeEventListener("pointerdown", onPointerDown, true)
  }, [showRefPanel])

  const togglePanel = useCallback(
    (e) => {
      sp(e)
      setShowRefPanel((v) => {
        if (!v) updatePanelPos()
        return !v
      })
    },
    [updatePanelPos]
  )

  const closePanel = useCallback(() => setShowRefPanel(false), [])

  const handleUpload = useCallback(
    (file) => {
      closePanel()
      onUpload?.(file)
    },
    [closePanel, onUpload]
  )

  const handleAssetPick = useCallback(
    (asset) => {
      closePanel()
      onAssetPick?.(asset)
    },
    [closePanel, onAssetPick]
  )

  return (
    <>
      <div
        ref={anchorRef}
        className={className}
        onClick={togglePanel}
        onPointerDown={sp}
        role="presentation"
      >
        {children}
      </div>
      {showRefPanel &&
        createPortal(
          <div
            ref={panelRef}
            className="add-ref-panel-anchor nodrag nopan"
            style={{
              position: "fixed",
              left: panelPos.left,
              top: panelPos.top,
              zIndex: Z_REF_HOVER,
            }}
            onPointerDown={sp}
          >
            <CanvasImageQuickPicker
              excludeNodeId={excludeNodeId}
              showUpload={showUpload}
              onSelect={(item) => {
                closePanel()
                onQuickSelect?.(item)
              }}
              onBrowseCanvas={() => {
                closePanel()
                onCanvasPick?.()
              }}
              onUpload={showUpload ? handleUpload : undefined}
              assetEntries={assetEntries}
              onAssetPick={onAssetPick ? handleAssetPick : undefined}
            />
          </div>,
          getThemePortalRoot()
        )}
    </>
  )
}
