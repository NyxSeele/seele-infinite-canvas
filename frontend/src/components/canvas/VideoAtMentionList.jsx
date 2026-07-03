import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useLocale } from "../../utils/locale"
import { useMentionableItems } from "./promptMentions"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import "./VideoReferencePanel.css"

const sp = (e) => e.stopPropagation()

function clampMentionPos(anchorRect) {
  if (!anchorRect) return null
  const pad = 12
  const maxW = Math.min(280, window.innerWidth - pad * 2)
  let left = anchorRect.left
  if (left + maxW > window.innerWidth - pad) {
    left = Math.max(pad, window.innerWidth - pad - maxW)
  }
  return {
    position: "fixed",
    top: anchorRect.bottom + 6,
    left,
    minWidth: 160,
    maxWidth: maxW,
    zIndex: 10050,
  }
}

/** 画布可引用元素列表（@ 提及） */
export function VideoAtMentionList({
  open,
  onSelect,
  onClose,
  query = "",
  anchorRect = null,
  excludeNodeId = null,
  compact = false,
}) {
  const { t } = useLocale()
  const candidates = useMentionableItems(excludeNodeId)
  const listRef = useRef(null)
  const [menuStyle, setMenuStyle] = useState(null)

  const filtered = candidates.filter((c) => {
    const q = (query || "").toLowerCase()
    if (!q) return true
    return c.name.toLowerCase().includes(q)
  })

  const updatePosition = useCallback(() => {
    setMenuStyle(clampMentionPos(anchorRect))
  }, [anchorRect])

  useEffect(() => {
    if (!open) {
      setMenuStyle(null)
      return undefined
    }
    updatePosition()

    let rafId = 0
    const tick = () => {
      updatePosition()
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)

    window.addEventListener("resize", updatePosition)
    window.addEventListener("scroll", updatePosition, true)
    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener("resize", updatePosition)
      window.removeEventListener("scroll", updatePosition, true)
    }
  }, [open, updatePosition])

  if (!open || !menuStyle) return null

  return createPortal(
    <div
      ref={listRef}
      className={`video-at-mention video-at-mention--portal nodrag nopan ${getThemePageClass()}${compact ? " video-at-mention--compact" : ""}`}
      style={menuStyle}
      onPointerDown={sp}
    >
      {filtered.length === 0 ? (
        <div className="video-at-mention-empty">{t("canvas.video.noRefElements")}</div>
      ) : (
        filtered.slice(0, 8).map((c) => (
          <button
            key={`${c.id}_${c.image_index ?? 0}_${c.type}`}
            type="button"
            className="video-at-mention-item nodrag nopan"
            onClick={() => {
              onSelect?.(c)
              onClose?.()
            }}
          >
            {c.thumbUrl || c.imageUrl ? (
              c.type === "video" ? (
                <span className="video-at-mention-thumb video-at-mention-thumb--video">▶</span>
              ) : (
                <img
                  src={ensureMediaUrl(c.thumbUrl || c.imageUrl)}
                  alt=""
                  draggable={false}
                  style={{ pointerEvents: "none" }}
                />
              )
            ) : (
              <span className="video-at-mention-thumb video-at-mention-thumb--text">T</span>
            )}
            <span className="video-at-mention-label">
              <span className="video-at-mention-name">@{c.name}</span>
              {c.preview && (
                <span className="video-at-mention-preview">{c.preview}</span>
              )}
            </span>
          </button>
        ))
      )}
    </div>,
    getThemePortalRoot(),
  )
}

export default VideoAtMentionList
