import { useCallback, useEffect, useState } from "react"
import api from "../../services/api"
import { cancelCanvasTask } from "../../services/cancelTask"

function formatDate(ts) {
  if (!ts) return "—"
  try {
    return new Date(ts).toLocaleString("zh-CN")
  } catch { return String(ts) }
}

const STATUS_BADGE = {
  running: "adm-badge--running",
  pending: "adm-badge--pending",
  queued: "adm-badge--pending",
  processing: "adm-badge--running",
  completed: "adm-badge--done",
  done: "adm-badge--done",
  failed: "adm-badge--error",
  cancelled: "adm-badge--disabled",
  timeout: "adm-badge--error",
}

const STATUS_LABEL = {
  running: "运行中",
  pending: "排队中",
  queued: "排队中",
  processing: "处理中",
  completed: "已完成",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
  timeout: "超时",
}

const TYPE_LABEL = {
  image: "图像",
  video: "视频",
  text: "文本",
}

const CANCELLABLE = new Set(["running", "pending", "queued", "processing"])

export default function TaskMonitor() {
  const [tasks, setTasks] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState("")
  const [page, setPage] = useState(1)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [expandedId, setExpandedId] = useState(null)
  const [cancellingId, setCancellingId] = useState("")
  const PAGE_SIZE = 20

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get("/api/admin/tasks", {
        params: {
          page,
          page_size: PAGE_SIZE,
          status: statusFilter || undefined,
        },
      })
      setTasks(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch (e) {
      console.error("加载任务失败", e)
      setTasks([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, statusFilter])

  useEffect(() => { loadTasks() }, [loadTasks])

  useEffect(() => {
    if (!autoRefresh) return undefined
    const t = setInterval(loadTasks, 8000)
    return () => clearInterval(t)
  }, [autoRefresh, loadTasks])

  const handleCancel = async (taskId) => {
    if (!taskId || cancellingId) return
    setCancellingId(taskId)
    try {
      await cancelCanvasTask(taskId)
      await loadTasks()
    } catch (e) {
      console.error("取消任务失败", e)
      window.alert(e.response?.data?.detail || "取消任务失败")
    } finally {
      setCancellingId("")
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div>
      <div className="adm-page-header">
        <h2 className="adm-page-title" style={{ marginBottom: 0 }}>任务监控</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <label className="adm-refresh-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            自动刷新
          </label>
          <button className="adm-btn" onClick={loadTasks}>刷新</button>
        </div>
      </div>

      <div className="adm-filter-bar">
        <select
          style={{ padding: "7px 12px", borderRadius: 8, border: "1px solid var(--adm-border)", background: "var(--adm-surface)", color: "var(--adm-text)", fontSize: 13, fontFamily: "inherit", outline: "none" }}
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
        >
          <option value="">全部状态</option>
          <option value="running">运行中</option>
          <option value="pending">排队中</option>
          <option value="processing">处理中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
          <option value="cancelled">已取消</option>
        </select>
      </div>

      <div className="adm-table-wrap">
        {loading ? (
          <div className="adm-loading">加载任务列表…</div>
        ) : tasks.length === 0 ? (
          <div className="adm-empty">暂无任务记录</div>
        ) : (
          <table className="adm-table">
            <thead>
              <tr>
                <th>任务 ID</th>
                <th>用户</th>
                <th>类型</th>
                <th>状态</th>
                <th>提示词</th>
                <th>提交时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td style={{ fontFamily: "monospace", fontSize: 12, color: "var(--adm-text-sub)" }}>
                    {String(t.id).slice(0, 8)}…
                  </td>
                  <td>{t.username || (t.user_id != null ? `#${t.user_id}` : "—")}</td>
                  <td>
                    <span className="adm-badge adm-badge--pending">
                      {TYPE_LABEL[t.task_type] || t.task_type}
                    </span>
                  </td>
                  <td>
                    <span className={`adm-badge ${STATUS_BADGE[t.status] || "adm-badge--disabled"}`}>
                      {STATUS_LABEL[t.status] || t.status}
                    </span>
                  </td>
                  <td
                    className={`adm-prompt-cell${expandedId === t.id ? " adm-prompt-cell--expanded" : ""}`}
                    style={{ fontSize: 12 }}
                    title={t.prompt_text || ""}
                    onClick={() => setExpandedId((prev) => (prev === t.id ? null : t.id))}
                  >
                    {t.prompt_text || "—"}
                  </td>
                  <td style={{ fontSize: 12, color: "var(--adm-text-sub)" }}>
                    {formatDate(t.created_at)}
                  </td>
                  <td>
                    {CANCELLABLE.has(t.status) ? (
                      <button
                        className="adm-btn adm-btn--danger"
                        disabled={cancellingId === t.id}
                        onClick={() => handleCancel(t.id)}
                      >
                        {cancellingId === t.id ? "取消中…" : "强制取消"}
                      </button>
                    ) : (
                      <span style={{ color: "var(--adm-text-sub)", fontSize: 12 }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

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
    </div>
  )
}
