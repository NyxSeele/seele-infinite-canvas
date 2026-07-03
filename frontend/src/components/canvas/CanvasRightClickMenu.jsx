import { useState, useEffect, useRef, useCallback } from "react"
import { LineIcon } from "../icons/LineIcons"
import { useLocale } from "../../utils/locale"
import { MENU_SUBMENU_CLOSE_MS } from "../../utils/menuFlyoutTiming"
import { MOTION_EXIT_MS, overlayClassNames } from "../../hooks/useFlyoutMount"

const NODE_ITEM_KEYS = [
  { type: "image-gen", icon: "sparkle", labelKey: "canvas.menu.imageGen" },
  { type: "video-gen", icon: "video", labelKey: "canvas.menu.videoGen" },
  { type: "text-note", icon: "text", labelKey: "canvas.menu.textNote" },
  { type: "script-table", icon: "script", labelKey: "canvas.menu.scriptTable" },
]

export default function CanvasRightClickMenu({ x, y, onCreateNode, onUploadImage, onUndo, onRedo, onPaste, onClose }) {
  const { t } = useLocale()
  const ref = useRef(null)
  const [addNodeHover, setAddNodeHover] = useState(false)
  const [closing, setClosing] = useState(false)
  const submenuTimerRef = useRef(null)

  const requestClose = useCallback(() => {
    if (closing) return
    setClosing(true)
    setTimeout(() => onClose?.(), MOTION_EXIT_MS)
  }, [closing, onClose])

  const clearSubmenuTimer = useCallback(() => {
    if (submenuTimerRef.current) clearTimeout(submenuTimerRef.current)
  }, [])

  const openSubmenu = useCallback(() => {
    clearSubmenuTimer()
    setAddNodeHover(true)
  }, [clearSubmenuTimer])

  const scheduleSubmenuClose = useCallback(() => {
    clearSubmenuTimer()
    submenuTimerRef.current = setTimeout(() => {
      submenuTimerRef.current = null
      setAddNodeHover(false)
    }, MENU_SUBMENU_CLOSE_MS)
  }, [clearSubmenuTimer])

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) requestClose()
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [requestClose])

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") requestClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [requestClose])

  useEffect(() => () => clearSubmenuTimer(), [clearSubmenuTimer])

  const pos = (() => {
    const menuW = 220, menuH = 200
    let left = x, top = y
    if (left + menuW > window.innerWidth - 8) left = window.innerWidth - menuW - 8
    if (top + menuH > window.innerHeight - 8) top = window.innerHeight - menuH - 8
    return { left: Math.max(8, left), top: Math.max(8, top) }
  })()

  const menuClasses = overlayClassNames({
    mounted: true,
    closing,
    open: !closing,
    base: "tl-context-menu",
    enterClass: !closing ? "motion-popover-in" : "",
    exitClass: closing ? "motion-popover-out" : "",
  })

  return (
    <div
      ref={ref}
      className={menuClasses}
      style={{ left: pos.left, top: pos.top }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <button className="tl-context-item" onClick={() => { requestClose(); onUploadImage?.() }}>
        <span className="tl-context-icon"><LineIcon name="upload" size={16} /></span>
        <span>{t("canvas.menu.uploadImage")}</span>
      </button>

      <div
        className="tl-context-item tl-context-submenu-trigger"
        onMouseEnter={openSubmenu}
        onMouseLeave={scheduleSubmenuClose}
      >
        <span className="tl-context-icon"><LineIcon name="plus" size={16} /></span>
        <span>{t("canvas.menu.addNode")}</span>
        <span className="tl-context-arrow">›</span>

        {addNodeHover && (
          <div
            className="tl-context-submenu"
            onMouseEnter={openSubmenu}
            onMouseLeave={scheduleSubmenuClose}
          >
            {NODE_ITEM_KEYS.map((item) => (
              <button
                key={item.type}
                className="tl-context-item"
                onClick={() => { onCreateNode(item.type); requestClose() }}
              >
                <span className="tl-context-icon"><LineIcon name={item.icon} size={16} /></span>
                <span>{t(item.labelKey)}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="tl-context-divider" />

      <button className="tl-context-item" onClick={() => { onUndo(); requestClose() }}>
        <span className="tl-context-icon"><LineIcon name="undo" size={16} /></span>
        <span>{t("canvas.menu.undo")}</span>
      </button>
      <button className="tl-context-item" onClick={() => { onRedo(); requestClose() }}>
        <span className="tl-context-icon"><LineIcon name="redo" size={16} /></span>
        <span>{t("canvas.menu.redo")}</span>
      </button>
      <button className="tl-context-item" onClick={() => { onPaste(); requestClose() }}>
        <span className="tl-context-icon"><LineIcon name="paste" size={16} /></span>
        <span>{t("canvas.menu.paste")}</span>
      </button>
    </div>
  )
}
