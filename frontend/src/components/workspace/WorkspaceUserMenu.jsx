import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useNavigate, useLocation } from "react-router-dom"
import { useAuth } from "../../contexts/AuthContext"
import { useCanvasStore, useTeamStore } from "../../stores"
import { LineIcon } from "../icons/LineIcons"
import CreateTeamModal from "./CreateTeamModal"
import MenuFlyoutPortal from "./MenuFlyoutPortal"
import IdentityInfoPopover from "./IdentityInfoPopover"
import { showDevNotice } from "../common/ProductNoticeModal"
import { useLocale } from "../../utils/locale"
import { navigateWithReturn } from "../../utils/navReturn"
import { restartOnboarding } from "../Onboarding/tourSteps"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import {
  MENU_FLYOUT_CLOSE_MS,
  MENU_FLYOUT_OPEN_MS,
} from "../../utils/menuFlyoutTiming"
import "./WorkspaceUserMenu.css"

const MENU_WIDTH = 300

const LANG_OPTIONS = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en", label: "English" },
]

const HELP_LINKS = [
  { id: "feedback", label: "问题反馈", icon: "feedback" },
  { id: "updates", label: "最近更新", icon: "doc" },
  { id: "changelog", label: "更新日志", icon: "doc", external: true },
  { id: "manual", label: "产品使用手册", icon: "book", external: true },
]

const HELP_LEGAL = [
  { id: "terms", label: "用户服务协议" },
  { id: "privacy", label: "隐私政策" },
  { id: "ai-rules", label: "AI功能使用规范" },
]

export default function WorkspaceUserMenu({
  open,
  onClose,
  anchorRef,
  displayName,
  avatarUrl,
  onAvatarError,
  notifyUnread = 0,
  onOpenNotify,
  onOpenJoinTeam,
  onMenuMouseEnter,
  onMenuMouseLeave,
  onSubmenuLatch,
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()
  const { locale, t, setLanguage } = useLocale()
  const openProfileModal = useCanvasStore((s) => s.openProfileModal)
  const allTeams = useTeamStore((s) => s.allTeams)
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const ownedTeam = useTeamStore((s) => s.ownedTeam)

  const menuRef = useRef(null)
  const menuInnerRef = useRef(null)
  const identityAnchorRef = useRef(null)
  const langAnchorRef = useRef(null)
  const helpAnchorRef = useRef(null)
  const flyoutTimerRef = useRef(null)
  const identityTimerRef = useRef(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [activeFlyout, setActiveFlyout] = useState(null)
  const [identityPopoverOpen, setIdentityPopoverOpen] = useState(false)
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 })

  const updateMenuPosition = useCallback(() => {
    const el = anchorRef?.current
    if (!el) return false
    const rect = el.getBoundingClientRect()
    if (
      rect.bottom < 0
      || rect.top > window.innerHeight
      || rect.right < 0
      || rect.left > window.innerWidth
    ) {
      return false
    }
    let left = rect.right - MENU_WIDTH
    if (left < 12) left = Math.max(12, rect.left)
    const top = rect.bottom + 10
    setMenuPos({ top, left })
    return true
  }, [anchorRef])

  useLayoutEffect(() => {
    if (!open) return undefined
    updateMenuPosition()
    const onReflow = () => updateMenuPosition()
    window.addEventListener("resize", onReflow)
    window.addEventListener("scroll", onReflow, true)
    return () => {
      window.removeEventListener("resize", onReflow)
      window.removeEventListener("scroll", onReflow, true)
    }
  }, [open, updateMenuPosition])

  const clearFlyoutTimer = () => {
    if (flyoutTimerRef.current) clearTimeout(flyoutTimerRef.current)
  }

  const clearIdentityTimer = () => {
    if (identityTimerRef.current) clearTimeout(identityTimerRef.current)
  }

  const closeIdentityPopover = () => {
    clearIdentityTimer()
    setIdentityPopoverOpen(false)
  }

  const openIdentityPopover = () => {
    clearIdentityTimer()
    clearFlyoutTimer()
    setActiveFlyout(null)
    setIdentityPopoverOpen(true)
    onSubmenuLatch?.(true)
    onMenuMouseEnter?.()
  }

  const scheduleIdentityClose = () => {
    clearIdentityTimer()
    identityTimerRef.current = setTimeout(() => {
      closeIdentityPopover()
    }, MENU_FLYOUT_CLOSE_MS)
  }

  const identityPopoverPanelProps = {
    onMouseEnter: clearIdentityTimer,
    onMouseLeave: scheduleIdentityClose,
  }

  const openFlyout = (id) => {
    clearFlyoutTimer()
    closeIdentityPopover()
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
  }

  const dismissFlyout = () => {
    clearFlyoutTimer()
    if (activeFlyout) closeFlyout()
    if (identityPopoverOpen) closeIdentityPopover()
  }

  const plainItemHover = {
    onMouseEnter: dismissFlyout,
  }

  const flyoutAnchorRef =
    activeFlyout === "lang" ? langAnchorRef
      : activeFlyout === "help" ? helpAnchorRef
        : null

  const flyoutWidth =
    activeFlyout === "lang" ? 172
      : activeFlyout === "help" ? 232
        : 240

  const handleMenuMouseLeave = (e) => {
    const next = e.relatedTarget
    if (
      next?.closest?.(".wum-flyout-portal")
      || next?.closest?.(".wum-flyout-bridge")
      || next?.closest?.(".wum-identity-popover")
      || next?.closest?.(".wum-identity-popover-bridge")
    ) return
    scheduleFlyoutClose()
    scheduleIdentityClose()
    if (!activeFlyout && !identityPopoverOpen) onMenuMouseLeave?.()
  }

  const themeClass = getThemePageClass()

  useEffect(() => () => {
    clearFlyoutTimer()
    clearIdentityTimer()
  }, [])

  useEffect(() => {
    const onTeamChange = () => useTeamStore.getState().scheduleRefreshTeams()
    window.addEventListener("team-context-changed", onTeamChange)
    return () => window.removeEventListener("team-context-changed", onTeamChange)
  }, [])

  useEffect(() => {
    if (!open) return
    if (identityPopoverOpen || activeFlyout) onSubmenuLatch?.(true)
    else onSubmenuLatch?.(false)
  }, [open, identityPopoverOpen, activeFlyout, onSubmenuLatch])

  useEffect(() => {
    if (!open) {
      closeFlyout()
      closeIdentityPopover()
      return undefined
    }
    void useTeamStore.getState().ensureTeamsLoaded()
    const onDoc = (e) => {
      const inMenu = menuRef.current?.contains(e.target)
      const inAnchor = anchorRef?.current?.contains(e.target)
      const inFlyout = e.target.closest?.(".wum-flyout-portal")
        || e.target.closest?.(".wum-flyout-bridge")
        || e.target.closest?.(".wum-identity-popover")
        || e.target.closest?.(".wum-identity-popover-bridge")
      const inCreateTeamModal = e.target.closest?.(".ctm-backdrop")
        || e.target.closest?.(".ctm-modal")
      if (!inMenu && !inAnchor && !inFlyout && !inCreateTeamModal) onClose?.()
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
  const identityLabel = activeTeam ? activeTeam.name : t("menu.spacePersonal")

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

  const menuPortal = open
    ? createPortal(
        <div
          ref={menuRef}
          className={`wum-menu wum-menu--portal ws-overlay-root ${themeClass}`}
          role="menu"
          style={{
            position: "fixed",
            top: menuPos.top,
            left: menuPos.left,
            width: MENU_WIDTH,
            zIndex: 530,
          }}
          onMouseEnter={onMenuMouseEnter}
          onMouseLeave={handleMenuMouseLeave}
        >
          <div className="wum-menu-inner" ref={menuInnerRef}>
          <div className="wum-head wum-head--top">
            <div className="wum-avatar wum-avatar--lg">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" draggable={false} onError={onAvatarError} />
              ) : (
                (displayName[0] || "U").toUpperCase()
              )}
            </div>
            <div className="wum-meta">
              <div className="wum-name">
                <span className="wum-name-text">{displayName}</span>
                <span
                  ref={identityAnchorRef}
                  className={`wum-identity-tag${identityPopoverOpen ? " is-open" : ""}`}
                  role="button"
                  tabIndex={0}
                  onMouseEnter={openIdentityPopover}
                  onMouseLeave={scheduleIdentityClose}
                  onClick={(e) => {
                    e.stopPropagation()
                    if (identityPopoverOpen) scheduleIdentityClose()
                    else openIdentityPopover()
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault()
                      if (identityPopoverOpen) scheduleIdentityClose()
                      else openIdentityPopover()
                    }
                  }}
                >
                  （{identityLabel}）
                </span>
              </div>
              <div className="wum-email">{user?.email || `UID ${user?.id ?? "—"}`}</div>
            </div>
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

          <button
            type="button"
            className="wum-item"
            {...plainItemHover}
            onClick={() => { onClose?.(); navigateWithReturn(navigate, location, "/team-files") }}
          >
            <LineIcon name="doc" size={18} />
            <span className="wum-item-label">团队文件</span>
          </button>

          <button
            type="button"
            className="wum-item"
            {...plainItemHover}
            onClick={() => { onClose?.(); navigateWithReturn(navigate, location, "/review-publish") }}
          >
            <LineIcon name="video" size={18} />
            <span className="wum-item-label">视频审阅</span>
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
            </button>
          </div>

          <button type="button" className="wum-item wum-item--logout" {...plainItemHover} onClick={handleLogout}>
            <LineIcon name="logout" size={18} />
            <span className="wum-item-label">{t("menu.logout")}</span>
          </button>
          </div>
        </div>,
        getThemePortalRoot()
      )
    : null

  return (
    <>
      {menuPortal}

      {open && (
      <MenuFlyoutPortal
        open={!!activeFlyout}
        anchorRef={flyoutAnchorRef}
        menuAlignRef={menuInnerRef}
        width={flyoutWidth}
        className={
          activeFlyout === "lang" ? "wum-lang-flyout"
            : activeFlyout === "help" ? "wum-help-flyout"
              : ""
        }
        {...flyoutPanelProps}
      >
        {activeFlyout === "lang" && LANG_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={`wum-lang-item${locale === opt.value ? " is-active" : ""}`}
            onClick={() => pickLanguage(opt.value)}
          >
            {opt.label}
            {locale === opt.value && (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
                <path d="M3.5 8.2 6.4 11 12.5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </button>
        ))}
        {activeFlyout === "help" && (
          <>
            <button
              type="button"
              className="wum-help-item"
              onClick={() => {
                onClose?.()
                restartOnboarding("ws")
              }}
            >
              <span className="wum-help-icon"><LineIcon name="help" size={16} /></span>
              <span className="wum-help-text">新手引导</span>
            </button>
            <div className="wum-help-divider" />
            {HELP_LINKS.map((item) => (
              <button
                key={item.id}
                type="button"
                className="wum-help-item"
                onClick={() => placeholder(item.label)}
              >
                <span className="wum-help-icon"><LineIcon name={item.icon} size={16} /></span>
                <span className="wum-help-text">{item.label}</span>
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
      )}

      <IdentityInfoPopover
        open={open && identityPopoverOpen}
        anchorRef={identityAnchorRef}
        themeClass={themeClass}
        {...identityPopoverPanelProps}
      >
        {activeTeam ? (
          <>
            <div className="wum-identity-detail-title">{activeTeam.name}</div>
            <div className="wum-identity-detail-line">
              {t("menu.identityMemberCount", { count: activeTeam.member_count ?? 0 })}
            </div>
            {activeTeam.my_role ? (
              <div className="wum-identity-detail-line">
                {t("menu.identityRole", { role: activeTeam.my_role })}
              </div>
            ) : null}
          </>
        ) : (
          <>
            <div className="wum-identity-detail-title">{displayName}</div>
            <div className="wum-identity-detail-line">{user?.email || `UID ${user?.id ?? "—"}`}</div>
            <div className="wum-identity-plan">
              <span className="wum-identity-plan-label">{t("menu.identityPlanFree")}</span>
              <span className="wum-quota-badge">FREE</span>
            </div>
            <div className="wum-identity-detail-line wum-identity-credits">
              {isUnlimited ? t("menu.unlimitedQuota") : `${t("menu.remainingCredits")} ${creditNum}`}
            </div>
          </>
        )}
      </IdentityInfoPopover>

      <CreateTeamModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
      />
    </>
  )
}
