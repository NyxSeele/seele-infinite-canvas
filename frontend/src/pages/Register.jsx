import { useState } from "react"
import { Navigate, useNavigate } from "react-router-dom"
import { message } from "antd"
import { useAuth } from "../contexts/AuthContext.jsx"
import AuthPage from "../components/auth/AuthPage.jsx"
import VeloraLoadingPage from "../components/common/VeloraLoadingPage.jsx"
import "./Auth.css"

export default function Register() {
  const { register, isAuthenticated, loading } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: "", email: "", password: "" })
  const [submitting, setSubmitting] = useState(false)

  if (loading) {
    return <VeloraLoadingPage message="正在加载…" />
  }

  if (isAuthenticated) {
    return <Navigate to="/workspace" replace />
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await register(form.username.trim(), form.email.trim(), form.password)
      message.success("注册成功")
      navigate("/workspace")
    } catch (err) {
      const detail = err.response?.data?.detail
      message.error(typeof detail === "string" ? detail : "注册失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthPage
      title="创建账号"
      subtitle="注册后即可体验 AI 创作工作流"
      footerText="已有账号？"
      footerLinkTo="/login"
      footerLinkLabel="去登录"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <div className="auth-field">
          <label htmlFor="register-username">用户名</label>
          <input
            id="register-username"
            value={form.username}
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
            placeholder="3-20 位字母、数字或下划线"
            required
            minLength={3}
            maxLength={20}
            pattern="[a-zA-Z0-9_]{3,20}"
            autoComplete="username"
          />
          <span className="auth-field-hint">3-20 位字母数字下划线</span>
        </div>
        <div className="auth-field">
          <label htmlFor="register-email">邮箱</label>
          <input
            id="register-email"
            type="email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            placeholder="name@example.com"
            required
            autoComplete="email"
          />
        </div>
        <div className="auth-field">
          <label htmlFor="register-password">密码</label>
          <input
            id="register-password"
            type="password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            placeholder="至少 8 位，含大小写字母和数字"
            required
            minLength={8}
            autoComplete="new-password"
          />
          <span className="auth-field-hint">至少 8 位，需包含大小写字母和数字</span>
        </div>
        <button type="submit" className="auth-submit" disabled={submitting}>
          {submitting ? "注册中…" : "注册"}
        </button>
      </form>
    </AuthPage>
  )
}
