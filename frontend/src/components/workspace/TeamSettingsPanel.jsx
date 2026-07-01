import { useCallback, useEffect, useRef, useState } from "react"
import { useAuth } from "../../contexts/AuthContext"
import {
  leaveTeam,
  listTeamMembers,
  removeTeamMember,
  updateTeam,
  updateTeamMember,
} from "../../services/teamApi"
import { useTeamStore } from "../../stores/teamStore"
import { readTeamAvatar, writeTeamAvatar } from "../../utils/teamAvatar"
import TeamAvatar from "./TeamAvatar"
import TeamInviteModal from "./TeamInviteModal"
import { useTeamMembersRefresh } from "../../hooks/useTeamMembersRefresh"
import "./TeamPanels.css"

const ROLE_OPTIONS = [
  { value: "owner", label: "所有者" },
  { value: "admin", label: "管理员" },
  { value: "editor", label: "编辑者" },
  { value: "viewer", label: "查看者" },
]

function roleLabel(role) {
  return ROLE_OPTIONS.find((r) => r.value === role)?.label || role
}

function formatAssignedQuota(settings) {
  const s = settings || {}
  if (s.quotaType === "fixed") {
    return `固定 ${s.fixedAmount ?? 0} Tapies`
  }
  if (s.quotaType === "periodic") {
    const cycle = s.periodicCycle === "weekly" ? "每周" : "每月"
    return `${cycle} ${s.periodicAmount ?? 0} Tapies`
  }
  return "无额度限制"
}

function formatMemberUsage(member) {
  const q = member.quota
  const assigned = formatAssignedQuota(member.quota_settings)
  if (!q) return assigned
  const used = q.image_used ?? 0
  if ((member.quota_settings?.quotaType || "unlimited") === "unlimited" || q.image_limit < 0) {
    return `已用 ${used} · ${assigned}`
  }
  return `${used} / ${q.image_limit} Tapies`
}

function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <rect x="5" y="5" width="7" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.2" />
      <path d="M3 9V3.8A.8.8 0 0 1 3.8 3H9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

export default function TeamSettingsPanel() {
  const { user } = useAuth()
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const allTeams = useTeamStore((s) => s.allTeams)
  const refreshTeams = useTeamStore((s) => s.refreshTeams)
  const switchToPersonal = useTeamStore((s) => s.switchToPersonal)

  const team = allTeams.find((t) => t.id === activeTeamId) || null
  const canAdmin = team && ["owner", "admin"].includes(team.my_role)
  const isOwner = team?.my_role === "owner"

  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState("")
  const [inviteOpen, setInviteOpen] = useState(false)
  const [teamName, setTeamName] = useState("")
  const [avatarTick, setAvatarTick] = useState(0)
  const avatarRef = useRef(null)

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
    if (!team) return
    setTeamName(team.name || "")
    refreshMembers(team.id)
  }, [team, refreshMembers])

  useEffect(() => {
    if (activeTeamId && !team) {
      void refreshTeams()
    }
  }, [activeTeamId, team, refreshTeams])

  useTeamMembersRefresh({
    enabled: Boolean(team),
    teamId: team?.id,
    refreshMembers,
  })

  const handleAvatar = (e) => {
    const file = e.target.files?.[0]
    if (!file || !team) return
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === "string") {
        writeTeamAvatar(team.id, reader.result)
        setAvatarTick((n) => n + 1)
      }
    }
    reader.readAsDataURL(file)
    e.target.value = ""
  }

  const handleRename = async () => {
    if (!team || !canAdmin) return
    const name = teamName.trim()
    if (!name || name === team.name) return
    try {
      await updateTeam(team.id, { name })
      await refreshTeams()
    } catch (err) {
      setError(err?.response?.data?.detail || "重命名失败")
    }
  }

  const handleRoleChange = async (userId, role) => {
    if (!team || !canAdmin) return
    try {
      await updateTeamMember(team.id, userId, { role })
      await refreshMembers(team.id)
    } catch (err) {
      setError(err?.response?.data?.detail || "更新角色失败")
    }
  }

  const handleRemove = async (userId) => {
    if (!team || !canAdmin) return
    if (!window.confirm("确定移除该成员？")) return
    try {
      await removeTeamMember(team.id, userId)
      await refreshMembers(team.id)
    } catch (err) {
      setError(err?.response?.data?.detail || "移除失败")
    }
  }

  const handleLeave = async () => {
    if (!team) return
    if (!window.confirm("确定退出该团队？")) return
    try {
      await leaveTeam(team.id)
      await refreshTeams()
      switchToPersonal()
      window.dispatchEvent(new CustomEvent("team-context-changed"))
    } catch (err) {
      setError(err?.response?.data?.detail || "退出失败")
    }
  }

  const handleCopyId = async () => {
    if (!team?.id) return
    try {
      await navigator.clipboard.writeText(team.id)
    } catch {
      window.prompt("团队 ID", team.id)
    }
  }

  const filtered = members.filter((m) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return (
      String(m.username || "").toLowerCase().includes(q)
      || String(m.email || "").toLowerCase().includes(q)
    )
  })

  if (!team) {
    return (
      <div className="tp-empty">
        <p>请先切换到团队空间，或在右上角菜单中创建团队。</p>
      </div>
    )
  }

  const avatarUrl = readTeamAvatar(team.id)
  void avatarTick

  return (
    <div className="tp-settings">
      <div className="tp-team-hero">
        <button
          type="button"
          className="tp-team-avatar-edit"
          onClick={() => canAdmin && avatarRef.current?.click()}
          disabled={!canAdmin}
          title={canAdmin ? "编辑团队头像" : "仅管理员可编辑"}
        >
          <TeamAvatar teamId={team.id} name={team.name} size={56} className="team-avatar--round" />
          {canAdmin && <span className="tp-team-avatar-pen">✎</span>}
        </button>
        <input ref={avatarRef} type="file" accept="image/*" hidden onChange={handleAvatar} />
        <div className="tp-team-meta">
          {canAdmin ? (
            <input
              className="tp-team-name-input"
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              onBlur={handleRename}
              onKeyDown={(e) => { if (e.key === "Enter") e.target.blur() }}
            />
          ) : (
            <h2 className="tp-team-name">{team.name}</h2>
          )}
          <button type="button" className="tp-team-id" onClick={handleCopyId}>
            团队 ID：{team.id}
            <CopyIcon />
          </button>
        </div>
      </div>

      {error && <div className="tp-error">{String(error)}</div>}

      <div className="tp-toolbar">
        <h3>团队设置</h3>
        <div className="tp-toolbar-actions">
          <button
            type="button"
            className="tp-icon-btn"
            onClick={() => refreshMembers(team.id)}
            title="刷新"
          >
            ↻
          </button>
          <input
            className="tp-search"
            placeholder="查找成员"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {canAdmin && (
            <button type="button" className="tp-invite-btn" onClick={() => setInviteOpen(true)}>
              + 邀请成员
            </button>
          )}
        </div>
      </div>

      <div className="tp-table">
        <div className="tp-table-head">
          <span>成员信息</span>
          <span>当前使用量 / 总额</span>
          <span>角色</span>
        </div>
        {loading ? (
          <div className="tp-table-empty">加载中…</div>
        ) : filtered.length === 0 ? (
          <div className="tp-table-empty">暂无成员</div>
        ) : (
          filtered.map((m) => {
            const isSelf = m.user_id === user?.id
            return (
              <div key={m.user_id} className="tp-table-row">
                <div className="tp-member-cell">
                  <span className="tp-member-avatar">{(m.username?.[0] || "U").toUpperCase()}</span>
                  <div>
                    <div className="tp-member-name">
                      {m.username}
                      {isSelf && <span className="tp-you">（你）</span>}
                    </div>
                    {m.email && <div className="tp-member-email">{m.email}</div>}
                  </div>
                </div>
                <div className="tp-usage-cell">
                  <div className="tp-usage-label">
                    <span>{formatMemberUsage(m)}</span>
                    {(m.quota_settings?.quotaType || "unlimited") === "unlimited" && (
                      <span className="tp-infinity">∞</span>
                    )}
                  </div>
                  <div className="tp-quota-bar tp-quota-bar--sm">
                    <div
                      className="tp-quota-fill"
                      style={{
                        width: m.quota && m.quota.image_limit > 0
                          ? `${Math.min(100, Math.round(((m.quota.image_used || 0) / m.quota.image_limit) * 100))}%`
                          : "100%",
                      }}
                    />
                  </div>
                  <div className="tp-member-email tp-quota-assigned">{formatAssignedQuota(m.quota_settings)}</div>
                </div>
                <div className="tp-role-cell">
                  {canAdmin && m.role !== "owner" ? (
                    <select
                      className="tp-role-select"
                      value={m.role}
                      onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                    >
                      {ROLE_OPTIONS.filter((r) => r.value !== "owner").map((r) => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="tp-role-text">{roleLabel(m.role)}</span>
                  )}
                  {canAdmin && m.role !== "owner" && (
                    <button
                      type="button"
                      className="tp-remove-btn"
                      onClick={() => handleRemove(m.user_id)}
                    >
                      移除
                    </button>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      {!isOwner && (
        <button type="button" className="tp-leave-btn" onClick={handleLeave}>
          退出团队
        </button>
      )}

      <TeamInviteModal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        teamId={team.id}
        teamName={team.name}
      />
    </div>
  )
}
