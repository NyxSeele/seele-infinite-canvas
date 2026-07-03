import { useState, useRef, useEffect, useCallback } from "react"
import { createPortal } from "react-dom"
import { useAuth } from "../../contexts/AuthContext"
import { useNavigate } from "react-router-dom"
import { useCanvasStore } from "../../stores"
import { CANVAS_NAV_MODE_OPTIONS } from "../../utils/canvas/canvasNavMode"

import { pushGenHistory, readGenHistory } from "../../utils/canvas/genHistory"
import { AVATAR_CHANGED_EVENT, readUserAvatar } from "../../utils/canvas/userAvatar"
import pkg from "../../../package.json"
import { LineIcon } from "../icons/LineIcons"
import { IconCredit } from "./CanvasTopbarIcons"
import { useLocale } from "../../utils/locale"
import { useThemeTransition } from "../../hooks/useThemeTransition"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"

const APP_VERSION = `v${pkg.version}`
const PREFS_KEY = "canvas-user-profile-prefs"

function readDisplayName(fallback) {
  try {
    const prefs = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}")
    return prefs.displayName || fallback || ""
  } catch {
    return fallback || ""
  }
}

export { pushGenHistory, readGenHistory }

function CltItemWrap({ label, className = "", children }) {
  const wrapRef = useRef(null)
  const [hovered, setHovered] = useState(false)
  const [pillPos, setPillPos] = useState(null)

  const updatePillPos = useCallback(() => {
    const r = wrapRef.current?.getBoundingClientRect()
    if (!r) return
    setPillPos({
      left: r.right + 8,
      top: r.top + r.height / 2,
    })
  }, [])

  useEffect(() => {
    if (!hovered) {
      setPillPos(null)
      return undefined
    }
    updatePillPos()
    window.addEventListener("scroll", updatePillPos, true)
    window.addEventListener("resize", updatePillPos)
    return () => {
      window.removeEventListener("scroll", updatePillPos, true)
      window.removeEventListener("resize", updatePillPos)
    }
  }, [hovered, updatePillPos])

  const portalPill = hovered && pillPos
    ? createPortal(
        <span
          className={`clt-hover-pill clt-hover-pill--portal ${getThemePageClass()}`}
          style={{ left: pillPos.left, top: pillPos.top }}
          aria-hidden
        >
          {label}
        </span>,
        getThemePortalRoot(),
      )
    : null

  return (
    <div
      ref={wrapRef}
      className={`clt-item-wrap${className ? ` ${className}` : ""}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {children}
      <span className="clt-hover-pill clt-hover-pill--inline" aria-hidden>{label}</span>
      {portalPill}
    </div>
  )
}

const PlusIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M8 2.5v11M2.5 8h11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
)
const AssetLibIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
    <path d="M2 6.5h12" stroke="currentColor" strokeWidth="1.2"/>
    <circle cx="5.5" cy="9" r="1.2" fill="currentColor" opacity="0.7"/>
    <path d="M8 11l2-2.2 2.5 3.2" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)
const HistoryIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.3"/>
    <path d="M8 5V8l2.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)
const NavModeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M2.5 5.5h11M2.5 8h11M2.5 10.5h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    <path d="M12 9.5l1.5 1-1.5 1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)
const CommentIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path
      d="M3.5 4.2A1.2 1.2 0 0 1 4.7 3h6.6a1.2 1.2 0 0 1 1.2 1.2v4.6a1.2 1.2 0 0 1-1.2 1.2H7.2L4.5 12.5V9.8H4.7A1.2 1.2 0 0 1 3.5 8.6V4.2Z"
      stroke="currentColor"
      strokeWidth="1.25"
      strokeLinejoin="round"
    />
  </svg>
)
const FullscreenIcon = ({ exit = false }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    {exit ? (
      <>
        <path d="M5.5 2.5H2.5V5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M10.5 2.5H13.5V5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M5.5 13.5H2.5V10.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M10.5 13.5H13.5V10.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      </>
    ) : (
      <>
        <path d="M2.5 5.5V2.5H5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M10.5 2.5H13.5V5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M2.5 10.5V13.5H5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M13.5 10.5V13.5H10.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      </>
    )}
  </svg>
)

const TOOLBAR_ITEMS = [
  { id: "assets",    Icon: AssetLibIcon, labelKey: "canvas.toolbar.assets",       action: "open-assets" },
  { id: "history",   Icon: HistoryIcon,  labelKey: "canvas.toolbar.history",     action: "open-history" },
  { id: "comment",   Icon: CommentIcon,  labelKey: "canvas.toolbar.comment",     action: "toggle-comment" },
  { id: "fullscreen", Icon: FullscreenIcon, labelKey: "canvas.toolbar.fullscreen", action: "toggle-fullscreen", dynamicLabel: true },
]

const ADD_CARDS = [
  { type: "image-gen", icon: "sparkle", labelKey: "canvas.toolbar.imageGen" },
  { type: "video-gen", icon: "video", labelKey: "canvas.toolbar.videoGen" },
  { type: "text-note", icon: "text", labelKey: "canvas.toolbar.textNote" },
  { type: "image-upload", icon: "upload", labelKey: "canvas.toolbar.imageUpload" },
]

function AddMenuPanel({ onSelect, onUploadImage, onClose, t }) {
  return (
    <div className="clt-add-menu">
      {ADD_CARDS.map((c) => (
        <button
          key={c.type}
          className="clt-add-card"
          onClick={() => {
            if (c.type === "image-upload") { onClose(); onUploadImage?.() }
            else { onSelect(c.type); onClose() }
          }}
        >
          <span className="clt-add-card-icon"><LineIcon name={c.icon} size={20} /></span>
          <span className="clt-add-card-label">{t(c.labelKey)}</span>
        </button>
      ))}
    </div>
  )
}

function CanvasNavModePanel({ mode, onSelect, t }) {
  return (
    <div className="clt-panel clt-nav-panel">
      <div className="clt-panel-title">{t("canvas.toolbar.navTitle")}</div>
      {CANVAS_NAV_MODE_OPTIONS.map((opt) => (
        <button
          key={opt.id}
          type="button"
          className={`clt-nav-option${mode === opt.id ? " clt-nav-option--active" : ""}`}
          onClick={() => onSelect(opt.id)}
        >
          <div className="clt-nav-option-head">
            <span className="clt-nav-option-label">{opt.label}</span>
            <span className="clt-nav-option-badge">{opt.badge}</span>
          </div>
          <span className="clt-nav-option-desc">{opt.desc}</span>
        </button>
      ))}
    </div>
  )
}

export default function CanvasLeftToolbar({
  onAddNodeOfType,
  onUploadImage,
  isFullscreen = false,
  onToggleFullscreen,
  hasUnreadComments = false,
}) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { t } = useLocale()
  const canvasNavMode = useCanvasStore((s) => s.canvasNavMode)
  const setCanvasNavMode = useCanvasStore((s) => s.setCanvasNavMode)
  const assetLibraryOpen = useCanvasStore((s) => s.assetLibraryOpen)
  const genHistoryOpen = useCanvasStore((s) => s.genHistoryOpen)
  const setAssetLibraryOpen = useCanvasStore((s) => s.setAssetLibraryOpen)
  const setGenHistoryOpen = useCanvasStore((s) => s.setGenHistoryOpen)
  const toggleAssetLibrary = useCanvasStore((s) => s.toggleAssetLibrary)
  const toggleGenHistory = useCanvasStore((s) => s.toggleGenHistory)
  const setProfileModalOpen = useCanvasStore((s) => s.setProfileModalOpen)
  const commentMode = useCanvasStore((s) => s.commentMode)
  const toggleCommentMode = useCanvasStore((s) => s.toggleCommentMode)
  const theme = useCanvasStore((s) => s.theme)
  const { toggleThemeWithTransition } = useThemeTransition()
  const isAdmin = user?.role === "admin"
  const avatarLetter = user?.username?.[0]?.toUpperCase() || "?"
  const [avatarUrl, setAvatarUrl] = useState(() => readUserAvatar())
  const [displayName, setDisplayName] = useState(() => readDisplayName(user?.username))
  const q = user?.quota
  const quotaText = q
    ? (q.image_limit < 0 ? "∞" : `${q.image_used ?? 0} / ${q.image_limit}`)
    : null

  const [activePanel, setActivePanel] = useState(null)
  const toolbarRef = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (toolbarRef.current && !toolbarRef.current.contains(e.target)) setActivePanel(null)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  useEffect(() => {
    setAvatarUrl(readUserAvatar())
    setDisplayName(readDisplayName(user?.username))
    const onAvatarChange = () => setAvatarUrl(readUserAvatar())
    const onPrefsChange = () => setDisplayName(readDisplayName(user?.username))
    window.addEventListener(AVATAR_CHANGED_EVENT, onAvatarChange)
    window.addEventListener("canvas-prefs-changed", onPrefsChange)
    return () => {
      window.removeEventListener(AVATAR_CHANGED_EVENT, onAvatarChange)
      window.removeEventListener("canvas-prefs-changed", onPrefsChange)
    }
  }, [user?.username])

  useEffect(() => {
    if (activePanel === "avatar" || activePanel === "nav") {
      setDisplayName(readDisplayName(user?.username))
    }
  }, [activePanel, user?.username])

  const closeFlyouts = useCallback(() => {
    setAssetLibraryOpen(false)
    setGenHistoryOpen(false)
  }, [setAssetLibraryOpen, setGenHistoryOpen])

  const toggle = useCallback(
    (id) => {
      setActivePanel((cur) => {
        const next = cur === id ? null : id
        if (next !== null) closeFlyouts()
        return next
      })
    },
    [closeFlyouts]
  )

  const handleAction = useCallback(
    (action) => {
      setActivePanel(null)
      if (action === "open-assets") toggleAssetLibrary()
      if (action === "open-history") toggleGenHistory()
      if (action === "toggle-comment") toggleCommentMode()
      if (action === "toggle-fullscreen") onToggleFullscreen?.()
    },
    [toggleAssetLibrary, toggleGenHistory, toggleCommentMode, onToggleFullscreen]
  )

  const handleLogout = useCallback(async () => {
    await logout()
    navigate("/login")
  }, [logout, navigate])

  const avatarMenuOpen = activePanel === "avatar" || activePanel === "nav"

  const navHoverOpenTimer = useRef(null)
  const navHoverCloseTimer = useRef(null)
  const NAV_HOVER_OPEN_MS = 140
  const NAV_HOVER_CLOSE_MS = 200

  const clearNavHoverTimers = useCallback(() => {
    if (navHoverOpenTimer.current) {
      clearTimeout(navHoverOpenTimer.current)
      navHoverOpenTimer.current = null
    }
    if (navHoverCloseTimer.current) {
      clearTimeout(navHoverCloseTimer.current)
      navHoverCloseTimer.current = null
    }
  }, [])

  useEffect(() => () => clearNavHoverTimers(), [clearNavHoverTimers])

  const toggleAvatarMenu = useCallback(() => {
    setActivePanel((cur) => (cur === "avatar" || cur === "nav" ? null : "avatar"))
  }, [])

  const toggleNavFlyout = useCallback(() => {
    clearNavHoverTimers()
    setActivePanel((cur) => (cur === "nav" ? "avatar" : "nav"))
  }, [clearNavHoverTimers])

  const handleNavItemEnter = useCallback(() => {
    clearNavHoverTimers()
    if (activePanel === "nav") return
    navHoverOpenTimer.current = setTimeout(() => {
      setActivePanel((cur) => (cur === "avatar" || cur === "nav" ? "nav" : cur))
    }, NAV_HOVER_OPEN_MS)
  }, [activePanel, clearNavHoverTimers])

  const handleNavItemLeave = useCallback(() => {
    clearNavHoverTimers()
    if (activePanel !== "nav") return
    navHoverCloseTimer.current = setTimeout(() => {
      setActivePanel((cur) => (cur === "nav" ? "avatar" : cur))
    }, NAV_HOVER_CLOSE_MS)
  }, [activePanel, clearNavHoverTimers])

  return (
    <div className="clt-toolbar" ref={toolbarRef} onPointerDown={(e) => e.stopPropagation()}>
      <div className="clt-top">
        <CltItemWrap label={t("canvas.toolbar.addNode")}>
          <button
            className={`clt-btn clt-btn--featured clt-add-btn${activePanel === "add" ? " clt-btn--active" : ""}`}
            onClick={() => toggle("add")}
          >
            <PlusIcon />
          </button>
          {activePanel === "add" && (
            <AddMenuPanel t={t} onSelect={onAddNodeOfType} onUploadImage={onUploadImage} onClose={() => setActivePanel(null)} />
          )}
        </CltItemWrap>

        {TOOLBAR_ITEMS.map(({ id, Icon, labelKey, action, dynamicLabel }) => {
          const isItemActive =
            activePanel === id
            || (id === "assets" && assetLibraryOpen)
            || (id === "history" && genHistoryOpen)
            || (id === "comment" && commentMode)
            || (id === "fullscreen" && isFullscreen)
          return (
          <CltItemWrap
            key={id}
            label={dynamicLabel && isFullscreen ? t("canvas.toolbar.exitFullscreen") : t(labelKey)}
            className={id === "comment" ? "clt-item-wrap--comment" : ""}
          >
            <button
              className={`clt-btn${isItemActive ? " clt-btn--active" : ""}`}
              onClick={() => handleAction(action)}
            >
              {id === "fullscreen" ? <Icon exit={isFullscreen} /> : <Icon />}
              {id === "comment" && hasUnreadComments && (
                <span className="clt-comment-unread-dot" aria-hidden />
              )}
            </button>
          </CltItemWrap>
          )
        })}
      </div>

      <div className="clt-bottom">
        <CltItemWrap label={t("canvas.toolbar.account")}>
          <button
            className={`clt-avatar-btn${avatarMenuOpen ? " clt-avatar-btn--open" : ""}`}
            onClick={toggleAvatarMenu}
          >
            {avatarUrl ? (
              <span className="clt-avatar-img" style={{ backgroundImage: `url(${avatarUrl})` }} />
            ) : avatarLetter}
          </button>
          {avatarMenuOpen && (
            <div className="clt-avatar-menu clt-avatar-menu--rich">
              <div className="clt-menu-profile">
                <div
                  className="clt-menu-avatar-lg"
                  style={avatarUrl ? { backgroundImage: `url(${avatarUrl})` } : undefined}
                >
                  {!avatarUrl && avatarLetter}
                </div>
                <div className="clt-menu-profile-text">
                  <span className="clt-menu-username">{displayName || user?.username}</span>
                  <span className="clt-menu-email">{user?.email || ""}</span>
                </div>
              </div>
              {quotaText && (
                <button
                  type="button"
                  className="clt-menu-quota nodrag nopan"
                  title={t("canvas.toolbar.quota")}
                >
                  <span className="clt-menu-quota-main">
                    <IconCredit />
                    <span className="clt-menu-quota-num">{quotaText}</span>
                  </span>
                  <span className="clt-menu-quota-upgrade">{t("canvas.toolbar.upgradePro")}</span>
                </button>
              )}
              <div className="clt-menu-divider" />
              <button
                type="button"
                className="clt-menu-item"
                onClick={() => { setProfileModalOpen(true); setActivePanel(null) }}
              >
                <span className="clt-menu-icon"><LineIcon name="user" size={16} /></span>
                {t("canvas.toolbar.accountManage")}
              </button>
              {isAdmin && (
                <button
                  type="button"
                  className="clt-menu-item"
                  onClick={() => { navigate("/admin"); setActivePanel(null) }}
                >
                  <span className="clt-menu-icon"><LineIcon name="settings" size={16} /></span>
                  {t("canvas.toolbar.admin")}
                </button>
              )}
              <div
                className="clt-menu-item--has-flyout"
                onMouseEnter={handleNavItemEnter}
                onMouseLeave={handleNavItemLeave}
              >
                <button
                  type="button"
                  className={`clt-menu-item${activePanel === "nav" ? " clt-menu-item--active" : ""}`}
                  onClick={toggleNavFlyout}
                >
                  <span className="clt-menu-icon"><NavModeIcon /></span>
                  {t("canvas.toolbar.nav")}
                </button>
                {activePanel === "nav" && (
                  <CanvasNavModePanel
                    t={t}
                    mode={canvasNavMode}
                    onSelect={(next) => {
                      setCanvasNavMode(next)
                      setActivePanel(null)
                    }}
                  />
                )}
              </div>
              <button
                type="button"
                className="clt-menu-item"
                onClick={(e) => { toggleThemeWithTransition(e); setActivePanel(null) }}
              >
                <span className="clt-menu-icon">
                  <LineIcon name="sun" size={16} />
                </span>
                {theme === "dark" ? t("canvas.topbar.themeLight") : t("canvas.topbar.themeDark")}
              </button>
              <div className="clt-menu-divider" />
              <div className="clt-menu-foot">
                <div className="clt-menu-version">{APP_VERSION}</div>
                <button type="button" className="clt-menu-item clt-menu-logout" onClick={handleLogout}>
                  <span className="clt-menu-icon"><LineIcon name="logout" size={16} /></span>
                  {t("profile.logout")}
                </button>
              </div>
            </div>
          )}
        </CltItemWrap>
      </div>
    </div>
  )
}

export function useGenHistory() {
  return { read: readGenHistory, push: pushGenHistory }
}
