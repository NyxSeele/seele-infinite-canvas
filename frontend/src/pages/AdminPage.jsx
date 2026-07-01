import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { message } from "antd"
import api from "../services/api"
import UserModelPermissions from "../components/admin/UserModelPermissions.jsx"
import "./AdminPage.css"

function formatQuota(limit, used, remaining) {
  if (limit < 0) return "无限"
  const rem = remaining ?? Math.max(0, limit - used)
  return `${used} / ${limit}（剩余 ${rem}）`
}

function formatDate(iso) {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleString("zh-CN")
  } catch {
    return iso
  }
}

export default function AdminPage() {
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState("")
  const [searchInput, setSearchInput] = useState("")
  const [loadingUsers, setLoadingUsers] = useState(true)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [activeTab, setActiveTab] = useState("basic")
  const [quotaImage, setQuotaImage] = useState(50)
  const [quotaVideo, setQuotaVideo] = useState(10)
  const [savingQuota, setSavingQuota] = useState(false)
  const [togglingStatus, setTogglingStatus] = useState(false)

  const loadUsers = useCallback(async () => {
    setLoadingUsers(true)
    try {
      const res = await api.get("/api/admin/users", {
        params: { page: 1, q: search || undefined },
      })
      setUsers(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch (err) {
      message.error(err.response?.data?.detail || "加载用户列表失败")
    } finally {
      setLoadingUsers(false)
    }
  }, [search])

  useEffect(() => {
    loadUsers()
  }, [loadUsers])

  const loadDetail = useCallback(async (userId) => {
    try {
      const res = await api.get(`/api/admin/users/${userId}`)
      setDetail(res.data)
      const q = res.data.quota
      if (q) {
        setQuotaImage(q.image_limit)
        setQuotaVideo(q.video_limit)
      }
    } catch (err) {
      message.error(err.response?.data?.detail || "加载用户详情失败")
    }
  }, [])

  const selectUser = (user) => {
    setSelectedId(user.id)
    setActiveTab("basic")
    loadDetail(user.id)
  }

  const handleToggleStatus = async () => {
    if (!detail) return
    setTogglingStatus(true)
    try {
      await api.patch(`/api/admin/users/${detail.id}/status`, {
        is_active: !detail.is_active,
      })
      message.success(detail.is_active ? "已禁用用户" : "已启用用户")
      await loadDetail(detail.id)
      await loadUsers()
    } catch (err) {
      message.error(err.response?.data?.detail || "更新状态失败")
    } finally {
      setTogglingStatus(false)
    }
  }

  const handleSaveQuota = async () => {
    if (!detail) return
    setSavingQuota(true)
    try {
      await api.patch(`/api/admin/users/${detail.id}/quota`, {
        image_limit: Number(quotaImage),
        video_limit: Number(quotaVideo),
      })
      message.success("配额已更新")
      await loadDetail(detail.id)
    } catch (err) {
      message.error(err.response?.data?.detail || "更新配额失败")
    } finally {
      setSavingQuota(false)
    }
  }

  const handleResetQuota = async () => {
    if (!detail) return
    setSavingQuota(true)
    try {
      await api.post(`/api/admin/users/${detail.id}/reset_quota`)
      message.success("配额已重置")
      await loadDetail(detail.id)
    } catch (err) {
      message.error(err.response?.data?.detail || "重置配额失败")
    } finally {
      setSavingQuota(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>用户与权限管理</h2>
        <Link to="/" className="admin-back-link">
          返回工作台
        </Link>
      </div>

      <div className="admin-layout">
        <aside className="admin-sidebar">
          <div className="admin-search">
            <input
              type="search"
              placeholder="搜索用户名或邮箱…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") setSearch(searchInput.trim())
              }}
            />
            <button type="button" onClick={() => setSearch(searchInput.trim())}>
              搜索
            </button>
          </div>
          {loadingUsers ? (
            <p className="admin-empty-hint">加载用户…</p>
          ) : users.length === 0 ? (
            <p className="admin-empty-hint">无匹配用户</p>
          ) : (
            <ul className="admin-user-list">
              {users.map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    className={`admin-user-item${selectedId === u.id ? " active" : ""}`}
                    onClick={() => selectUser(u)}
                  >
                    <span className="admin-user-name">{u.username}</span>
                    <span className="admin-user-email">{u.email}</span>
                    {!u.is_active && (
                      <span className="admin-user-badge disabled">已禁用</span>
                    )}
                    {u.role === "admin" && (
                      <span className="admin-user-badge admin">管理员</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="admin-user-count">共 {total} 位用户</p>
        </aside>

        <section className="admin-panel">
          {!selectedId ? (
            <p className="admin-empty-hint">请从左侧选择用户查看详情</p>
          ) : (
            <>
              <div className="admin-tabs">
                <button
                  type="button"
                  className={activeTab === "basic" ? "active" : ""}
                  onClick={() => setActiveTab("basic")}
                >
                  基础信息
                </button>
                <button
                  type="button"
                  className={activeTab === "models" ? "active" : ""}
                  onClick={() => setActiveTab("models")}
                >
                  模型权限
                </button>
                <button
                  type="button"
                  className={activeTab === "quota" ? "active" : ""}
                  onClick={() => setActiveTab("quota")}
                >
                  配额管理
                </button>
              </div>

              <div className="admin-tab-body">
                {activeTab === "basic" && detail && (
                  <div className="admin-basic">
                    <dl>
                      <dt>用户名</dt>
                      <dd>{detail.username}</dd>
                      <dt>邮箱</dt>
                      <dd>{detail.email}</dd>
                      <dt>角色</dt>
                      <dd>{detail.role === "admin" ? "管理员" : "普通用户"}</dd>
                      <dt>注册时间</dt>
                      <dd>{formatDate(detail.created_at)}</dd>
                      <dt>状态</dt>
                      <dd>{detail.is_active ? "正常" : "已禁用"}</dd>
                    </dl>
                    <button
                      type="button"
                      className={`admin-action-btn${detail.is_active ? " danger" : ""}`}
                      disabled={togglingStatus}
                      onClick={handleToggleStatus}
                    >
                      {togglingStatus
                        ? "处理中…"
                        : detail.is_active
                          ? "禁用账户"
                          : "启用账户"}
                    </button>
                  </div>
                )}

                {activeTab === "models" && (
                  <UserModelPermissions userId={selectedId} />
                )}

                {activeTab === "quota" && detail && (
                  <div className="admin-quota">
                    <p className="admin-quota-summary">
                      图像：{formatQuota(
                        detail.quota.image_limit,
                        detail.quota.image_used,
                        detail.quota.image_remaining
                      )}
                      <br />
                      视频：{formatQuota(
                        detail.quota.video_limit,
                        detail.quota.video_used,
                        detail.quota.video_remaining
                      )}
                      <br />
                      周期起始：{detail.quota.period_start}，{detail.quota.days_until_reset}{" "}
                      天后重置
                    </p>
                    <div className="admin-quota-form">
                      <label>
                        图像配额上限（-1 为无限）
                        <input
                          type="number"
                          value={quotaImage}
                          onChange={(e) => setQuotaImage(Number(e.target.value))}
                        />
                      </label>
                      <label>
                        视频配额上限（-1 为无限）
                        <input
                          type="number"
                          value={quotaVideo}
                          onChange={(e) => setQuotaVideo(Number(e.target.value))}
                        />
                      </label>
                    </div>
                    <div className="admin-quota-actions">
                      <button
                        type="button"
                        className="admin-action-btn primary"
                        disabled={savingQuota}
                        onClick={handleSaveQuota}
                      >
                        保存配额
                      </button>
                      <button
                        type="button"
                        className="admin-action-btn"
                        disabled={savingQuota}
                        onClick={handleResetQuota}
                      >
                        重置本月用量
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
