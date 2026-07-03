import { useEffect, useState } from "react"
import { createTeamInviteLink, getTeamInviteLink } from "../../services/teamApi"
import { inviteExpiryLabel } from "../../utils/teamInviteLink"
import TeamInviteLinkSettingsModal from "./TeamInviteLinkSettingsModal"
import AnimatedModal from "../common/AnimatedModal"
import "./TeamInviteModal.css"

function CopyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="6" y="6" width="9" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M4 12V4.5A1.5 1.5 0 0 1 5.5 3H12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

export default function TeamInviteModal({ open, onClose, teamId, teamName }) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [linkKey, setLinkKey] = useState(0)
  const [url, setUrl] = useState("")
  const [settings, setSettings] = useState({ expiryDays: 7, quotaType: "unlimited" })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const applyInviteData = (data) => {
    const path = data?.url || (data?.token ? `/join-team?token=${data.token}` : "")
    const fullUrl = path.startsWith("http") ? path : `${window.location.origin}${path}`
    setUrl(fullUrl)
    setSettings(data?.settings || { expiryDays: 7, quotaType: "unlimited" })
  }

  useEffect(() => {
    if (!open || !teamId) return undefined
    let cancelled = false
    setLoading(true)
    setError("")
    setUrl("")
    getTeamInviteLink(teamId)
      .then((data) => {
        if (cancelled) return
        applyInviteData(data)
      })
      .catch((err) => {
        if (cancelled) return
        const detail = err?.response?.data?.detail
        setError(typeof detail === "string" ? detail : "加载邀请链接失败")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [open, teamId, linkKey])

  const handleCopy = async () => {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      window.prompt("复制邀请链接", url)
    }
  }

  return (
    <>
      <AnimatedModal
        open={open}
        onClose={onClose}
        overlayClass="tim-backdrop"
        modalClass="tim-modal"
      >
          <header className="tim-head">
            <div>
              <h2>邀请成员</h2>
              <p>
                分享此链接邀请朋友加入您的团队「{teamName || "团队"}」。
                他们加入后将立即获得团队资源访问权限。
              </p>
            </div>
            <button type="button" className="tim-close" onClick={onClose} aria-label="关闭">×</button>
          </header>

          <label className="tim-field">
            <span>邀请链接</span>
            <div className="tim-link-row">
              <input className="tim-link-input" readOnly value={loading ? "生成链接中…" : url} />
              <button type="button" className="tim-copy-btn" onClick={handleCopy} title="复制链接">
                <CopyIcon />
              </button>
            </div>
            {copied && <span className="tim-copied">已复制</span>}
            {error && !loading && <span className="tim-error">{error}</span>}
          </label>

          <div className="tim-info">
            <p>
              <span className="tim-dot" />
              此链接设置为 <strong>{inviteExpiryLabel(settings.expiryDays)}</strong> 内有效
            </p>
            <p className="tim-info-sub">
              {settings.quotaType === "unlimited"
                ? "通过此链接加入的成员拥有无限 Tapies 使用量。"
                : settings.quotaType === "periodic"
                  ? `通过此链接加入的成员将获得周期 Tapies 额度（${settings.periodicAmount ?? 20000} / 周期）。`
                  : `通过此链接加入的成员将获得 ${settings.fixedAmount ?? 20000} Tapies 初始额度。`}
            </p>
          </div>

          <footer className="tim-foot">
            <button
              type="button"
              className="tim-settings-btn"
              onClick={() => setSettingsOpen(true)}
            >
              <span aria-hidden>⚙</span>
              编辑链接设置
            </button>
          </footer>
      </AnimatedModal>

      <TeamInviteLinkSettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        teamId={teamId}
        onGenerated={() => {
          setLinkKey((k) => k + 1)
          setSettingsOpen(false)
        }}
      />
    </>
  )
}
