import { useRef, useState } from "react"
import { createTeam } from "../../services/teamApi"
import { useTeamStore } from "../../stores/teamStore"
import { writeTeamAvatar } from "../../utils/teamAvatar"
import { teamInitial } from "../../utils/teamAvatar"
import "./CreateTeamModal.css"

const MAX_NAME = 50

export default function CreateTeamModal({ open, onClose }) {
  const refreshTeams = useTeamStore((s) => s.refreshTeams)
  const setActiveTeamId = useTeamStore((s) => s.setActiveTeamId)

  const [name, setName] = useState("")
  const [avatarUrl, setAvatarUrl] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const fileRef = useRef(null)

  if (!open) return null

  const trimmed = name.trim()
  const canSubmit = trimmed.length > 0 && !busy

  const handleAvatar = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === "string") setAvatarUrl(reader.result)
    }
    reader.readAsDataURL(file)
    e.target.value = ""
  }

  const handleSubmit = async () => {
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const team = await createTeam(trimmed)
      if (avatarUrl) writeTeamAvatar(team.id, avatarUrl)
      await refreshTeams()
      setActiveTeamId(team.id)
      window.dispatchEvent(new CustomEvent("team-context-changed"))
      setName("")
      setAvatarUrl("")
      onClose?.()
    } catch (err) {
      setError(err?.response?.data?.detail || "创建团队失败")
    } finally {
      setBusy(false)
    }
  }

  const handleBackdrop = () => {
    if (!busy) onClose?.()
  }

  return (
    <div className="ctm-backdrop" onClick={handleBackdrop}>
      <div className="ctm-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="创建团队">
        <header className="ctm-head">
          <div>
            <h2>创建团队</h2>
            <p>新团队将拥有独立的工作空间</p>
          </div>
          <button type="button" className="ctm-close" onClick={onClose} aria-label="关闭">×</button>
        </header>

        <div className="ctm-warn">
          <span className="ctm-warn-icon" aria-hidden>!</span>
          <div>
            <strong>重要提示</strong>
            <p>
              新团队拥有独立的资源空间，初始积分为 <strong>0</strong>。
              个人空间的权益与积分<strong>无法继承</strong>至新团队。
            </p>
          </div>
        </div>

        {error && <div className="ctm-error">{String(error)}</div>}

        <label className="ctm-field">
          <span className="ctm-field-top">
            <span>团队名称 *</span>
            <span className="ctm-counter">{trimmed.length}/{MAX_NAME}</span>
          </span>
          <div className="ctm-name-row">
            <button
              type="button"
              className="ctm-avatar-btn"
              onClick={() => fileRef.current?.click()}
              title="上传团队头像"
            >
              {avatarUrl ? (
                <img src={avatarUrl} alt="" draggable={false} />
              ) : (
                teamInitial(trimmed || "T")
              )}
              <span className="ctm-avatar-edit" aria-hidden>✎</span>
            </button>
            <input
              className="ctm-input"
              placeholder="请输入团队名称"
              value={name}
              maxLength={MAX_NAME}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSubmit() }}
            />
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={handleAvatar} />
          </div>
        </label>

        <footer className="ctm-foot">
          <button type="button" className="ctm-btn ctm-btn--ghost" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="ctm-btn ctm-btn--primary"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {busy ? "创建中…" : "确认"}
          </button>
        </footer>
      </div>
    </div>
  )
}
