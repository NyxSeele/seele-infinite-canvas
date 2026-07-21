import { Maximize2, Minimize2 } from "lucide-react"

const sp = (e) => e.stopPropagation()

/**
 * 画布 Prompt Bar 共用壳层（对齐视频卡布局：顶栏 + 媒体区 + 输入区 + 底栏）
 */
export default function PromptBarShell({
  visible,
  videoTopbarLayout = false,
  compact = false,
  promptVariant = null,
  style,
  onBannerPointerDown,
  showTopbar = true,
  expandInField = false,
  topbarSlot = null,
  mediaSlot = null,
  modal = false,
  expandCardOpen = false,
  onToggleExpand,
  expandTitle,
  collapseTitle,
  showExpandButton = true,
  bannerRef,
  textareaWrapRef,
  textareaSlot,
  bottombarSlot,
}) {
  const expandBtn = onToggleExpand && showExpandButton ? (
    <button
      type="button"
      className={`nb-icon-btn nb-expand-btn nodrag${expandInField ? " nb-expand-btn--in-field" : ""}`}
      onPointerDown={sp}
      onClick={(e) => { sp(e); onToggleExpand() }}
      title={expandCardOpen ? collapseTitle : expandTitle}
      aria-expanded={expandCardOpen}
    >
      {expandCardOpen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
    </button>
  ) : null

  return (
    <div
      ref={bannerRef}
      className={`nb-banner nodrag nopan${visible ? " nb-banner--visible" : ""}${compact ? " nb-banner--compact" : ""}${modal ? " nb-banner--modal" : ""}${!showTopbar && compact ? " nb-banner--no-topbar" : ""}${promptVariant ? ` nb-banner--prompt-${promptVariant}` : ""}`}
      style={style}
      onPointerDown={onBannerPointerDown}
    >
      {showTopbar && (
        <div className={`nb-topbar${videoTopbarLayout ? " nb-topbar--video" : ""}`}>
          {topbarSlot}
          {!expandInField && expandBtn}
        </div>
      )}

      {mediaSlot ? <div className="nb-banner__media">{mediaSlot}</div> : null}

      <div
        className={`nb-textarea-wrap${expandInField ? " nb-textarea-wrap--in-field-expand" : ""}`}
        ref={textareaWrapRef}
      >
        {textareaSlot}
        {expandInField && expandBtn}
      </div>

      {bottombarSlot}
    </div>
  )
}
