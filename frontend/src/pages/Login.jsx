import { useState } from "react"
import { Navigate, useNavigate, useLocation } from "react-router-dom"
import { message } from "antd"
import { useAuth } from "../contexts/AuthContext.jsx"
import AuthPage from "../components/auth/AuthPage.jsx"
import VeloraLoadingPage from "../components/common/VeloraLoadingPage.jsx"
import "./Auth.css"

export default function Login() {
  const { login, isAuthenticated, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ username_or_email: "", password: "" })
  const [submitting, setSubmitting] = useState(false)

  const redirectTo = (() => {
    const from = location.state?.from
    if (!from) return "/workspace"
    return `${from.pathname || "/workspace"}${from.search || ""}`
  })()

  if (loading) {
    return <VeloraLoadingPage message="正在加载…" />
  }

  if (isAuthenticated) {
    return <Navigate to={redirectTo} replace />
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await login(form.username_or_email.trim(), form.password)
      message.success("登录成功")
      navigate(redirectTo)
    } catch (err) {
      const detail = err.response?.data?.detail
      message.error(typeof detail === "string" ? detail : "登录失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthPage
      title="欢迎回来"
      subtitle="登录后即可进入工作台与无限画布"
      footerText="还没有账号？"
      footerLinkTo="/register"
      footerLinkLabel="立即注册"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <div className="auth-field">
          <label htmlFor="login-username">用户名或邮箱</label>
          <input
            id="login-username"
            value={form.username_or_email}
            onChange={(e) =>
              setForm((f) => ({ ...f, username_or_email: e.target.value }))
            }
            placeholder="输入用户名或邮箱"
            required
            autoComplete="username"
          />
        </div>
        <div className="auth-field">
          <label htmlFor="login-password">密码</label>
          <input
            id="login-password"
            type="password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            placeholder="输入密码"
            required
            autoComplete="current-password"
          />
        </div>
        <button type="submit" className="auth-submit" disabled={submitting}>
          {submitting ? "登录中…" : "登录"}
        </button>
      </form>
    </AuthPage>
  )
}
