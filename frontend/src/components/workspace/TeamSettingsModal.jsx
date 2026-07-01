import { useCallback, useEffect, useState } from "react"
import { useTeamStore } from "../../stores/teamStore"
import {
  addTeamMember,
  createTeam,
  leaveTeam,
  listTeamMembers,
  removeTeamMember,
  updateTeam,
  updateTeamMember,
} from "../../services/teamApi"
import { useTeamMembersRefresh } from "../../hooks/useTeamMembersRefresh"
import "./TeamSettingsModal.css"

const ROLE_OPTIONS = [
  { value: "editor", label: "编辑者" },
  { value: "viewer", label: "查看者" },
  { value: "admin", label: "管理员" },
]

export default function TeamSettingsModal({ open, onClose, initialTeamId = null }) {
  const refreshTeams = useTeamStore((s) => s.refreshTeams)
  const ownedTeam = useTeamStore((s) => s.ownedTeam)
  const allTeams = useTeamStore((s) => s.allTeams)
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const setActiveTeamId = useTeamStore((s) => s.setActiveTeamId)

  const [teamId, setTeamId] = useState(initialTeamId || activeTeamId || ownedTeam?.id || "")
  const [members, setMembers] = useState([])
  const [teamName, setTeamName] = useState("")
  const [newTeamName, setNewTeamName] = useState("")
  const [inviteUsername, setInviteUsername] = useState("")
  const [inviteRole, setInviteRole] = useState("editor")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const selectedTeam = allTeams.find((t) => t.id === teamId) || null
  const canAdmin = selectedTeam && ["owner", "admin"].includes(selectedTeam.my_role)
  const isOwner = selectedTeam?.my_role === "owner"

  const refreshMembers = useCallback(async (id) => {
    if (!id) {
      setMembers([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const rows = await listTeamMembers(id)
      setMembers(rows)
    } catch (err) {
      setError(err?.response?.data?.detail || "加载成员失败")
      setMembers([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const id =
      initialTeamId
      || activeTeamId
      || ownedTeam?.id
      || useTeamStore.getState().allTeams[0]?.id
      || ""
    if (id) setTeamId(id)
  }, [open, initialTeamId, activeTeamId, ownedTeam?.id])

  useEffect(() => {
    if (!open || !teamId) return
    const team = useTeamStore.getState().allTeams.find((t) => t.id === teamId)
    setTeamName(team?.name || "")
    refreshMembers(teamId)
  }, [open, teamId, refreshMembers])

  useTeamMembersRefresh({
    enabled: open && Boolean(teamId),
    teamId,
    refreshMembers,
  })

  const handleCreateTeam = async () => {
    const name = newTeamName.trim()
    if (!name) return
    setBusy(true)
    setError(null)
    try {
      const team = await createTeam(name)
      await refreshTeams()
      setTeamId(team.id)
      setActiveTeamId(team.id)
      setNewTeamName("")
      window.dispatchEvent(new CustomEvent("team-context-changed"))
    } catch (err) {
      setError(err?.response?.data?.detail || "创建团队失败")
    } finally {
      setBusy(false)
    }
  }

  const handleRename = async () => {
    if (!teamId || !canAdmin) return
    const name = teamName.trim()
    if (!name) return
    setBusy(true)
    try {
      await updateTeam(teamId, { name })
      await refreshTeams()
    } catch (err) {
      setError(err?.response?.data?.detail || "重命名失败")
    } finally {
      setBusy(false)
    }
  }

  const handleInvite = async () => {
    if (!teamId || !canAdmin) return
    const username = inviteUsername.trim()
    if (!username) return
    setBusy(true)
    try {
      await addTeamMember(teamId, { username, role: inviteRole })
      setInviteUsername("")
      await refreshMembers(teamId)
    } catch (err) {
      setError(err?.response?.data?.detail || "添加成员失败")
    } finally {
      setBusy(false)
    }
  }

  const handleRoleChange = async (userId, role) => {
    if (!teamId || !canAdmin) return
    try {
      await updateTeamMember(teamId, userId, { role })
      await refreshMembers(teamId)
    } catch (err) {
      setError(err?.response?.data?.detail || "更新角色失败")
    }
  }

  const handleRemove = async (userId) => {
    if (!teamId || !canAdmin) return
    if (!window.confirm("确定移除该成员？")) return
    try {
      await removeTeamMember(teamId, userId)
      await refreshMembers(teamId)
    } catch (err) {
      setError(err?.response?.data?.detail || "移除失败")
    }
  }

  const handleLeave = async () => {
    if (!teamId) return
    if (!window.confirm("确定退出该团队？")) return
    try {
      await leaveTeam(teamId)
      await refreshTeams()
      if (activeTeamId === teamId) {
        useTeamStore.getState().switchToPersonal()
        window.dispatchEvent(new CustomEvent("team-context-changed"))
      }
      onClose?.()
    } catch (err) {
      setError(err?.response?.data?.detail || "退出失败")
    }
  }

  if (!open) return null

  return (
    <div className="team-modal-backdrop" onClick={onClose}>
      <div className="team-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="团队管理">
        <header className="team-modal-head">
          <h2>团队管理</h2>
          <button type="button" className="team-modal-close" onClick={onClose} aria-label="关闭">×</button>
        </header>

        {error && <div className="team-modal-error">{String(error)}</div>}

        {!ownedTeam && (
          <section className="team-modal-section">
            <h3>创建你的团队</h3>
            <p className="team-modal-hint">每个账号只能拥有一个团队，可加入多个他人团队。</p>
            <div className="team-modal-row">
              <input
                className="team-modal-input"
                placeholder="团队名称"
                value={newTeamName}
                onChange={(e) => setNewTeamName(e.target.value)}
              />
              <button type="button" className="team-modal-btn" disabled={busy} onClick={handleCreateTeam}>
                创建
              </button>
            </div>
          </section>
        )}

        {allTeams.length > 0 && (
          <section className="team-modal-section">
            <label className="team-modal-label">
              管理团队
              <select
                className="team-modal-select"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
              >
                {allTeams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.my_role})
                  </option>
                ))}
              </select>
            </label>

            {canAdmin && (
              <div className="team-modal-row">
                <input
                  className="team-modal-input"
                  value={teamName}
                  onChange={(e) => setTeamName(e.target.value)}
                />
                <button type="button" className="team-modal-btn" disabled={busy} onClick={handleRename}>
                  保存名称
                </button>
              </div>
            )}

            <h3>成员 ({members.length})</h3>
            {loading ? (
              <p className="team-modal-hint">加载中…</p>
            ) : (
              <ul className="team-member-list">
                {members.map((m) => (
                  <li key={m.user_id} className="team-member-row">
                    <div className="team-member-info">
                      <strong>{m.username}</strong>
                      <span className="team-member-role">{m.role}</span>
                    </div>
                    {canAdmin && m.role !== "owner" && (
                      <div className="team-member-actions">
                        <select
                          className="team-modal-select team-modal-select--sm"
                          value={m.role}
                          onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                        >
                          {ROLE_OPTIONS.map((r) => (
                            <option key={r.value} value={r.value}>{r.label}</option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="team-modal-btn team-modal-btn--danger"
                          onClick={() => handleRemove(m.user_id)}
                        >
                          移除
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {canAdmin && (
              <div className="team-modal-invite">
                <h3>邀请成员</h3>
                <div className="team-modal-row">
                  <input
                    className="team-modal-input"
                    placeholder="用户名"
                    value={inviteUsername}
                    onChange={(e) => setInviteUsername(e.target.value)}
                  />
                  <select
                    className="team-modal-select"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                  >
                    {ROLE_OPTIONS.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                  <button type="button" className="team-modal-btn" disabled={busy} onClick={handleInvite}>
                    添加
                  </button>
                </div>
              </div>
            )}

            {!isOwner && selectedTeam && (
              <button type="button" className="team-modal-btn team-modal-btn--danger team-modal-leave" onClick={handleLeave}>
                退出团队
              </button>
            )}
          </section>
        )}
      </div>
    </div>
  )
}
