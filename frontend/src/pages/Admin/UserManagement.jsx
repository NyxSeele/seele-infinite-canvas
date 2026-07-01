import { useCallback, useEffect, useState } from "react"
import api from "../../services/api"
import UserModelPermissions from "../../components/admin/UserModelPermissions.jsx"

const PAGE_SIZE = 20

function formatQuota(limit, used, remaining) {
  if (limit < 0) return "无限"
  const rem = remaining ?? Math.max(0, limit - used)
  return `${used} / ${limit}（剩余 ${rem}）`
}

function formatDate(iso) {
  if (!iso) return "—"
  try { return new Date(iso).toLocaleString("zh-CN") } catch { return iso }
}

function QuotaEditModal({ user, onClose, onSaved }) {
  const [imageLimit, setImageLimit] = useState(user.quota?.image_limit ?? 50)
  const [videoLimit, setVideoLimit] = useState(user.quota?.video_limit ?? 10)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState("")

  const handleSave = async () => {
    setSaving(true)
    setErr("")
    try {
      await api.patch(`/api/admin/users/${user.id}/quota`, {
        image_limit: Number(imageLimit),
        video_limit: Number(videoLimit),
      })
      onSaved()
    } catch (e) {
      setErr(e.response?.data?.detail || "保存失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="adm-modal-overlay" onClick={onClose}>
      <div className="adm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="adm-modal-title">编辑配额 — {user.username}</div>
        <div className="adm-field">
          <label>图像配额上限（-1 为无限）</label>
          <input
            type="number"
            value={imageLimit}
            onChange={(e) => setImageLimit(e.target.value)}
          />
        </div>
        <div className="adm-field">
          <label>视频配额上限（-1 为无限）</label>
          <input
            type="number"
            value={videoLimit}
            onChange={(e) => setVideoLimit(e.target.value)}
          />
        </div>
        {err && <p style={{ color: "var(--adm-danger)", fontSize: 12 }}>{err}</p>}
        <div className="adm-modal-footer">
          <button className="adm-btn" onClick={onClose}>取消</button>
          <button className="adm-btn adm-btn--primary" onClick={handleSave} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  )
}

function ConfirmModal({ title, body, onConfirm, onClose, danger }) {
  const [loading, setLoading] = useState(false)

  const handleConfirm = async () => {
    setLoading(true)
    try { await onConfirm() } finally { setLoading(false) }
  }

  return (
    <div className="adm-modal-overlay" onClick={onClose}>
      <div className="adm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="adm-modal-title">{title}</div>
        <p className="adm-confirm-text" dangerouslySetInnerHTML={{ __html: body }} />
        <div className="adm-modal-footer">
          <button className="adm-btn" onClick={onClose}>取消</button>
          <button
            className={`adm-btn ${danger ? "adm-btn--danger" : "adm-btn--primary"}`}
            onClick={handleConfirm}
            disabled={loading}
          >
            {loading ? "处理中…" : "确认"}
          </button>
        </div>
      </div>
    </div>
  )
}

function ModelPermModal({ userId, username, onClose }) {
  return (
    <div className="adm-modal-overlay" onClick={onClose}>
      <div className="adm-modal" style={{ width: 520 }} onClick={(e) => e.stopPropagation()}>
        <div className="adm-modal-title">模型权限 — {username}</div>
        <UserModelPermissions userId={userId} />
        <div className="adm-modal-footer">
          <button className="adm-btn adm-btn--primary" onClick={onClose}>完成</button>
        </div>
      </div>
    </div>
  )
}

function UserCardActions({ user, onQuota, onRole, onStatus, onModelPerm }) {
  return (
    <div className="adm-user-card-actions adm-user-card-actions--inline">
      <button type="button" className="adm-btn adm-btn--sm" onClick={() => onQuota(user)}>
        编辑配额
      </button>
      <button type="button" className="adm-btn adm-btn--sm" onClick={() => onRole(user)}>
        {user.role === "admin" ? "降为用户" : "升为管理员"}
      </button>
      <button
        type="button"
        className={`adm-btn adm-btn--sm${user.is_active ? " adm-btn--danger" : ""}`}
        onClick={() => onStatus(user)}
      >
        {user.is_active ? "禁用" : "启用"}
      </button>
      <button type="button" className="adm-btn adm-btn--sm" onClick={() => onModelPerm(user)}>
        模型权限
      </button>
    </div>
  )
}

export default function UserManagement() {
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [searchInput, setSearchInput] = useState("")
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [quotaModal, setQuotaModal] = useState(null)
  const [confirmModal, setConfirmModal] = useState(null)
  const [modelPermModal, setModelPermModal] = useState(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get("/api/admin/users", {
        params: { page, page_size: PAGE_SIZE, q: search || undefined },
      })
      setUsers(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch (e) {
      console.error("加载用户列表失败", e)
    } finally {
      setLoading(false)
    }
  }, [page, search])

  useEffect(() => { loadUsers() }, [loadUsers])

  const handleToggleStatus = (user) => {
    setConfirmModal({
      title: user.is_active ? "禁用账号" : "启用账号",
      body: `确认要<strong>${user.is_active ? "禁用" : "启用"}</strong>用户 <strong>${user.username}</strong> 吗？`,
      danger: user.is_active,
      onConfirm: async () => {
        await api.patch(`/api/admin/users/${user.id}/status`, {
          is_active: !user.is_active,
        })
        setConfirmModal(null)
        await loadUsers()
      },
    })
  }

  const handleToggleRole = (user) => {
    const newRole = user.role === "admin" ? "user" : "admin"
    setConfirmModal({
      title: "切换角色",
      body: `将用户 <strong>${user.username}</strong> 的角色从 <strong>${user.role === "admin" ? "管理员" : "普通用户"}</strong> 切换为 <strong>${newRole === "admin" ? "管理员" : "普通用户"}</strong>？`,
      danger: newRole === "admin",
      onConfirm: async () => {
        await api.patch(`/api/admin/users/${user.id}/role`, { role: newRole })
        setConfirmModal(null)
        await loadUsers()
      },
    })
  }

  const handleQuotaSaved = async () => {
    setQuotaModal(null)
    await loadUsers()
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div>
      <div className="adm-page-header">
        <h2 className="adm-page-title" style={{ marginBottom: 0 }}>用户管理</h2>
        <span style={{ fontSize: 13, color: "var(--adm-text-sub)" }}>共 {total} 位用户</span>
      </div>

      <div className="adm-filter-bar">
        <input
          className="adm-search-input"
          type="search"
          placeholder="搜索用户名或邮箱…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        {searchInput && (
          <button className="adm-btn" onClick={() => setSearchInput("")}>
            清除
          </button>
        )}
      </div>

      {loading ? (
        <div className="adm-loading">加载用户列表…</div>
      ) : users.length === 0 ? (
        <div className="adm-empty">无匹配用户</div>
      ) : (
        <div className="adm-user-cards">
          {users.map((u) => (
            <article key={u.id} className="adm-user-card">
              <div className="adm-user-avatar">{u.username?.[0]?.toUpperCase() || "?"}</div>
              <div className="adm-user-card-main">
                <div className="adm-user-card-name">{u.username}</div>
                <div className="adm-user-card-email">{u.email}</div>
                <div className="adm-user-card-meta">
                  <span className={`adm-badge adm-badge--${u.role}`}>
                    {u.role === "admin" ? "管理员" : "普通用户"}
                  </span>
                  <span className={`adm-badge ${u.is_active ? "adm-badge--active" : "adm-badge--disabled"}`}>
                    {u.is_active ? "正常" : "已禁用"}
                  </span>
                  <span className="adm-user-card-quota">
                    图 {u.quota ? formatQuota(u.quota.image_limit, u.quota.image_used, u.quota.image_remaining) : "—"}
                  </span>
                  <span className="adm-user-card-quota">
                    视频 {u.quota ? formatQuota(u.quota.video_limit, u.quota.video_used, u.quota.video_remaining) : "—"}
                  </span>
                  <span className="adm-user-card-quota">{formatDate(u.created_at)}</span>
                </div>
              </div>
              <UserCardActions
                user={u}
                onQuota={setQuotaModal}
                onRole={handleToggleRole}
                onStatus={handleToggleStatus}
                onModelPerm={(user) => setModelPermModal({ id: user.id, username: user.username })}
              />
            </article>
          ))}
        </div>
      )}

      {total > PAGE_SIZE && (
        <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
          <button className="adm-btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            上一页
          </button>
          <span style={{ fontSize: 13, color: "var(--adm-text-sub)", alignSelf: "center" }}>
            第 {page} 页 / 共 {totalPages} 页（{total} 条）
          </span>
          <button className="adm-btn" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            下一页
          </button>
        </div>
      )}

      {quotaModal && (
        <QuotaEditModal
          user={quotaModal}
          onClose={() => setQuotaModal(null)}
          onSaved={handleQuotaSaved}
        />
      )}

      {confirmModal && (
        <ConfirmModal
          title={confirmModal.title}
          body={confirmModal.body}
          danger={confirmModal.danger}
          onConfirm={confirmModal.onConfirm}
          onClose={() => setConfirmModal(null)}
        />
      )}

      {modelPermModal && (
        <ModelPermModal
          userId={modelPermModal.id}
          username={modelPermModal.username}
          onClose={() => setModelPermModal(null)}
        />
      )}
    </div>
  )
}
