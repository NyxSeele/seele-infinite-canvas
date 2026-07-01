import { useEffect, useState } from "react"
import { createTeamInviteLink } from "../../services/teamApi"
import { getInviteSettings, inviteExpiryLabel, inviteUsesLabel } from "../../utils/teamInviteLink"
import "./TeamInviteLinkSettingsModal.css"

const EXPIRY_OPTIONS = [
  { value: 1, label: "1 天" },
  { value: 7, label: "7 天" },
  { value: 30, label: "30 天" },
  { value: 0, label: "永不过期" },
]

const USES_OPTIONS = [
  { value: 0, label: "无限制" },
  { value: 1, label: "1 次" },
  { value: 5, label: "5 次" },
  { value: 10, label: "10 次" },
]

const CYCLE_OPTIONS = [
  { value: "daily", label: "每天" },
  { value: "weekly", label: "每周" },
  { value: "monthly", label: "每月" },
]

const QUOTA_OPTIONS = [
  { value: "unlimited", label: "无额度限制", icon: "unlimited" },
  { value: "periodic", label: "周期额度", icon: "periodic" },
  { value: "fixed", label: "固定额度", icon: "fixed" },
]

function QuotaHelpIcon() {
  return (
    <span className="tils-quota-help" title="新成员加入团队后的积分额度规则">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden>
        <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1" />
        <path d="M6 5.2V8.2M6 3.6h.01" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
      </svg>
    </span>
  )
}

function QuotaTypeIcon({ type }) {
  if (type === "unlimited") {
    return (
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
        <path d="M5.5 11c0-3.04 2.46-5.5 5.5-5.5s5.5 2.46 5.5 5.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M5.5 11c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    )
  }
  if (type === "periodic") {
    return (
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
        <path d="M11 4.5v2.2M11 15.3v2.2M6.2 6.2l1.55 1.55M14.25 14.25l1.55 1.55M4.5 11h2.2M15.3 11h2.2M6.2 15.8l1.55-1.55M14.25 7.75l1.55-1.55" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        <path d="M11 8.2a2.8 2.8 0 1 1 0 5.6 2.8 2.8 0 0 1 0-5.6Z" stroke="currentColor" strokeWidth="1.3" />
      </svg>
    )
  }
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
      <rect x="7.5" y="10.5" width="7" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.3" />
      <path d="M9.5 10.5V8.8a1.7 1.7 0 0 1 3.4 0V10.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

export default function TeamInviteLinkSettingsModal({ open, onClose, teamId, onGenerated }) {
  const [expiryDays, setExpiryDays] = useState(7)
  const [maxUses, setMaxUses] = useState(0)
  const [quotaType, setQuotaType] = useState("unlimited")
  const [periodicCycle, setPeriodicCycle] = useState("monthly")
  const [periodicAmount, setPeriodicAmount] = useState(20000)
  const [fixedAmount, setFixedAmount] = useState(20000)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open || !teamId) return
    const s = getInviteSettings(teamId)
    setExpiryDays(s.expiryDays)
    setMaxUses(s.maxUses)
    setQuotaType(s.quotaType)
    setPeriodicCycle(s.periodicCycle || "monthly")
    setPeriodicAmount(s.periodicAmount ?? 20000)
    setFixedAmount(s.fixedAmount ?? 20000)
  }, [open, teamId])

  if (!open) return null

  const handleGenerate = async () => {
    if (!teamId || busy) return
    setBusy(true)
    try {
      await createTeamInviteLink(teamId, {
        expiryDays,
        maxUses,
        quotaType,
        periodicCycle,
        periodicAmount: Number(periodicAmount) || 0,
        fixedAmount: Number(fixedAmount) || 0,
      })
      onGenerated?.()
    } catch (err) {
      console.error(err)
      window.alert("生成邀请链接失败，请稍后重试")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="tils-backdrop" onClick={onClose}>
      <div className="tils-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="链接设置">
        <header className="tils-head">
          <button type="button" className="tils-back" onClick={onClose} aria-label="返回">←</button>
          <div>
            <h2>链接设置</h2>
            <p>自定义邀请链接的有效期和使用限制</p>
          </div>
          <button type="button" className="tils-close" onClick={onClose} aria-label="关闭">×</button>
        </header>

        <div className="tils-row">
          <label className="tils-select-field">
            <span>链接有效期</span>
            <select value={expiryDays} onChange={(e) => setExpiryDays(Number(e.target.value))}>
              {EXPIRY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <label className="tils-select-field">
            <span>链接有效使用次数</span>
            <select value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value))}>
              {USES_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
        </div>

        <section className="tils-quota">
          <h3>新成员 Tapies 设置</h3>
          <div className="tils-quota-grid">
            {QUOTA_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                className={`tils-quota-card${quotaType === o.value ? " is-active" : ""}`}
                onClick={() => setQuotaType(o.value)}
              >
                <QuotaHelpIcon />
                <span className="tils-quota-icon">
                  <QuotaTypeIcon type={o.icon} />
                </span>
                <span className="tils-quota-label">{o.label}</span>
              </button>
            ))}
          </div>

          {quotaType === "periodic" && (
            <div className="tils-quota-detail tils-quota-detail--periodic">
              <label className="tils-select-field">
                <span>恢复周期</span>
                <select value={periodicCycle} onChange={(e) => setPeriodicCycle(e.target.value)}>
                  {CYCLE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </label>
              <label className="tils-amount-field">
                <span>周期内 Tapies 额度</span>
                <div className="tils-amount-input">
                  <input
                    type="number"
                    min="0"
                    value={periodicAmount}
                    onChange={(e) => setPeriodicAmount(e.target.value)}
                  />
                  <span className="tils-amount-unit">Tapies</span>
                </div>
              </label>
            </div>
          )}

          {quotaType === "fixed" && (
            <div className="tils-quota-detail tils-quota-detail--fixed">
              <label className="tils-amount-field tils-amount-field--full">
                <span>初始额度</span>
                <div className="tils-amount-input">
                  <input
                    type="number"
                    min="0"
                    value={fixedAmount}
                    onChange={(e) => setFixedAmount(e.target.value)}
                  />
                  <span className="tils-amount-unit">Tapies</span>
                </div>
              </label>
            </div>
          )}

          <p className="tils-quota-hint">
            当前：{inviteExpiryLabel(expiryDays)} · {inviteUsesLabel(maxUses)}
          </p>
        </section>

        <footer className="tils-foot">
          <button
            type="button"
            className="tils-generate"
            disabled={busy}
            onClick={handleGenerate}
          >
            {busy ? "生成中…" : "生成新链接"}
          </button>
        </footer>
      </div>
    </div>
  )
}
