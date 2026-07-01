import { LineIcon } from "../icons/LineIcons"
import { useLocale } from "../../utils/locale"

const STARTER_TEMPLATES = [
  {
    id: "ad",
    labelKey: "canvas.empty.template.ad",
    prefillMessage: "我想做一个广告短片",
  },
  {
    id: "drama",
    labelKey: "canvas.empty.template.drama",
    prefillMessage: "我想做一个短剧分镜",
  },
  {
    id: "product",
    labelKey: "canvas.empty.template.product",
    prefillMessage: "我想做一个产品介绍视频",
  },
]

const QUICK_ITEM_KEYS = [
  {
    type: "character",
    accent: "character",
    labelKey: "canvas.empty.role",
    icon: "character",
    action: "open-assets",
    assetView: { contentTab: "subjects", filter: "character" },
  },
  {
    type: "scene",
    accent: "scene",
    labelKey: "canvas.empty.scene",
    icon: "scene",
    action: "open-assets",
    assetView: { contentTab: "subjects", filter: "scene" },
  },
  { type: "video-gen", accent: "video", labelKey: "canvas.empty.video", icon: "video" },
  { type: "image-gen", accent: "image", labelKey: "canvas.empty.image", icon: "image" },
  { type: "text-note", accent: "text", labelKey: "canvas.empty.text", icon: "text" },
]

export default function CanvasEmptyState({ onQuickCreate, onOpenAssets, onStarterTemplate }) {
  const { t } = useLocale()

  const handleTemplateClick = (template) => {
    onStarterTemplate?.(template.prefillMessage)
  }

  const handleClick = (item) => {
    if (item.action === "open-assets") {
      onOpenAssets?.(item.assetView)
      return
    }
    onQuickCreate?.(item.type)
  }

  return (
    <div className="tl-empty-state">
      <div className="tl-empty-templates">
        <p className="tl-empty-templates-label">{t("canvas.empty.templatesLabel")}</p>
        <div className="tl-empty-template-row">
          {STARTER_TEMPLATES.map((template) => (
            <button
              key={template.id}
              type="button"
              className="tl-empty-template-card"
              onClick={() => handleTemplateClick(template)}
            >
              {t(template.labelKey)}
            </button>
          ))}
        </div>
      </div>
      <div className="tl-empty-quick-row">
        {QUICK_ITEM_KEYS.map((item) => (
          <button
            key={item.type}
            type="button"
            className={`tl-empty-chip tl-empty-chip--${item.accent}`}
            onClick={() => handleClick(item)}
          >
            <span className="tl-empty-chip-icon">
              <LineIcon name={item.icon} size={26} />
            </span>
            <span className="tl-empty-chip-label">{t(item.labelKey)}</span>
          </button>
        ))}
      </div>
      <p className="tl-empty-cta">
        <span className="tl-empty-cursor">↖</span>
        {t("canvas.empty.quickAdd")}
      </p>
      <p className="tl-empty-sub">{t("canvas.empty.dblClick")}</p>
    </div>
  )
}
