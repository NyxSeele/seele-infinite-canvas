import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

import { ensureMediaUrl } from "../../utils/mediaTicket"

import { useLocale } from "../../utils/locale"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_DROPDOWN } from "../../utils/zIndexLayers"
import { closeCanvasDropdown, openCanvasDropdown } from "./canvasDropdownCoordinator"

import "./CastMentionPicker.css"

const sp = (e) => e.stopPropagation()

function clampCastMentionPos(anchorRect) {
  if (!anchorRect) return null
  const pad = 12
  const maxW = Math.min(320, window.innerWidth - pad * 2)
  let left = anchorRect.left
  if (left + maxW > window.innerWidth - pad) {
    left = Math.max(pad, window.innerWidth - pad - maxW)
  }
  return {
    position: "fixed",
    top: anchorRect.bottom + 6,
    left,
    minWidth: 200,
    maxWidth: maxW,
    zIndex: Z_DROPDOWN,
  }
}

export default function CastMentionPicker({ open, items = [], anchorRect = null, onSelect, onClose }) {
  const { t } = useLocale()
  const listRef = useRef(null)
  const [menuStyle, setMenuStyle] = useState(null)

  const list = items.filter((c) => c?.name)

  const updatePosition = useCallback(() => {
    setMenuStyle(clampCastMentionPos(anchorRect))
  }, [anchorRect])

  useEffect(() => {
    if (!open) return undefined
    const closeSelf = () => onClose?.()
    openCanvasDropdown(closeSelf)
    return () => closeCanvasDropdown(closeSelf)
  }, [open, onClose])

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
      className={`cast-mention-picker cast-mention-picker--portal nodrag nopan ${getThemePageClass()}`}
      style={menuStyle}
      onPointerDown={sp}
    >
      {list.length === 0 ? (
        <div className="cast-mention-empty">
          {t("canvas.cast.noItems")}
        </div>
      ) : (
        list.map((item) => (
          <button
            key={item.id}
            type="button"
            className="cast-mention-item nodrag"
            onMouseDown={(e) => {
              e.preventDefault()
              onSelect?.(item)
              onClose?.()
            }}
          >
            {item.imageUrl ? (
              <img
                src={ensureMediaUrl(item.imageUrl)}
                alt=""
                className="cast-mention-thumb"
                draggable={false}
              />
            ) : (
              <span className="cast-mention-thumb cast-mention-thumb--placeholder">
                {item.type === "scene" ? t("canvas.asset.sceneTag") : t("canvas.asset.personTag")}
              </span>
            )}
            <span className="cast-mention-meta">
              <span className="cast-mention-name">@{item.name}</span>
              <span className="cast-mention-type">
                {item.source === "global"
                  ? t("canvas.cast.fromAssetLib", {
                      type: item.type === "scene"
                        ? t("canvas.script.scene")
                        : t("canvas.script.person"),
                    })
                  : item.type === "scene"
                    ? t("canvas.cast.sceneSetting")
                    : t("canvas.cast.charSetting")}
              </span>
            </span>
          </button>
        ))
      )}
    </div>,
    getThemePortalRoot(),
  )
}
