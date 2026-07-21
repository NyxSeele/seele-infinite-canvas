import { useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { getThemePortalRoot } from "../../utils/themePortalRoot"

const POPOVER_WIDTH = 240
const GAP_PX = 10
const VIEWPORT_MARGIN = 12

export default function IdentityInfoPopover({
  open,
  anchorRef,
  themeClass,
  onMouseEnter,
  onMouseLeave,
  children,
}) {
  const panelRef = useRef(null)
  const [pos, setPos] = useState({
    top: 0,
    left: 0,
    bridgeTop: 0,
    bridgeLeft: 0,
    bridgeWidth: 0,
    bridgeHeight: 0,
  })

  useLayoutEffect(() => {
    if (!open || !anchorRef?.current) return undefined

    const update = () => {
      const anchor = anchorRef.current.getBoundingClientRect()
      const panel = panelRef.current
      const panelHeight = panel?.offsetHeight ?? 0
      const left = Math.max(VIEWPORT_MARGIN, anchor.left - POPOVER_WIDTH - GAP_PX)
      let top = anchor.top
      if (panelHeight > 0) {
        const maxTop = window.innerHeight - panelHeight - VIEWPORT_MARGIN
        top = Math.max(VIEWPORT_MARGIN, Math.min(top, maxTop))
      }

      const bridgeLeft = left + POPOVER_WIDTH
      const bridgeWidth = Math.max(GAP_PX, anchor.left - bridgeLeft)
      const bridgeTop = panelHeight > 0 ? Math.min(anchor.top, top) : anchor.top
      const bridgeHeight = panelHeight > 0
        ? Math.max(anchor.bottom, top + panelHeight) - bridgeTop
        : anchor.height

      setPos({
        top,
        left,
        bridgeTop,
        bridgeLeft,
        bridgeWidth,
        bridgeHeight,
      })
    }

    update()
    const ro = panelRef.current ? new ResizeObserver(update) : null
    ro?.observe(panelRef.current)
    window.addEventListener("scroll", update, true)
    window.addEventListener("resize", update)
    return () => {
      ro?.disconnect()
      window.removeEventListener("scroll", update, true)
      window.removeEventListener("resize", update)
    }
  }, [open, anchorRef, children])

  if (!open) return null

  return createPortal(
    <>
      <div
        className="wum-identity-popover-bridge ws-overlay-root"
        style={{
          top: pos.bridgeTop,
          left: pos.bridgeLeft,
          width: pos.bridgeWidth,
          height: Math.max(pos.bridgeHeight, 24),
        }}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        aria-hidden
      />
      <div
        ref={panelRef}
        className={`wum-identity-popover ws-overlay-root ${themeClass}`}
        style={{ top: pos.top, left: pos.left, width: POPOVER_WIDTH }}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      >
        {children}
      </div>
    </>,
    getThemePortalRoot()
  )
}
