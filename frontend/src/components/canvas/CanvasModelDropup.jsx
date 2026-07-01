import { useEffect, useRef, useState } from "react"
import { useLocale } from "../../utils/locale"
import "./NodeBanner.css"

const sp = (e) => e.stopPropagation()

/**
 * 与文本/图像卡一致的模型选择器：固定前置 tag + 下拉菜单
 */
export default function CanvasModelDropup({
  tag,
  icon: Icon,
  models = [],
  value,
  onChange,
  disabled = false,
  bare = true,
  title,
  direction = "down",
}) {
  const { t } = useLocale()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const label =
    models.find((m) => m.id === value)?.display_name
    || models.find((m) => (m.id || m.display_name) === value)?.display_name
    || value
    || t("canvas.image.noModel")

  const btnClass = bare ? "nb-model-btn-bare" : "nb-model-btn"
  const menuClass = direction === "up" ? "nb-dropup-menu" : "nb-dropdown-menu"

  useEffect(() => {
    if (!open) return undefined

    const isInside = (e) => {
      const path = e.composedPath?.() || []
      if (wrapRef.current && path.includes(wrapRef.current)) return true
      return wrapRef.current?.contains(e.target)
    }

    const close = () => setOpen(false)

    const onPointerDown = (e) => {
      if (!isInside(e)) close()
    }
    const onKeyDown = (e) => {
      if (e.key === "Escape") close()
    }
    const onScroll = () => close()

    document.addEventListener("pointerdown", onPointerDown, true)
    document.addEventListener("keydown", onKeyDown)
    window.addEventListener("scroll", onScroll, true)
    window.addEventListener("resize", close)

    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true)
      document.removeEventListener("keydown", onKeyDown)
      window.removeEventListener("scroll", onScroll, true)
      window.removeEventListener("resize", close)
    }
  }, [open])

  return (
    <div className="st-model-dropup nodrag" title={title} ref={wrapRef}>
      {tag && <span className="st-model-tag cn-param-key">{tag}</span>}
      <div className="nb-dropup-wrap st-model-dropup-wrap">
        {open && models.length > 0 && (
          <div className={`${menuClass} nodrag`} onPointerDown={sp}>
            {models.map((m) => {
              const id = m.id || m.display_name
              return (
                <button
                  key={id}
                  type="button"
                  className={`nb-dropup-item nodrag${value === id ? " nb-dropup-item--active" : ""}`}
                  onClick={(e) => {
                    sp(e)
                    onChange?.(id)
                    setOpen(false)
                  }}
                >
                  {m.display_name || m.id}
                </button>
              )
            })}
          </div>
        )}
        <button
          type="button"
          className={`${btnClass} nodrag`}
          disabled={disabled || models.length === 0}
          onPointerDown={sp}
          onClick={(e) => {
            sp(e)
            if (models.length > 0) setOpen((v) => !v)
          }}
        >
          {Icon ? (
            <span className="nb-model-btn-icon" aria-hidden>
              <Icon />
            </span>
          ) : null}
          <span className="nb-model-btn-label">{label}</span>
        </button>
      </div>
    </div>
  )
}
