import VeloraShellBackground from "./VeloraShellBackground"
import "./VeloraLoadingPage.css"
import "../../styles/velora-brand.css"

export default function VeloraLoadingPage({ message = "正在连接服务器…" }) {
  return (
    <div className="velora-loading-page">
      <VeloraShellBackground />
      <div className="velora-loading-page__center">
        <div className="velora-loading-page__logo-ring" aria-hidden />
        <img
          src="/velora-logo.png"
          alt="Velora"
          className="velora-loading-page__logo"
          draggable={false}
        />
        <span className="velora-wordmark velora-wordmark--loading">Velora</span>
        <p className="velora-loading-page__message">{message}</p>
      </div>
    </div>
  )
}
