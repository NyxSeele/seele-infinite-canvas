import { useState } from "react"
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import { useAuth } from "../../contexts/AuthContext.jsx"
import VeloraShellBackground from "../../components/common/VeloraShellBackground"
import {
  IconChevron,
  IconDashboard,
  IconModels,
  IconTasks,
  IconUsers,
} from "./AdminIcons.jsx"
import "../../styles/velora-brand.css"
import "./Admin.css"

const NAV_ITEMS = [
  { to: "/admin", label: "概览", Icon: IconDashboard, end: true },
  { to: "/admin/users", label: "用户管理", Icon: IconUsers },
  { to: "/admin/models", label: "模型管理", Icon: IconModels },
  { to: "/admin/tasks", label: "任务监控", Icon: IconTasks },
]

function pageTitle(pathname) {
  if (pathname.startsWith("/admin/users")) return "用户管理"
  if (pathname.startsWith("/admin/models")) return "模型管理"
  if (pathname.startsWith("/admin/tasks")) return "任务监控"
  return "系统概览"
}

export default function AdminLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate("/login")
  }

  return (
    <div className={`admin-shell${collapsed ? " admin-shell--collapsed" : ""}`}>
      <VeloraShellBackground />
      <aside className="admin-nav">
        <div className="admin-nav-logo">
          <span className="admin-nav-logo-icon">◈</span>
          {!collapsed && (
            <div>
              <div className="admin-nav-logo-title">Velora</div>
              <div className="admin-nav-logo-sub">管理后台</div>
            </div>
          )}
        </div>

        <nav className="admin-nav-links">
          {NAV_ITEMS.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `admin-nav-item${isActive ? " active" : ""}`
              }
            >
              <span className="admin-nav-icon">
                <Icon />
              </span>
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="admin-nav-footer">
          {!collapsed && (
            <div className="admin-nav-user">
              <span className="admin-nav-username">{user?.username}</span>
              <span className="admin-nav-role-badge">管理员</span>
            </div>
          )}
          <div className="admin-nav-actions">
            <button
              className="admin-nav-btn"
              onClick={() => navigate("/canvas")}
              title="返回画布"
            >
              {collapsed ? "←" : "← 返回画布"}
            </button>
            <button
              className="admin-nav-btn admin-nav-btn--danger"
              onClick={handleLogout}
              title="退出"
            >
              {collapsed ? "×" : "退出"}
            </button>
          </div>
        </div>

        <button
          type="button"
          className="admin-nav-collapse"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
        >
          <span className={`admin-nav-collapse-icon${collapsed ? " admin-nav-collapse-icon--flipped" : ""}`}>
            <IconChevron />
          </span>
        </button>
      </aside>

      <main className="admin-content">
        <header className="admin-content-header">
          <div className="admin-breadcrumb">
            <span className="admin-breadcrumb-root">管理后台</span>
            <span className="admin-breadcrumb-sep">/</span>
            <span className="admin-breadcrumb-current">{pageTitle(location.pathname)}</span>
          </div>
        </header>
        <Outlet />
      </main>
    </div>
  )
}
