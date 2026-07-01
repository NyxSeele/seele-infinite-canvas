import { Wand2, Plus, ArrowLeftRight, Maximize2, BarChart2, Settings, Mic, ArrowUp, Volume2 } from "lucide-react"
import { useLocale } from "../../utils/locale"
import "./NodeBanner.css"

const sp = (e) => e.stopPropagation()

export default function NodeBanner({
  modelName = "—",
  resolution = "1:1",
  onGenerate,
  onPromptChange,
  prompt = "",
  onMagicPrompt,
  onAddReference,
  sizeOptions = [],
  sizeIndex = 0,
  onSizeChange,
  nodeType = "image",
  selected = false,
}) {
  const { t } = useLocale()

  const handleSend = (e) => {
    e?.stopPropagation()
    if (!prompt?.trim()) return
    onGenerate?.()
  }

  const handleCycleSize = (e) => {
    sp(e)
    if (!sizeOptions.length) return
    onSizeChange?.((sizeIndex + 1) % sizeOptions.length)
  }

  const currentSizeLabel = sizeOptions[sizeIndex]?.label

  return (
    <div
      className={`nb-banner nodrag nopan${selected ? " nb-banner--visible" : ""}`}
      onMouseDown={sp}
      onPointerDown={sp}
      onClick={sp}
    >
      <div className="nb-topbar">
        <div className="nb-topbar-left">
          <button
            className="nb-icon-btn nodrag"
            onPointerDown={sp}
            onMouseDown={sp}
            onClick={(e) => { sp(e); onMagicPrompt?.() }}
            title={t("canvas.prompt.magic")}
          >
            <Wand2 size={15} />
          </button>
          <div className="nb-btn-sep" />
          <button
            className="nb-icon-btn nodrag"
            onPointerDown={sp}
            onMouseDown={sp}
            onClick={(e) => { sp(e); onAddReference?.() }}
            title={t("canvas.prompt.addRef")}
          >
            <Plus size={15} />
          </button>
          <button
            className="nb-icon-btn nodrag"
            onPointerDown={sp}
            onMouseDown={sp}
            onClick={handleCycleSize}
            title={
              sizeOptions.length
                ? t("canvas.prompt.switchSizeCurrent", { label: currentSizeLabel })
                : t("canvas.prompt.switchOrient")
            }
          >
            <ArrowLeftRight size={15} />
          </button>
          <button
            className="nb-icon-btn nodrag"
            onPointerDown={sp}
            onMouseDown={sp}
            onClick={sp}
            title={t("canvas.common.more")}
          >
            <Plus size={15} />
          </button>
        </div>
        <button
          className="nb-icon-btn nodrag"
          onPointerDown={sp}
          onMouseDown={sp}
          onClick={sp}
          title={t("canvas.common.expand")}
        >
          <Maximize2 size={15} />
        </button>
      </div>

      <textarea
        className="nb-textarea nodrag nowheel"
        placeholder={t("canvas.prompt.nodeBannerPh")}
        value={prompt}
        onChange={(e) => onPromptChange?.(e.target.value)}
        onPointerDown={sp}
        onMouseDown={sp}
        onClick={sp}
        onKeyDown={(e) => {
          sp(e)
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend()
        }}
      />

      <div className="nb-bottombar">
        <div className="nb-bottom-left">
          <BarChart2 size={14} className="nb-model-icon" />
          <span className="nb-model-name">{modelName}</span>
          <div className="nb-bottom-sep" />
          <span className="nb-resolution">{resolution}</span>
          <Volume2 size={13} className="nb-mic-icon" />
          <Settings size={13} className="nb-settings-icon" />
        </div>
        <div className="nb-bottom-right">
          <Mic size={14} className="nb-mic-icon" />
          <span className="nb-speed-text">1×</span>
          <span className="nb-credits-badge">88</span>
          <button
            className="nb-send-btn nodrag"
            disabled={!prompt?.trim()}
            onPointerDown={sp}
            onMouseDown={sp}
            onClick={handleSend}
            title={t("canvas.prompt.genShortcut")}
          >
            <ArrowUp size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
