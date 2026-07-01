import { Link } from "react-router-dom"
import VeloraShellBackground from "../common/VeloraShellBackground"
import "../../styles/velora-brand.css"

export default function AuthPage({
  title,
  subtitle,
  children,
  footerText,
  footerLinkTo,
  footerLinkLabel,
}) {
  return (
    <div className="auth-page">
      <VeloraShellBackground />

      <div className="auth-shell">
        <aside className="auth-brand">
          <div className="auth-brand__hero">
            <img
              className="auth-brand__logo"
              src="/velora-logo.png"
              alt="Velora"
              draggable={false}
            />
            <div className="auth-brand__name-block">
              <span className="velora-wordmark velora-wordmark--hero">Velora</span>
              <span className="auth-brand__company">蓝金领 · AI 创作平台</span>
            </div>
          </div>
          <h2 className="auth-brand__tagline">描述画面，一键生成 AI 图像与视频</h2>
          <ul className="auth-brand__features">
            <li>无限画布协作创作</li>
            <li>多模型图像与视频生成</li>
            <li>剧本分镜与智能工作流</li>
          </ul>
        </aside>

        <div className="auth-card">
          <div className="auth-card__head">
            <h1>{title}</h1>
            {subtitle && <p className="auth-card__subtitle">{subtitle}</p>}
          </div>
          {children}
          <p className="auth-footer">
            {footerText}
            <Link to={footerLinkTo}>{footerLinkLabel}</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
