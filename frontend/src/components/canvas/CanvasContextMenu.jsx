import { useEffect, useRef } from "react"
import { LineIcon } from "../icons/LineIcons"
import { useLocale } from "../../utils/locale"

const NODE_CREATE_ITEMS = [
  { type: "generationCard", icon: "sparkle", labelKey: "canvas.menu.imageGen" },
  { type: "videoGeneration", icon: "video", labelKey: "canvas.menu.videoGen" },
  { type: "text", icon: "text", labelKey: "canvas.menu.textNote" },
  { type: "imageUpload", icon: "upload", labelKey: "canvas.menu.uploadImage" },
]

const NODE_OPTIONS_ITEMS = [
  { type: "duplicate", icon: "plus", labelKey: "canvas.menu.copyNode" },
  { type: "delete", icon: "trash", labelKey: "canvas.menu.deleteNode", danger: true },
]

export default function CanvasContextMenu({
  contextMenu,
  onClose,
  onCreateNode,
  onNodeAction,
}) {
  const { t } = useLocale()
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        onClose()
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [onClose])

  if (!contextMenu) return null

  const isCreate =
    contextMenu.type === "create" || contextMenu.type === "create-from-edge"
  const items = isCreate ? NODE_CREATE_ITEMS : NODE_OPTIONS_ITEMS

  const handleItemClick = (item) => {
    if (isCreate) {
      onCreateNode(item.type, contextMenu)
    } else {
      onNodeAction(item.type, contextMenu.nodeId)
    }
    onClose()
  }

  return (
    <div
      ref={ref}
      className="canvas-context-menu"
      style={{ left: contextMenu.x, top: contextMenu.y }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {items.map((item) => (
        <button
          key={item.type}
          type="button"
          className={`context-menu-item${item.danger ? " danger" : ""}`}
          onClick={() => handleItemClick(item)}
        >
          <span className="context-menu-icon"><LineIcon name={item.icon} size={16} /></span>
          <span>{t(item.labelKey)}</span>
        </button>
      ))}
    </div>
  )
}
