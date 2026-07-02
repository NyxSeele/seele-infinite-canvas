import "./GenerationBrandLoader.css"

/** 卡片生成中品牌 Logo 动效（复用 VeloraLoadingPage 旋转 + 外圈脉冲） */
export default function GenerationBrandLoader({ className = "", size = "compact" }) {
  return (
    <div
      className={`gn2-generating-brand gn2-generating-brand--${size} ${className}`.trim()}
      aria-hidden
    >
      <div className="gn2-generating-brand__ring" />
      <img
        src="/velora-logo.png"
        alt=""
        className="gn2-generating-brand__logo"
        draggable={false}
      />
    </div>
  )
}
