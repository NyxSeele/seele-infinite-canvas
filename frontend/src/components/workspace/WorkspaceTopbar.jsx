import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../../contexts/AuthContext"
import { useCanvasStore } from "../../stores"
import { readUserAvatar } from "../../utils/canvas/userAvatar"
import { LineIcon } from "../icons/LineIcons"
import WorkspaceUserMenu from "./WorkspaceUserMenu"
import WorkspaceNotifyPanel from "./WorkspaceNotifyPanel"
import { useNotificationUnread, emitNotificationUnread } from "../../hooks/useNotificationUnread"
import JoinTeamInputModal from "./JoinTeamInputModal"
import { MENU_HOVER_MENU_CLOSE_MS } from "../../utils/menuFlyoutTiming"
import { useThemeTransition } from "../../hooks/useThemeTransition"
import { IconCredit } from "../canvas/CanvasTopbarIcons"

const PREFS_KEY = "canvas-user-profile-prefs"

function readDisplayName(fallback) {
  try {
    const prefs = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}")
    return prefs.displayName || fallback || ""
  } catch {
    return fallback || ""
  }
}

export default function WorkspaceTopbar({
  backLabel = null,
  onBack = null,
  title = null,
}) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const theme = useCanvasStore((s) => s.theme)
  const { toggleThemeWithTransition } = useThemeTransition()

  const [avatarUrl, setAvatarUrl] = useState(() => readUserAvatar())
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [notifyOpen, setNotifyOpen] = useState(false)
  const { unread: notifyUnread, setUnread: setNotifyUnread } = useNotificationUnread()
  const [joinOpen, setJoinOpen] = useState(false)
  const avatarBtnRef = useRef(null)
  const avatarWrapRef = useRef(null)
  const menuOpenTimerRef = useRef(null)
  const menuCloseTimerRef = useRef(null)

  const submenuLatchRef = useRef(false)

  const MENU_OPEN_DELAY_MS = 180
  const MENU_CLOSE_DELAY_MS = MENU_HOVER_MENU_CLOSE_MS

  const scheduleMenuOpen = () => {
    clearTimeout(menuCloseTimerRef.current)
    menuOpenTimerRef.current = setTimeout(() => setUserMenuOpen(true), MENU_OPEN_DELAY_MS)
  }

  const scheduleMenuClose = () => {
    clearTimeout(menuOpenTimerRef.current)
    menuCloseTimerRef.current = setTimeout(() => {
      if (!submenuLatchRef.current) setUserMenuOpen(false)
    }, MENU_CLOSE_DELAY_MS)
  }

  const cancelMenuClose = () => {
    clearTimeout(menuCloseTimerRef.current)
  }

  const handleSubmenuLatch = (latched) => {
    submenuLatchRef.current = latched
    if (latched) cancelMenuClose()
  }

  useEffect(() => {
    const onAvatar = () => setAvatarUrl(readUserAvatar())
    window.addEventListener("canvas-avatar-changed", onAvatar)
    return () => window.removeEventListener("canvas-avatar-changed", onAvatar)
  }, [])

  useEffect(() => () => {
    clearTimeout(menuOpenTimerRef.current)
    clearTimeout(menuCloseTimerRef.current)
  }, [])

  const displayName = readDisplayName(user?.username) || user?.username || "创作者"
  const logoSrc = "/velora-logo.png"

  const q = user?.quota
  const creditNum = q
    ? (q.image_limit < 0 ? "∞" : String(Math.max(0, (q.image_limit ?? 0) - (q.image_used ?? 0))))
    : "—"

  return (
    <>
      <header className="ws-header">
        <div className="ws-header-left">
          <div className="ctb-logo-wrap">
            <button type="button" className="ctb-logo" onClick={() => navigate("/workspace")}>
              <img src={logoSrc} alt="Velora" className="ctb-logo-img" draggable={false} />
            </button>
          </div>
          {!onBack && !title && (
            <span className="ws-brand-name velora-wordmark velora-wordmark--sm">Velora</span>
          )}
          {onBack && (
            <button type="button" className="ws-back-btn" onClick={onBack} aria-label="返回">
              <span className="ws-back-arrow">←</span>
              {backLabel && <span className="ws-back-label">{backLabel}</span>}
            </button>
          )}
          {title && <h1 className="ws-header-title">{title}</h1>}
        </div>

        <div className="ws-util-capsule">
          <button type="button" className="ws-util-credit" title="Credits">
            <IconCredit />
            <span className="ws-util-credit-num">{creditNum}</span>
          </button>
          <span className="ws-util-sep" />
          <button
            type="button"
            className="ws-util-theme"
            onClick={(e) => toggleThemeWithTransition(e)}
            title={theme === "dark" ? "切换亮色" : "切换暗色"}
          >
            <LineIcon name="sun" size={16} />
          </button>
          <span className="ws-util-sep" />
          <div
            className="ws-avatar-wrap"
            ref={avatarWrapRef}
            onMouseEnter={scheduleMenuOpen}
            onMouseLeave={scheduleMenuClose}
          >
            {notifyUnread > 0 && <span className="ws-avatar-notify-dot" aria-hidden />}
            <button
              ref={avatarBtnRef}
              type="button"
              className="ws-avatar-btn"
              onClick={() => setUserMenuOpen((v) => !v)}
              title="账户菜单"
            >
              {avatarUrl ? (
                <img src={avatarUrl} alt="" draggable={false} />
              ) : (
                (displayName[0] || "U").toUpperCase()
              )}
            </button>
            <WorkspaceUserMenu
              open={userMenuOpen}
              onClose={() => setUserMenuOpen(false)}
              anchorRef={avatarWrapRef}
              displayName={displayName}
              avatarUrl={avatarUrl}
              notifyUnread={notifyUnread}
              onOpenNotify={() => setNotifyOpen(true)}
              onOpenJoinTeam={() => {
                setUserMenuOpen(false)
                submenuLatchRef.current = false
                setJoinOpen(true)
              }}
              onMenuMouseEnter={cancelMenuClose}
              onMenuMouseLeave={scheduleMenuClose}
              onSubmenuLatch={handleSubmenuLatch}
            />
          </div>
        </div>
      </header>
      <JoinTeamInputModal
        open={joinOpen}
        onClose={() => setJoinOpen(false)}
      />
      <WorkspaceNotifyPanel
        open={notifyOpen}
        onClose={() => setNotifyOpen(false)}
        onUnreadChange={(count) => {
          setNotifyUnread(count)
          emitNotificationUnread(count)
        }}
      />
    </>
  )
}
