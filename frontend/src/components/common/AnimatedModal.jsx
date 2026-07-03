import { createPortal } from "react-dom"
import { useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"

/**
 * 带进出场动画的 Modal 壳（overlay + content）
 */
export default function AnimatedModal({
  open,
  onClose,
  overlayClass = "ws-modal-overlay",
  modalClass = "ws-modal",
  children,
}) {
  const { mounted, closing } = useOverlayMount(open)
  if (!mounted) return null

  const themeClass = getThemePageClass()

  const overlayClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: `${overlayClass} ${themeClass}`.trim(),
    enterClass: open && !closing ? "motion-modal-overlay-in" : "",
    exitClass: closing ? "motion-modal-overlay-out" : "",
  })

  const modalClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: modalClass,
    enterClass: open && !closing ? "motion-modal-in" : "",
    exitClass: closing ? "motion-modal-out" : "",
  })

  return createPortal(
    <div className={overlayClasses} onClick={onClose}>
      <div className={modalClasses} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>,
    getThemePortalRoot()
  )
}

/**
 * idm / 画布 Modal 专用壳（class 前缀不同）
 */
export function AnimatedDialog({
  open,
  onClose,
  overlayClassName = "idm-overlay",
  modalClassName = "idm-modal",
  themeClass = "",
  children,
}) {
  const { mounted, closing } = useOverlayMount(open)
  if (!mounted) return null

  const resolvedTheme = themeClass || getThemePageClass()

  const overlayClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: `${overlayClassName}${resolvedTheme ? ` ${resolvedTheme}` : ""}`,
    enterClass: open && !closing ? "motion-modal-overlay-in" : "",
    exitClass: closing ? "motion-modal-overlay-out" : "",
  })

  const modalClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: modalClassName,
    enterClass: open && !closing ? "motion-modal-in" : "",
    exitClass: closing ? "motion-modal-out" : "",
  })

  return createPortal(
    <div className={overlayClasses} onMouseDown={onClose}>
      <div className={modalClasses} onMouseDown={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>,
    getThemePortalRoot()
  )
}
