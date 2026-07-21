import { useCallback, useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { useNavigate } from "react-router-dom"
import { formatRelativeTime } from "../../utils/canvas/formatRelativeTime"
import { markThreadNotificationsRead, applyReadToItems } from "../../utils/notificationThread"
import { fetchNotifications } from "../../services/notificationsApi"
import { emitNotificationUnread } from "../../hooks/useNotificationUnread"
import { useLocale } from "../../utils/locale"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_WS_NOTIFY } from "../../utils/zIndexLayers"
import "./WorkspaceNotifyPanel.css"

function IconBellLarge() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden>
      <circle cx="20" cy="20" r="18" fill="currentColor" opacity="0.12" />
      <path d="M20 10a5.5 5.5 0 0 0-5.5 5.5v4.2l-1.5 2.8h14l-1.5-2.8V15.5A5.5 5.5 0 0 0 20 10Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M17 27.5a3 3 0 0 0 6 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export default function WorkspaceNotifyPanel({ open, onClose, onUnreadChange }) {
  const navigate = useNavigate()
  const { t } = useLocale()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchNotifications()
      setItems(data?.notifications || [])
      onUnreadChange?.(data?.unread_count ?? 0)
    } catch (err) {
      console.warn("load notifications failed", err)
    } finally {
      setLoading(false)
    }
  }, [onUnreadChange])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === "Escape") onClose?.() }
    window.addEventListener("keydown", onKey)
    void load()
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose, load])

  const syncUnread = useCallback((nextItems) => {
    const count = nextItems.filter((i) => !i.is_read).length
    onUnreadChange?.(count)
    emitNotificationUnread(count)
  }, [onUnreadChange])

  const handleClickItem = async (item) => {
    const payload = item.payload || {}
    const { ids, commentIds } = await markThreadNotificationsRead(items, item)
    if (ids.length) {
      const nextItems = applyReadToItems(items, ids)
      setItems(nextItems)
      syncUnread(nextItems)
    }
    if (payload.project_id && payload.node_id) {
      onClose?.()
      const highlight = commentIds.length
        ? `&highlightComments=${commentIds.map(encodeURIComponent).join(",")}`
        : ""
      navigate(
        `/canvas/${payload.project_id}?openComment=${encodeURIComponent(payload.node_id)}${highlight}`
      )
    }
  }

  if (!open) return null

  return createPortal(
    <div className="wnp-backdrop ws-overlay-root" style={{ zIndex: Z_WS_NOTIFY }} onClick={onClose} role="presentation">
      <aside
        className="wnp-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t("canvas.notify.title")}
      >
        <header className="wnp-head">
          <div>
            <h2 className="wnp-title">{t("canvas.notify.title")}</h2>
            <p className="wnp-sub">{t("canvas.notify.sub")}</p>
          </div>
          <div className="wnp-head-actions">
            <button type="button" className="wnp-close" onClick={onClose} aria-label={t("canvas.common.close")}>
              ×
            </button>
          </div>
        </header>
        {loading ? (
          <div className="wnp-empty">
            <p className="wnp-empty-title">{t("canvas.common.loading")}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="wnp-empty">
            <div className="wnp-empty-icon">
              <IconBellLarge />
            </div>
            <p className="wnp-empty-title">{t("canvas.notify.empty")}</p>
            <p className="wnp-empty-sub">{t("canvas.notify.emptySub")}</p>
          </div>
        ) : (
          <ul className="wnp-list">
            {items.map((item) => {
              const payload = item.payload || {}
              const who = payload.mentioner?.name || payload.mentioner?.username || "Someone"
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`wnp-item${item.is_read ? "" : " wnp-item--unread"}`}
                    onClick={() => handleClickItem(item)}
                  >
                    <span className="wnp-item-title">
                      <strong>{who}</strong> {t("canvas.notify.mention")}
                    </span>
                    {payload.body_preview && (
                      <span className="wnp-item-preview">{payload.body_preview}</span>
                    )}
                    {payload.project_name && (
                      <span className="wnp-item-meta">{payload.project_name}</span>
                    )}
                    <span className="wnp-item-time">{formatRelativeTime(item.created_at)}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </aside>
    </div>,
    getThemePortalRoot(),
  )
}
