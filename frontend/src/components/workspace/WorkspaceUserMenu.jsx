import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../../contexts/AuthContext"
import { useCanvasStore, useTeamStore } from "../../stores"
import { LineIcon } from "../icons/LineIcons"
import TeamAvatar from "./TeamAvatar"
import CreateTeamModal from "./CreateTeamModal"
import MenuFlyoutPortal from "./MenuFlyoutPortal"
import { showDevNotice } from "../common/ProductNoticeModal"
import { useLocale } from "../../utils/locale"
import {
  MENU_FLYOUT_CLOSE_MS,
  MENU_FLYOUT_OPEN_MS,
} from "../../utils/menuFlyoutTiming"
import "./WorkspaceUserMenu.css"

const LANG_OPTIONS = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en", label: "English" },
]

const HELP_LINKS = [
  { id: "feedback", label: "问题反馈", icon: "feedback" },
  { id: "updates", label: "最近更新", icon: "doc", chevron: true },
  { id: "changelog", label: "更新日志", icon: "doc", external: true },
  { id: "manual", label: "产品使用手册", icon: "book", external: true },
]

const HELP_LEGAL = [
  { id: "terms", label: "用户服务协议" },
  { id: "privacy", label: "隐私政策" },
  { id: "ai-rules", label: "AI功能使用规范" },
]

function ChevronRight() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M5 3.5 8.5 7 5 10.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M3.5 8.2 6.4 11 12.5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function WorkspaceUserMenu({
  open,
  onClose,
  anchorRef,
  displayName,
  avatarUrl,
  notifyUnread = 0,
  onOpenNotify,
  onOpenJoinTeam,
  onMenuMouseEnter,
  onMenuMouseLeave,
  onSubmenuLatch,
}) {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { locale, t, setLanguage } = useLocale()
  const openProfileModal = useCanvasStore((s) => s.openProfileModal)
  const allTeams = useTeamStore((s) => s.allTeams)
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const ownedTeam = useTeamStore((s) => s.ownedTeam)
  const setActiveTeamId = useTeamStore((s) => s.setActiveTeamId)
  const switchToPersonal = useTeamStore((s) => s.switchToPersonal)

  const menuRef = useRef(null)
  const menuInnerRef = useRef(null)
  const spaceAnchorRef = useRef(null)
  const langAnchorRef = useRef(null)
  const helpAnchorRef = useRef(null)
  const flyoutTimerRef = useRef(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [activeFlyout, setActiveFlyout] = useState(null)

  const clearFlyoutTimer = () => {
    if (flyoutTimerRef.current) clearTimeout(flyoutTimerRef.current)
  }

  const openFlyout = (id) => {
    clearFlyoutTimer()
    setActiveFlyout(id)
    onSubmenuLatch?.(true)
    onMenuMouseEnter?.()
  }

  const scheduleFlyoutOpen = (id) => {
    clearFlyoutTimer()
    flyoutTimerRef.current = setTimeout(() => openFlyout(id), MENU_FLYOUT_OPEN_MS)
  }

  const scheduleFlyoutClose = () => {
    clearFlyoutTimer()
    flyoutTimerRef.current = setTimeout(() => {
      setActiveFlyout(null)
      onSubmenuLatch?.(false)
    }, MENU_FLYOUT_CLOSE_MS)
  }

  const flyoutTriggerProps = (id) => ({
    onMouseEnter: () => {
      clearFlyoutTimer()
      if (activeFlyout === id) return
      if (activeFlyout) {
        setActiveFlyout(id)
        onSubmenuLatch?.(true)
        onMenuMouseEnter?.()
      } else {
        scheduleFlyoutOpen(id)
      }
    },
    onMouseLeave: scheduleFlyoutClose,
  })

  const flyoutPanelProps = {
    onMouseEnter: clearFlyoutTimer,
    onMouseLeave: scheduleFlyoutClose,
  }

  const closeFlyout = () => {
    clearFlyoutTimer()
    setActiveFlyout(null)
    onSubmenuLatch?.(false)
  }

  const dismissFlyout = () => {
    clearFlyoutTimer()
    if (activeFlyout) closeFlyout()
  }

  const plainItemHover = {
    onMouseEnter: dismissFlyout,
  }

  const flyoutAnchorRef =
    activeFlyout === "space" ? spaceAnchorRef
      : activeFlyout === "lang" ? langAnchorRef
        : activeFlyout === "help" ? helpAnchorRef
          : null

  const flyoutWidth =
    activeFlyout === "space" ? 272
      : activeFlyout === "lang" ? 172
        : activeFlyout === "help" ? 232
          : 240

  const handleMenuMouseLeave = (e) => {
    const next = e.relatedTarget
    if (next?.closest?.(".wum-flyout-portal") || next?.closest?.(".wum-flyout-bridge")) return
    scheduleFlyoutClose()
    if (!activeFlyout) onMenuMouseLeave?.()
  }

  useEffect(() => () => clearFlyoutTimer(), [])

  useEffect(() => {
    const onTeamChange = () => void useTeamStore.getState().refreshTeams()
    window.addEventListener("team-context-changed", onTeamChange)
    return () => window.removeEventListener("team-context-changed", onTeamChange)
  }, [])

  useEffect(() => {
    if (!open) {
      closeFlyout()
      return undefined
    }
    void useTeamStore.getState().refreshTeams()
    const onDoc = (e) => {
      const inMenu = menuRef.current?.contains(e.target)
      const inAnchor = anchorRef?.current?.contains(e.target)
      const inFlyout = e.target.closest?.(".wum-flyout-portal")
        || e.target.closest?.(".wum-flyout-bridge")
      if (!inMenu && !inAnchor && !inFlyout) onClose?.()
    }
    const onKey = (e) => { if (e.key === "Escape") onClose?.() }
    document.addEventListener("mousedown", onDoc)
    window.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDoc)
      window.removeEventListener("keydown", onKey)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, onClose, anchorRef])

  const activeTeam = activeTeamId
    ? allTeams.find((t) => t.id === activeTeamId)
    : null
  const contextLabel = activeTeam?.name || displayName

  const q = user?.quota
  const isUnlimited = q?.image_limit < 0
  const creditNum = q
    ? (isUnlimited ? "∞" : String(Math.max(0, (q.image_limit ?? 0) - (q.image_used ?? 0))))
    : "0"

  const langLabel = LANG_OPTIONS.find((o) => o.value === locale)?.label || "简体中文"

  const placeholder = (label) => {
    showDevNotice(label)
  }

  const handleLogout = async () => {
    onClose?.()
    await logout()
    navigate("/login")
  }

  const selectPersonal = () => {
    switchToPersonal()
    window.dispatchEvent(new CustomEvent("team-context-changed"))
    closeFlyout()
    onClose?.()
  }

  const selectTeam = (teamId) => {
    setActiveTeamId(teamId)
    window.dispatchEvent(new CustomEvent("team-context-changed"))
    closeFlyout()
    onClose?.()
  }

  const openTeamSettings = (teamId, e) => {
    e.stopPropagation()
    if (teamId) setActiveTeamId(teamId)
    openProfileModal("team-settings")
    closeFlyout()
    onClose?.()
  }

  const openBenefits = () => {
    openProfileModal("team-benefits")
    onClose?.()
  }

  const handleCreateTeam = () => {
    if (ownedTeam) {
      window.alert(t("menu.teamOwnedAlert", { name: ownedTeam.name }))
      return
    }
    setCreateOpen(true)
  }

  const pickLanguage = (value) => {
    setLanguage(value)
    closeFlyout()
  }

  if (!open) return null

  return (
    <>
      <div
        ref={menuRef}
        className="wum-menu"
        role="menu"
        onMouseEnter={onMenuMouseEnter}
        onMouseLeave={handleMenuMouseLeave}
      >
        <div className="wum-menu-inner" ref={menuInnerRef}>
          <div className="wum-head wum-head--top">
            <div className="wum-avatar wum-avatar--lg">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" draggable={false} />
              ) : (
                (displayName[0] || "U").toUpperCase()
              )}
            </div>
            <div className="wum-meta">
              <div className="wum-name">{displayName}</div>
              <div className="wum-email">{user?.email || `UID ${user?.id ?? "—"}`}</div>
            </div>
          </div>

          <div
            ref={spaceAnchorRef}
            className="wum-active-block"
            {...flyoutTriggerProps("space")}
          >
            <button type="button" className={`wum-active-row${activeFlyout === "space" ? " is-open" : ""}`}>
              {activeTeam ? (
                <TeamAvatar teamId={activeTeam.id} name={activeTeam.name} size={28} />
              ) : (
                <span className="wum-space-avatar wum-space-avatar--personal wum-space-avatar--sm">
                  {(displayName[0] || "U").toUpperCase()}
                </span>
              )}
              <span className="wum-active-text">
                <span className="wum-active-label">{contextLabel}</span>
                <span className={`wum-space-kind${activeTeam ? " wum-space-kind--team" : " wum-space-kind--personal"}`}>
                  {activeTeam ? t("menu.spaceTeam") : t("menu.spacePersonal")}
                </span>
              </span>
              <ChevronRight />
            </button>
          </div>

          <button type="button" className="wum-quota-card" onClick={openBenefits} {...plainItemHover}>
            <div className="wum-quota-top">
              <span className="wum-quota-icon-wrap">
                <LineIcon name="style" size={16} />
              </span>
              <span className="wum-quota-num">{creditNum}</span>
              <span className="wum-quota-badge">FREE</span>
            </div>
            <div className="wum-quota-row">
              <span className="wum-quota-label">
                {isUnlimited ? t("menu.unlimitedQuota") : t("menu.remainingCredits")}
                <span className="wum-quota-hint-icon" title="额度说明">?</span>
              </span>
              {isUnlimited && <span className="wum-infinity">∞</span>}
            </div>
            <div className="wum-quota-bar">
              <div
                className="wum-quota-fill"
                style={{
                  width: isUnlimited
                    ? "100%"
                    : `${Math.min(100, ((q?.image_used ?? 0) / Math.max(1, q?.image_limit ?? 1)) * 100)}%`,
                }}
              />
            </div>
          </button>

          <div className="wum-team-row" {...plainItemHover}>
            <button type="button" className="wum-team-btn" onClick={() => onOpenJoinTeam?.()}>
              {t("menu.joinTeam")}
            </button>
            <span className="wum-team-sep" aria-hidden />
            <button type="button" className="wum-team-btn" onClick={handleCreateTeam}>
              {t("menu.createTeam")}
            </button>
          </div>

          <div className="wum-divider" />

          <button
            type="button"
            className="wum-item"
            {...plainItemHover}
            onClick={() => { openProfileModal("personal"); onClose?.() }}
          >
            <LineIcon name="agent" size={18} />
            <span className="wum-item-label">{t("menu.personalHome")}</span>
          </button>

          <div
            ref={langAnchorRef}
            className="wum-flyout-block"
            {...flyoutTriggerProps("lang")}
          >
            <button
              type="button"
              className={`wum-item${activeFlyout === "lang" ? " wum-item--open" : ""}`}
            >
              <LineIcon name="book" size={18} />
              <span className="wum-item-label">{langLabel}</span>
              <ChevronRight />
            </button>
          </div>

          <button
            type="button"
            className="wum-item wum-item--notify"
            {...plainItemHover}
            onClick={() => { onOpenNotify?.(); onClose?.() }}
          >
            <LineIcon name="bell" size={18} />
            <span className="wum-item-label">{t("menu.notifications")}</span>
            {notifyUnread > 0 && <span className="wum-notify-dot" aria-hidden />}
          </button>

          <button type="button" className="wum-item" {...plainItemHover} onClick={() => placeholder(t("menu.connectAgent"))}>
            <LineIcon name="agent" size={18} />
            <span className="wum-item-label">{t("menu.connectAgent")}</span>
          </button>

          <button type="button" className="wum-item" {...plainItemHover} onClick={() => placeholder(t("menu.featureWish"))}>
            <LineIcon name="sprout" size={18} />
            <span className="wum-item-label">{t("menu.featureWish")}</span>
          </button>

          <div
            ref={helpAnchorRef}
            className="wum-flyout-block"
            {...flyoutTriggerProps("help")}
          >
            <button
              type="button"
              className={`wum-item${activeFlyout === "help" ? " wum-item--open" : ""}`}
            >
              <LineIcon name="help" size={18} />
              <span className="wum-item-label">{t("menu.help")}</span>
              <ChevronRight />
            </button>
          </div>

          <button type="button" className="wum-item wum-item--logout" {...plainItemHover} onClick={handleLogout}>
            <LineIcon name="logout" size={18} />
            <span className="wum-item-label">{t("menu.logout")}</span>
          </button>
        </div>
      </div>

      <MenuFlyoutPortal
        open={!!activeFlyout}
        anchorRef={flyoutAnchorRef}
        menuAlignRef={menuInnerRef}
        width={flyoutWidth}
        className={
          activeFlyout === "space" ? "wum-space-flyout"
            : activeFlyout === "lang" ? "wum-lang-flyout"
              : "wum-help-flyout"
        }
        {...flyoutPanelProps}
      >
        {activeFlyout === "space" && (
          <>
            <button
              type="button"
              className={`wum-space-item${!activeTeamId ? " is-active" : ""}`}
              onClick={selectPersonal}
            >
              <span className="wum-space-avatar wum-space-avatar--personal">
                {(displayName[0] || "U").toUpperCase()}
              </span>
              <span className="wum-space-text">
                <span className="wum-space-label">{displayName}</span>
                <span className="wum-space-kind wum-space-kind--personal">{t("menu.spacePersonal")}</span>
              </span>
              {!activeTeamId && <span className="wum-space-check"><CheckIcon /></span>}
            </button>
            {allTeams.map((team) => (
              <div
                key={team.id}
                className={`wum-space-item${activeTeamId === team.id ? " is-active" : ""}`}
                role="button"
                tabIndex={0}
                onClick={() => selectTeam(team.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    selectTeam(team.id)
                  }
                }}
              >
                <TeamAvatar teamId={team.id} name={team.name} size={32} />
                <span className="wum-space-text">
                  <span className="wum-space-label">{team.name}</span>
                  <span className="wum-space-kind wum-space-kind--team">{t("menu.spaceTeam")}</span>
                </span>
                <span className="wum-space-actions">
                  <span
                    className="wum-space-gear"
                    role="button"
                    tabIndex={0}
                    onClick={(e) => openTeamSettings(team.id, e)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        e.stopPropagation()
                        openTeamSettings(team.id, e)
                      }
                    }}
                    title={t("menu.teamSettings")}
                    aria-label={t("menu.teamSettings")}
                  >
                    <LineIcon name="settings" size={14} />
                  </span>
                  {activeTeamId === team.id && (
                    <span className="wum-space-check"><CheckIcon /></span>
                  )}
                </span>
              </div>
            ))}
          </>
        )}
        {activeFlyout === "lang" && LANG_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={`wum-lang-item${locale === opt.value ? " is-active" : ""}`}
            onClick={() => pickLanguage(opt.value)}
          >
            {opt.label}
            {locale === opt.value && <CheckIcon />}
          </button>
        ))}
        {activeFlyout === "help" && (
          <>
            {HELP_LINKS.map((item) => (
              <button
                key={item.id}
                type="button"
                className="wum-help-item"
                onClick={() => placeholder(item.label)}
              >
                <span className="wum-help-icon"><LineIcon name={item.icon} size={16} /></span>
                <span className="wum-help-text">{item.label}</span>
                {item.chevron && <ChevronRight />}
                {item.external && <span className="wum-ext">↗</span>}
              </button>
            ))}
            <div className="wum-help-divider" />
            {HELP_LEGAL.map((item) => (
              <button
                key={item.id}
                type="button"
                className="wum-help-legal"
                onClick={() => placeholder(item.label)}
              >
                {item.label}
              </button>
            ))}
          </>
        )}
      </MenuFlyoutPortal>

      <CreateTeamModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  )
}
