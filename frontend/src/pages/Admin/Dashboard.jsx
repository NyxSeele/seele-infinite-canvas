import { useEffect, useState } from "react"
import api from "../../services/api"

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

function formatDate(iso) {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleString("zh-CN")
  } catch {
    return iso
  }
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [recentTasks, setRecentTasks] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/admin/stats/overview")
        setStats(res.data?.stats || res.data)
        setRecentTasks(res.data?.recent_tasks || [])
      } catch {
        setStats(null)
        setRecentTasks([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div>
      <h2 className="adm-page-title">系统概览</h2>
      {loading ? (
        <div className="adm-loading">加载中…</div>
      ) : !stats ? (
        <div className="adm-empty">加载统计数据失败</div>
      ) : (
        <>
          <div className="adm-stats-grid">
            <div className="adm-stat-card">
              <div className="adm-stat-label">注册用户总数</div>
              <div className="adm-stat-value accent">{stats.total_users}</div>
            </div>
            <div className="adm-stat-card">
              <div className="adm-stat-label">历史任务总数</div>
              <div className="adm-stat-value">{stats.total_tasks}</div>
            </div>
            <div className="adm-stat-card">
              <div className="adm-stat-label">当前运行中任务</div>
              <div className="adm-stat-value warning">{stats.active_tasks}</div>
            </div>
            <div className="adm-stat-card">
              <div className="adm-stat-label">今日新增用户</div>
              <div className="adm-stat-value success">{stats.today_users ?? 0}</div>
            </div>
            <div className="adm-stat-card">
              <div className="adm-stat-label">今日任务量</div>
              <div className="adm-stat-value">{stats.today_tasks ?? 0}</div>
            </div>
            <div className="adm-stat-card">
              <div className="adm-stat-label">历史失败率</div>
              <div className="adm-stat-value danger">{stats.failed_rate ?? 0}%</div>
            </div>
          </div>

          <section className="adm-activity-section">
            <h3 className="adm-activity-title">最近任务动态</h3>
            {recentTasks.length === 0 ? (
              <div className="adm-empty">暂无任务记录</div>
            ) : (
              <div className="adm-activity-list">
                {recentTasks.map((task) => (
                  <div key={task.id} className="adm-activity-item">
                    <span className={`adm-badge ${STATUS_BADGE[task.status] || "adm-badge--disabled"}`}>
                      {STATUS_LABEL[task.status] || task.status}
                    </span>
                    <span className="adm-badge adm-badge--pending">
                      {TYPE_LABEL[task.task_type] || task.task_type}
                    </span>
                    <span>{task.username || "—"}</span>
                    <span className="adm-activity-prompt" title={task.prompt_text || ""}>
                      {task.prompt_text || "—"}
                    </span>
                    <span className="adm-activity-time">{formatDate(task.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
