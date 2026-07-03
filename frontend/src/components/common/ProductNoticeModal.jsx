import { useCallback, useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import { useLocale } from "../../utils/locale"
import "./ProductNoticeModal.css"

export const PRODUCT_NOTICE_EVENT = "product-notice-show"

export function showDevNotice(feature = "") {
  window.dispatchEvent(
    new CustomEvent(PRODUCT_NOTICE_EVENT, { detail: { type: "dev", feature } })
  )
}

export function showProductNotice({ title, message } = {}) {
  window.dispatchEvent(
    new CustomEvent(PRODUCT_NOTICE_EVENT, { detail: { type: "custom", title, message } })
  )
}

export default function ProductNoticeModal() {
  const { t } = useLocale()
  const [open, setOpen] = useState(false)
  const [payload, setPayload] = useState(null)

  const close = useCallback(() => {
    setOpen(false)
    setPayload(null)
  }, [])

  useEffect(() => {
    const onShow = (e) => {
      setPayload(e.detail || {})
      setOpen(true)
    }
    window.addEventListener(PRODUCT_NOTICE_EVENT, onShow)
    return () => window.removeEventListener(PRODUCT_NOTICE_EVENT, onShow)
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === "Escape") close()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, close])

  if (!open || !payload) return null

  const isDev = payload.type === "dev"
  const title = isDev
    ? t("notice.devTitle")
    : (payload.title || t("notice.devTitle"))
  const message = isDev
    ? t("notice.devMessage", { feature: payload.feature || t("notice.devFeatureFallback") })
    : (payload.message || "")

  return createPortal(
    <div className="pnm-backdrop" onPointerDown={(e) => { if (e.target === e.currentTarget) close() }}>
      <div className="pnm-card" role="dialog" aria-modal="true" aria-labelledby="pnm-title">
        <div className="pnm-icon" aria-hidden>
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <circle cx="14" cy="14" r="12" stroke="currentColor" strokeWidth="1.5" />
            <path d="M14 8v7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <circle cx="14" cy="19.5" r="1.2" fill="currentColor" />
          </svg>
        </div>
        <h2 id="pnm-title" className="pnm-title">{title}</h2>
        <p className="pnm-message">{message}</p>
        <button type="button" className="pnm-btn" onClick={close}>
          {t("notice.ok")}
        </button>
      </div>
    </div>,
    getThemePortalRoot()
  )
}
