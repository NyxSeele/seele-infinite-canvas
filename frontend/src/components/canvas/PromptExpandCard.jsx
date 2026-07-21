import { useEffect, useRef } from "react"
import { createPortal } from "react-dom"
import { X } from "lucide-react"
import { useOverlayMount } from "../../hooks/useFlyoutMount"
import { useLocale } from "../../utils/locale"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_MODAL } from "../../utils/zIndexLayers"
import "./PromptExpandCard.css"

const sp = (e) => e.stopPropagation()

export default function PromptExpandCard({
  open,
  onClose,
  children,
}) {
  const { t } = useLocale()
  const { mounted, closing } = useOverlayMount(open)
  const cardRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!mounted) return null

  const overlayClass = [
    "pec-overlay",
    "nodrag",
    "nopan",
    getThemePageClass(),
    open && !closing ? "pec-overlay--open" : "",
    closing ? "pec-overlay--closing" : "",
  ].filter(Boolean).join(" ")

  return createPortal(
    <div
      className={overlayClass}
      style={{ zIndex: Z_MODAL }}
      role="presentation"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onClose?.()
      }}
    >
      <div
        ref={cardRef}
        className="pec-card"
        role="dialog"
        aria-modal="true"
        aria-label={t("canvas.prompt.expand")}
        onPointerDown={sp}
        onDoubleClick={sp}
      >
        <button
          type="button"
          className="pec-close nodrag"
          onClick={onClose}
          aria-label={t("canvas.common.close")}
        >
          <X size={16} />
        </button>
        <div className="pec-card__shell">{children}</div>
      </div>
    </div>,
    getThemePortalRoot()
  )
}
