import { useLayoutEffect, useState } from "react"
import { createPortal } from "react-dom"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import { useCanvasStore } from "../../stores"
import { useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import { MENU_FLYOUT_BRIDGE_GAP_PX } from "../../utils/menuFlyoutTiming"
import "./MenuFlyoutPortal.css"

/** 一次栏与二次栏之间的净间距（px） */
const GAP_PX = MENU_FLYOUT_BRIDGE_GAP_PX

export default function MenuFlyoutPortal({
  open,
  anchorRef,
  menuAlignRef,
  width = 240,
  className = "",
  onMouseEnter,
  onMouseLeave,
  children,
}) {
  const theme = useCanvasStore((s) => s.theme)
  const [pos, setPos] = useState({ top: 0, left: 0, bridgeLeft: 0, bridgeWidth: 0, height: 0 })
  const { mounted, closing } = useOverlayMount(open)

  useLayoutEffect(() => {
    if (!mounted || !anchorRef?.current) return undefined

    const update = () => {
      const anchor = anchorRef.current.getBoundingClientRect()
      const menuLeft = menuAlignRef?.current?.getBoundingClientRect().left ?? anchor.left
      const left = Math.max(12, menuLeft - width - GAP_PX)
      const bridgeLeft = left + width
      const bridgeWidth = Math.max(GAP_PX, menuLeft - bridgeLeft)

      setPos({
        top: anchor.top,
        left,
        height: anchor.height,
        bridgeLeft,
        bridgeWidth,
      })
    }

    update()
    window.addEventListener("scroll", update, true)
    window.addEventListener("resize", update)
    return () => {
      window.removeEventListener("scroll", update, true)
      window.removeEventListener("resize", update)
    }
  }, [mounted, anchorRef, menuAlignRef, width])

  if (!mounted) return null

  const themeClass = theme === "dark" ? "rf-page--dark" : "rf-page--light"

  const portalClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: `wum-flyout-portal ${themeClass}${className ? ` ${className}` : ""}`,
    enterClass: open && !closing ? "motion-popover-in motion-popover-in--left" : "",
    exitClass: closing ? "motion-popover-out motion-popover-out--left" : "",
  })

  return createPortal(
    <>
      <div
        className="wum-flyout-bridge"
        style={{
          top: pos.top,
          left: pos.bridgeLeft,
          width: pos.bridgeWidth,
          height: Math.max(pos.height, 36),
        }}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        aria-hidden
      />
      <div
        className={portalClasses}
        style={{ top: pos.top, left: pos.left, width }}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      >
        {children}
      </div>
    </>,
    getThemePortalRoot()
  )
}
