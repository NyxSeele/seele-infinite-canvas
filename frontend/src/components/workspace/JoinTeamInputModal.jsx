import { useState } from "react"
import { createPortal } from "react-dom"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import { useNavigate } from "react-router-dom"
import { useCanvasStore } from "../../stores"
import { useLocale } from "../../utils/locale"
import { useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import "../../pages/Canvas.css"
import "./JoinTeamInputModal.css"

function parseInviteToken(raw) {
  const text = String(raw || "").trim()
  if (!text) return ""
  try {
    const url = new URL(text, window.location.origin)
    const fromQuery = url.searchParams.get("token")
    if (fromQuery) return fromQuery.trim()
  } catch {
    /* not a url */
  }
  if (/^[\w-]{8,}$/.test(text)) return text
  return ""
}

export default function JoinTeamInputModal({ open, onClose }) {
  const navigate = useNavigate()
  const { t } = useLocale()
  const theme = useCanvasStore((s) => s.theme)
  const [value, setValue] = useState("")
  const [error, setError] = useState("")
  const { mounted, closing } = useOverlayMount(open)

  const handleSubmit = (e) => {
    e.preventDefault()
    const token = parseInviteToken(value)
    if (!token) {
      setError(t("join.error"))
      return
    }
    onClose?.()
    navigate(`/join-team?token=${encodeURIComponent(token)}`)
  }

  if (!mounted) return null

  const overlayClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: `jti-backdrop ws-overlay-root rf-page--${theme}`,
    enterClass: open && !closing ? "motion-modal-overlay-in" : "",
    exitClass: closing ? "motion-modal-overlay-out" : "",
  })

  const modalClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: "jti-modal",
    enterClass: open && !closing ? "motion-modal-in" : "",
    exitClass: closing ? "motion-modal-out" : "",
  })

  return createPortal(
    <div className={overlayClasses} onClick={onClose}>
      <form className={modalClasses} onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}>
        <header className="jti-head">
          <h2>{t("join.title")}</h2>
          <button type="button" className="jti-close" onClick={onClose} aria-label={t("profile.close")}>×</button>
        </header>
        <p className="jti-desc">{t("join.desc")}</p>
        <label className="jti-field">
          <span>{t("join.field")}</span>
          <input
            className="jti-input"
            value={value}
            onChange={(e) => { setValue(e.target.value); setError("") }}
            placeholder={t("join.placeholder")}
            autoFocus
          />
        </label>
        {error && <p className="jti-error">{error}</p>}
        <footer className="jti-foot">
          <button type="button" className="jti-btn jti-btn--ghost" onClick={onClose}>{t("join.cancel")}</button>
          <button type="submit" className="jti-btn jti-btn--primary">{t("join.continue")}</button>
        </footer>
      </form>
    </div>,
    getThemePortalRoot()
  )
}
