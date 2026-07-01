import { useEffect } from "react"
import { createPortal } from "react-dom"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import "./MediaLightbox.css"

export default function MediaLightbox({ url, alt = "", onClose }) {
  useEffect(() => {
    if (!url) return undefined
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [url, onClose])

  if (!url) return null

  return createPortal(
    <div
      className="media-lightbox"
      role="dialog"
      aria-modal="true"
      onClick={() => onClose?.()}
    >
      <button type="button" className="media-lightbox-close" onClick={() => onClose?.()}>
        ×
      </button>
      <img
        src={ensureMediaUrl(url)}
        alt={alt}
        className="media-lightbox-img"
        onClick={(e) => e.stopPropagation()}
        draggable={false}
      />
    </div>,
    document.body
  )
}
