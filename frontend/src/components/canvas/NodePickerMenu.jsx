import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { MOTION_EXIT_MS, useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import { LineIcon } from "../icons/LineIcons"
import { useLocale } from "../../utils/locale"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_NODE_DOTS_MENU } from "../../utils/zIndexLayers"

function usePickerGroups(fromEdge, sourceNodeType) {
  const { t } = useLocale()

  return useMemo(() => {
    const ALL_GROUPS = [
      {
        group: t("canvas.menu.addNode"),
        items: [
          { type: "image-gen", action: "create-image", icon: "sparkle", label: t("canvas.menu.imageGen"), sub: t("canvas.menu.subImageStyle") },
          { type: "video-gen", action: "create-video", icon: "video", label: t("canvas.menu.videoGen"), sub: t("canvas.menu.subVideoStyle") },
          { type: "short-video-factory", action: "create-short-video", icon: "video", label: t("canvas.menu.shortVideoFactory"), sub: t("canvas.menu.subShortVideoFactory") },
          { type: "text-note", action: "create-text", icon: "text", label: t("canvas.menu.textNote"), sub: t("canvas.menu.subTextNote") },
          { type: "script-table", action: "create-script-table", icon: "script", label: t("canvas.menu.scriptTable"), sub: t("canvas.menu.subScriptTable") },
          { type: "character-card", action: "create-character-card", icon: "text", label: t("canvas.menu.characterCard"), sub: t("canvas.menu.subCharacterCard") },
          { type: "import", action: "import-document", icon: "upload", label: t("canvas.menu.importDocument"), sub: t("canvas.menu.subImportDocument") },
        ],
      },
    ]

    if (!fromEdge) return ALL_GROUPS

    switch (sourceNodeType) {
      case "text-note":
        return [{
          group: t("canvas.menu.refGenerate"),
          items: [
            { type: "image-gen", action: "create-image", icon: "sparkle", label: t("canvas.menu.imageGen"), sub: t("canvas.menu.subFromTextPrompt") },
            { type: "video-gen", action: "create-video", icon: "video", label: t("canvas.menu.videoGen"), sub: t("canvas.menu.subFromTextPrompt") },
          ],
        }]
      case "script-table":
        return [{
          group: t("canvas.menu.refGenerate"),
          items: [
            { type: "image-gen", action: "create-image", icon: "sparkle", label: t("canvas.menu.imageGen"), sub: t("canvas.menu.subFromScriptPrompt") },
            { type: "text-note", action: "create-text", icon: "text", label: t("canvas.menu.addCaption"), sub: null },
          ],
        }]
      case "image-gen":
        return [{
          group: t("canvas.menu.refGenerate"),
          items: [
            { type: "video-gen", action: "create-video-from-image", icon: "video", label: t("canvas.menu.img2video"), sub: t("canvas.menu.subAsFirstFrame") },
            { type: "image-gen", action: "create-image-from-image", icon: "sparkle", label: t("canvas.menu.img2img"), sub: t("canvas.menu.subAsRefImage") },
            { type: "text-note", action: "create-text", icon: "text", label: t("canvas.menu.addCaption"), sub: null },
          ],
        }]
      case "video-gen":
        return [{
          group: t("canvas.menu.refGenerate"),
          items: [
            { type: "text-note", action: "create-text", icon: "text", label: t("canvas.menu.addCaption"), sub: null },
            { type: "video-gen", action: "duplicate-video", icon: "video", label: t("canvas.menu.copyAsVideo"), sub: null },
          ],
        }]
      default:
        return [{
          group: t("canvas.menu.refGenerate"),
          items: [
            { type: "image-gen", action: "create-image", icon: "sparkle", label: t("canvas.menu.imageGen"), sub: null },
            { type: "video-gen", action: "create-video", icon: "video", label: t("canvas.menu.videoGen"), sub: null },
            { type: "text-note", action: "create-text", icon: "text", label: t("canvas.menu.textNote"), sub: null },
          ],
        }]
    }
  }, [fromEdge, sourceNodeType, t])
}

export default function NodePickerMenu({ x, y, fromEdge = false, sourceNodeType = null, onSelect, onClose }) {
  const ref = useRef(null)
  const [activeIdx, setActiveIdx] = useState(0)
  const [closing, setClosing] = useState(false)
  const groups = usePickerGroups(fromEdge, sourceNodeType)
  const allItems = groups.flatMap((g) => g.items)

  const requestClose = useCallback(() => {
    if (closing) return
    setClosing(true)
    setTimeout(() => onClose?.(), MOTION_EXIT_MS)
  }, [closing, onClose])

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) requestClose()
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [requestClose])

  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") { requestClose(); return }
      if (e.key === "ArrowDown") { setActiveIdx((i) => (i + 1) % allItems.length); e.preventDefault() }
      if (e.key === "ArrowUp") { setActiveIdx((i) => (i - 1 + allItems.length) % allItems.length); e.preventDefault() }
      if (e.key === "Enter") { const item = allItems[activeIdx]; onSelect({ type: item.type, action: item.action }); e.preventDefault() }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [activeIdx, allItems, requestClose, onSelect])

  const adjustedPos = useCallback(() => {
    const menuW = 260, menuH = 320
    let left = x, top = y
    if (left + menuW > window.innerWidth - 8) left = window.innerWidth - menuW - 8
    if (top + menuH > window.innerHeight - 8) top = window.innerHeight - menuH - 8
    return { left: Math.max(8, left), top: Math.max(8, top) }
  }, [x, y])

  const pos = adjustedPos()
  let globalIdx = 0

  const menuClasses = overlayClassNames({
    mounted: true,
    closing,
    open: !closing,
    base: "tl-picker-menu",
    enterClass: !closing ? "motion-popover-in" : "",
    exitClass: closing ? "motion-popover-out" : "",
  })

  return createPortal(
    <div
      ref={ref}
      className={menuClasses}
      style={{ left: pos.left, top: pos.top, zIndex: Z_NODE_DOTS_MENU }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {groups.map((group) => (
        <div key={group.group}>
          <div className="tl-picker-group-label">{group.group}</div>
          {group.items.map((item) => {
            const idx = globalIdx++
            return (
              <button
                key={`${item.type}-${item.action}`}
                className={`tl-picker-item${activeIdx === idx ? " active" : ""}`}
                onMouseEnter={() => setActiveIdx(idx)}
                onClick={() => onSelect({ type: item.type, action: item.action })}
              >
                <div className="tl-picker-icon"><LineIcon name={item.icon} size={18} /></div>
                <div className="tl-picker-text">
                  <div className="tl-picker-label">{item.label}</div>
                  {item.sub && <div className="tl-picker-sub">{item.sub}</div>}
                </div>
              </button>
            )
          })}
        </div>
      ))}
    </div>,
    getThemePortalRoot(),
  )
}
