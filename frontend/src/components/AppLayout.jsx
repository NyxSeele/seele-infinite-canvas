import { Link, Outlet, useNavigate } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext.jsx"
import "./AppLayout.css"

function formatQuota(limit, used, remaining) {
  if (limit < 0) return "无限"
  const rem = remaining ?? Math.max(0, limit - used)
  return `${used}/${limit}（剩余 ${rem}）`
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate("/login")
  }

  const q = user?.quota

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-row">
          <div>
            <h1>Velora</h1>
            <p>描述画面，一键生成 AI 图像与视频</p>
            {q && (
              <div className="quota-bar">
                <span>图像配额：{formatQuota(q.image_limit, q.image_used, q.image_remaining)}</span>
                <span>视频配额：{formatQuota(q.video_limit, q.video_used, q.video_remaining)}</span>
                <span>{q.days_until_reset} 天后重置</span>
              </div>
            )}
          </div>
          {user && (
            <div className="header-user">
              <Link to="/canvas" className="header-nav-link">
                画布
              </Link>
              <span>
                {user.username}
                {user.role === "admin" ? "（管理员）" : ""}
              </span>
              {user.role === "admin" && (
                <Link to="/admin" className="header-admin-link">
                  管理后台
                </Link>
              )}
              <button type="button" className="header-logout" onClick={handleLogout}>
                退出
              </button>
            </div>
          )}
        </div>
      </header>
      <Outlet />
    </div>
  )
}
