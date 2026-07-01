import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { Link } from "lucide-react"
import { useLocale } from "../../utils/locale"
import { showDevNotice } from "../common/ProductNoticeModal"

function IconLink() {
  return <Link size={14} strokeWidth={2} aria-hidden />
}

function IconDownload() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M8 2.5v7.2M5.2 6.9 8 9.7l2.8-2.8"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3.5 11.5h9"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  )
}

function IconInvite() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="6" cy="5.5" r="2.2" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="M2.5 13c0-2.2 1.6-3.5 3.5-3.5s3.5 1.3 3.5 3.5"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <path
        d="M11.5 6.5v3M10 8h3"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  )
}

function IconReadonly() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M2.5 8s2.5-3.5 5.5-3.5S13.5 8 13.5 8s-2.5 3.5-5.5 3.5S2.5 8 2.5 8Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="8" r="1.8" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  )
}

export default function CanvasShareMenu({
  open,
  onClose,
  anchorRef,
  onCopyLink,
  onExportProject,
  readOnly = false,
}) {
  const { t } = useLocale()
  const panelRef = useRef(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })

  useLayoutEffect(() => {
    if (!open || !anchorRef?.current) return
    const rect = anchorRef.current.getBoundingClientRect()
    const panelW = 220
    let left = rect.right - panelW
    left = Math.max(12, Math.min(left, window.innerWidth - panelW - 12))
    setPos({
      top: rect.bottom + 8,
      left,
    })
  }, [open, anchorRef])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.()
    }
    const onPointer = (e) => {
      const anchor = anchorRef?.current
      if (panelRef.current?.contains(e.target)) return
      if (anchor?.contains(e.target)) return
      onClose?.()
    }
    window.addEventListener("keydown", onKey)
    document.addEventListener("mousedown", onPointer)
    return () => {
      window.removeEventListener("keydown", onKey)
      document.removeEventListener("mousedown", onPointer)
    }
  }, [open, onClose, anchorRef])

  if (!open) return null

  const items = [
    {
      key: "copy-link",
      icon: <IconLink />,
      label: t("canvas.shareMenu.copyLink"),
      disabled: readOnly,
      onClick: () => {
        onCopyLink?.()
        onClose?.()
      },
    },
    {
      key: "export",
      icon: <IconDownload />,
      label: t("canvas.shareMenu.exportProject"),
      disabled: readOnly,
      onClick: () => {
        onExportProject?.()
        onClose?.()
      },
    },
    {
      key: "invite",
      icon: <IconInvite />,
      label: t("canvas.shareMenu.inviteMember"),
      onClick: () => {
        showDevNotice(t("canvas.shareMenu.inviteMember"))
        onClose?.()
      },
    },
    {
      key: "readonly",
      icon: <IconReadonly />,
      label: t("canvas.shareMenu.readonlyView"),
      onClick: () => {
        showDevNotice(t("canvas.shareMenu.readonlyView"))
        onClose?.()
      },
    },
  ]

  return createPortal(
    <div
      ref={panelRef}
      className="ctb-share-menu"
      style={{ top: pos.top, left: pos.left }}
      role="menu"
      aria-label={t("canvas.topbar.share")}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className="ctb-share-menu-item"
          role="menuitem"
          disabled={item.disabled}
          onClick={item.onClick}
        >
          <span className="ctb-share-menu-icon">{item.icon}</span>
          <span className="ctb-share-menu-label">{item.label}</span>
        </button>
      ))}
    </div>,
    document.body
  )
}
