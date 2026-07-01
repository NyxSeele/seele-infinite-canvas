import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../../contexts/AuthContext"
import { useCanvasStore } from "../../stores"
import { readUserAvatarRaw } from "../../utils/canvas/userAvatar"
import { saveProfileToServer } from "../../utils/canvas/profileSync"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import TeamBenefitsPanel from "../workspace/TeamBenefitsPanel"
import TeamSettingsPanel from "../workspace/TeamSettingsPanel"
import BillingRecordsPanel from "../workspace/BillingRecordsPanel"
import AvatarCropModal from "../workspace/AvatarCropModal"
import { useLocale } from "../../utils/locale"
import { useThemeTransition } from "../../hooks/useThemeTransition"
import pkg from "../../../package.json"
import "./CanvasProfileModal.css"

const PREFS_KEY = "canvas-user-profile-prefs"
const APP_VERSION = `v${pkg.version}`

function buildNavGroups(t) {
  return [
    {
      title: t("profile.nav.benefitsGroup"),
      items: [
        { id: "team-benefits", label: t("profile.nav.benefits") },
        { id: "billing-records", label: t("profile.nav.billing") },
      ],
    },
    {
      title: t("profile.nav.settingsGroup"),
      items: [{ id: "personal", label: t("profile.nav.personal") }],
    },
    {
      title: "",
      items: [{ id: "team-settings", label: t("profile.nav.team") }],
    },
  ]
}

function readPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}")
  } catch {
    return {}
  }
}

function writePrefs(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
    window.dispatchEvent(new CustomEvent("canvas-prefs-changed"))
  } catch {
    /* ignore */
  }
}

const VersionIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
    <path d="M7 1.5v2M7 10.5v2M2.5 7h2M9.5 7h2M4.1 4.1l1.4 1.4M8.5 8.5l1.4 1.4M4.1 9.9l1.4-1.4M8.5 5.5l1.4-1.4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
    <circle cx="7" cy="7" r="2.2" stroke="currentColor" strokeWidth="1.1"/>
  </svg>
)

const LogoutIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
    <path d="M5.5 3H3.5a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
    <path d="M9 5l2.5 2L9 9M5.5 7H11.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

function tabTitle(t, tab) {
  if (tab === "personal") return t("profile.nav.personal")
  if (tab === "team-benefits") return t("profile.nav.benefits")
  if (tab === "team-settings") return t("profile.nav.team")
  if (tab === "billing-records") return t("profile.nav.billing")
  return t("profile.nav.account")
}

export default function CanvasProfileModal() {
  const open = useCanvasStore((s) => s.profileModalOpen)
  const tab = useCanvasStore((s) => s.profileModalTab)
  const setOpen = useCanvasStore((s) => s.setProfileModalOpen)
  const setTab = useCanvasStore((s) => s.setProfileModalTab)
  const theme = useCanvasStore((s) => s.theme)
  const { toggleThemeWithTransition } = useThemeTransition()
  const { user, logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const { t } = useLocale()
  const navGroups = buildNavGroups(t)

  const [bio, setBio] = useState("")
  const [language, setLanguage] = useState("zh-CN")
  const [displayName, setDisplayName] = useState("")
  const [avatarUrl, setAvatarUrl] = useState("")
  const [cropOpen, setCropOpen] = useState(false)
  const [cropSrc, setCropSrc] = useState("")
  const [saveToast, setSaveToast] = useState("")
  const [saving, setSaving] = useState(false)
  const [avatarRemoved, setAvatarRemoved] = useState(false)
  const avatarInputRef = useRef(null)
  const toastTimerRef = useRef(null)
  const ignoreBackdropCloseRef = useRef(false)

  useEffect(() => {
    if (!open) return
    const prefs = readPrefs()
    setBio(user?.bio || prefs.bio || "")
    setLanguage(prefs.language || "zh-CN")
    setDisplayName(user?.display_name || prefs.displayName || user?.username || "")
    const raw = user?.avatar_url || readUserAvatarRaw()
    if (!raw) {
      setAvatarUrl("")
    } else if (raw.startsWith("data:") || raw.startsWith("blob:")) {
      setAvatarUrl(raw)
    } else {
      setAvatarUrl(ensureMediaUrl(raw))
    }
    setAvatarRemoved(false)
  }, [open, user])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      writePrefs({ bio, language, displayName: displayName.trim() || user?.username || "" })
      await saveProfileToServer({
        displayName: displayName.trim() || user?.username || "",
        bio,
        avatarUrl: avatarRemoved ? "" : avatarUrl,
        removeAvatar: avatarRemoved,
      })
      await refreshUser()
      setSaveToast(t("profile.saved"))
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
      toastTimerRef.current = setTimeout(() => setSaveToast(""), 2200)
    } catch (err) {
      console.error(err)
      setSaveToast(t("profile.saveFailed"))
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
      toastTimerRef.current = setTimeout(() => setSaveToast(""), 2800)
    } finally {
      setSaving(false)
    }
  }, [bio, language, displayName, avatarUrl, avatarRemoved, user?.username, refreshUser, t])

  useEffect(() => () => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
  }, [])

  const armBackdropCloseGuard = useCallback((ms = 500) => {
    ignoreBackdropCloseRef.current = true
    window.setTimeout(() => {
      ignoreBackdropCloseRef.current = false
    }, ms)
  }, [])

  const handleAvatarPick = useCallback(() => {
    armBackdropCloseGuard(700)
    avatarInputRef.current?.click()
  }, [armBackdropCloseGuard])

  const handleAvatarChange = useCallback((e) => {
    const file = e.target.files?.[0]
    if (!file) return
    armBackdropCloseGuard(700)
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setCropSrc(reader.result)
        setCropOpen(true)
      }
    }
    reader.readAsDataURL(file)
    e.target.value = ""
  }, [armBackdropCloseGuard])

  const handleBackdropPointerDown = useCallback((e) => {
    if (e.target !== e.currentTarget) return
    if (cropOpen || ignoreBackdropCloseRef.current) return
    setOpen(false)
  }, [cropOpen, setOpen])

  const handleCropConfirm = useCallback((dataUrl) => {
    setAvatarUrl(dataUrl)
    setAvatarRemoved(false)
    setCropOpen(false)
    setCropSrc("")
  }, [])

  const handleCropCancel = useCallback(() => {
    setCropOpen(false)
    setCropSrc("")
  }, [])

  const handleRemoveAvatar = useCallback(() => {
    setAvatarUrl("")
    setAvatarRemoved(true)
  }, [])

  const handleLogout = useCallback(async () => {
    setOpen(false)
    await logout()
    navigate("/login")
  }, [logout, navigate, setOpen])

  if (!open && !cropOpen) return null

  const avatarLetter = user?.username?.[0]?.toUpperCase() || "?"

  return (
    <>
    {open && (
    <div className="cps-modal-backdrop nodrag nopan" onPointerDown={handleBackdropPointerDown}>
      <div
        className="cps-modal"
        onPointerDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t("profile.nav.account")}
      >
        <aside className="cps-modal-nav">
          <div className="cps-modal-nav-title">{t("profile.nav.account")}</div>
          {navGroups.map((group) => (
            <div key={group.title} className="cps-nav-group">
              {group.title ? <div className="cps-nav-group-title">{group.title}</div> : null}
              <div className="cps-nav-group-list">
                {group.items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`cps-modal-nav-item${tab === item.id ? " cps-modal-nav-item--active" : ""}`}
                    onClick={() => setTab(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <div className="cps-modal-nav-foot">
            <div className="cps-modal-version">
              <VersionIcon />
              <span>{APP_VERSION}</span>
            </div>
            <button type="button" className="cps-modal-logout" onClick={handleLogout}>
              <LogoutIcon />
              {t("profile.logout")}
            </button>
          </div>
        </aside>

        <div className="cps-modal-body">
          {saveToast && tab === "personal" && (
            <div className="cps-save-toast" role="status">
              {saveToast}
            </div>
          )}
          <header className="cps-modal-head">
            <h2>{tabTitle(t, tab)}</h2>
            <button type="button" className="cps-modal-close" onClick={() => setOpen(false)}>×</button>
          </header>

          <div className="cps-tab-stage">
          {tab === "personal" && (
            <div className="cps-tab-panel cps-tab-panel--personal">
              <section className="cps-avatar-section">
                <div
                  className="cps-profile-avatar cps-profile-avatar--editable"
                  style={avatarUrl ? { backgroundImage: `url(${avatarUrl})` } : undefined}
                >
                  {!avatarUrl && avatarLetter}
                </div>
                <div className="cps-avatar-actions">
                  <span className="cps-field-label">{t("profile.avatar")}</span>
                  <div className="cps-avatar-btns">
                    <button
                      type="button"
                      className="cps-btn cps-btn--ghost cps-btn--sm"
                      onClick={handleAvatarPick}
                    >
                      {t("profile.uploadAvatar")}
                    </button>
                    {avatarUrl && (
                      <button
                        type="button"
                        className="cps-btn cps-btn--ghost cps-btn--sm"
                        onClick={handleRemoveAvatar}
                      >
                        {t("profile.removeAvatar")}
                      </button>
                    )}
                  </div>
                  <input
                    ref={avatarInputRef}
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={handleAvatarChange}
                  />
                </div>
              </section>

              <label className="cps-field">
                <span className="cps-field-label">{t("profile.displayName")}</span>
                <input
                  className="cps-input"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder={user?.username || t("profile.displayNamePh")}
                />
              </label>

              <label className="cps-field">
                <span className="cps-field-label">{t("profile.bio")}</span>
                <textarea
                  className="cps-textarea"
                  rows={4}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder={t("profile.bioPh")}
                />
              </label>

              <label className="cps-field">
                <span className="cps-field-label">{t("profile.email")}</span>
                <input className="cps-input" value={user?.email || ""} readOnly />
              </label>

              <label className="cps-field">
                <span className="cps-field-label">{t("profile.language")}</span>
                <select
                  className="cps-input"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  <option value="zh-CN">简体中文</option>
                  <option value="en">English</option>
                </select>
              </label>

              <div className="cps-field cps-field--row">
                <span className="cps-field-label">{t("profile.canvasTheme")}</span>
                <button type="button" className="cps-theme-toggle" onClick={(e) => toggleThemeWithTransition(e)}>
                  {theme === "dark" ? t("profile.themeDark") : t("profile.themeLight")}
                </button>
              </div>

              <footer className="cps-modal-foot">
                <button type="button" className="cps-btn cps-btn--ghost" onClick={() => setOpen(false)}>
                  {t("profile.close")}
                </button>
                <button
                  type="button"
                  className="cps-btn cps-btn--primary"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? t("profile.saving") : t("profile.save")}
                </button>
              </footer>
            </div>
          )}

          {tab === "team-benefits" && (
            <div className="cps-tab-panel">
              <TeamBenefitsPanel />
            </div>
          )}
          {tab === "team-settings" && (
            <div className="cps-tab-panel">
              <TeamSettingsPanel />
            </div>
          )}
          {tab === "billing-records" && (
            <div className="cps-tab-panel cps-tab-panel--billing">
              <BillingRecordsPanel />
            </div>
          )}
          </div>
        </div>
      </div>
    </div>
    )}
    <AvatarCropModal
      open={cropOpen}
      imageSrc={cropSrc}
      onConfirm={handleCropConfirm}
      onCancel={handleCropCancel}
    />
    </>
  )
}
