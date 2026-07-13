import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useStore } from "reactflow"
import { useLocale } from "../../utils/locale"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_DROPDOWN } from "../../utils/zIndexLayers"
import { closeCanvasDropdown, openCanvasDropdown } from "./canvasDropdownCoordinator"
import "./NodeBanner.css"

const sp = (e) => e.stopPropagation()

/** 模型下拉项：名称 + 可选能力说明；disabled 时灰显且不可选 */
export function ModelDropupItem({ model, active, onSelect, disabled = false, disabledHint }) {
  const id = model?.id || model?.display_name
  const name = model?.display_name || model?.id || ""
  const summary = (model?.summary || "").trim()
  const hint = disabled ? (disabledHint || "当前模式不可用") : ""
  const sub = disabled && hint ? hint : summary
  return (
    <button
      type="button"
      className={`nb-dropup-item nodrag${active ? " nb-dropup-item--active" : ""}${disabled ? " nb-dropup-item--disabled" : ""}`}
      disabled={disabled}
      title={disabled ? hint : undefined}
      onClick={(e) => {
        sp(e)
        if (disabled) return
        onSelect?.(id)
      }}
    >
      <span className="nb-dropup-item-name">{name}</span>
      {sub ? <span className="nb-dropup-item-summary">{sub}</span> : null}
    </button>
  )
}

/**
 * 与文本/图像卡一致的模型选择器：固定前置 tag + 下拉菜单（portal 避免被分镜卡遮挡）
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
  const [menuStyle, setMenuStyle] = useState(null)
  const wrapRef = useRef(null)
  const anchorRef = useRef(null)
  const label =
    models.find((m) => m.id === value)?.display_name
    || models.find((m) => (m.id || m.display_name) === value)?.display_name
    || value
    || t("canvas.image.noModel")

  const btnClass = bare ? "nb-model-btn-bare" : "nb-model-btn"
  const menuClass = direction === "up" ? "nb-dropup-menu" : "nb-dropdown-menu"
  const viewportTransform = useStore((s) => s.transform)

  const updateMenuPosition = useCallback(() => {
    const el = anchorRef.current
    if (!el) return false
    const rect = el.getBoundingClientRect()
    if (
      rect.bottom < 0
      || rect.top > window.innerHeight
      || rect.right < 0
      || rect.left > window.innerWidth
    ) {
      return false
    }
    if (direction === "up") {
      setMenuStyle({
        position: "fixed",
        left: rect.left,
        bottom: window.innerHeight - rect.top + 6,
        minWidth: Math.max(rect.width, 220),
        zIndex: Z_DROPDOWN,
      })
    } else {
      setMenuStyle({
        position: "fixed",
        left: rect.left,
        top: rect.bottom + 6,
        minWidth: Math.max(rect.width, 220),
        zIndex: Z_DROPDOWN,
      })
    }
    return true
  }, [direction])

  useEffect(() => {
    if (!open) return undefined

    const closeSelf = () => setOpen(false)
    openCanvasDropdown(closeSelf)
    updateMenuPosition()

    const isInside = (e) => {
      const path = e.composedPath?.() || []
      if (wrapRef.current && path.includes(wrapRef.current)) return true
      return wrapRef.current?.contains(e.target)
    }

    const onPointerDown = (e) => {
      if (!isInside(e) && !e.target.closest?.(".nb-dropdown-menu--portal, .nb-dropup-menu--portal")) {
        closeSelf()
      }
    }
    const onKeyDown = (e) => {
      if (e.key === "Escape") closeSelf()
    }
    const onReflow = () => updateMenuPosition()

    document.addEventListener("pointerdown", onPointerDown, true)
    document.addEventListener("keydown", onKeyDown)
    window.addEventListener("scroll", onReflow, true)
    window.addEventListener("resize", onReflow)

    return () => {
      closeCanvasDropdown(closeSelf)
      document.removeEventListener("pointerdown", onPointerDown, true)
      document.removeEventListener("keydown", onKeyDown)
      window.removeEventListener("scroll", onReflow, true)
      window.removeEventListener("resize", onReflow)
    }
  }, [open, updateMenuPosition])

  // 画布平移/缩放、节点拖动时持续对齐锚点（fixed portal 不随 React Flow transform 自动移动）
  useEffect(() => {
    if (!open) return undefined
    let rafId = 0
    const tick = () => {
      const ok = updateMenuPosition()
      if (!ok) {
        setOpen(false)
        return
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [open, updateMenuPosition, viewportTransform])

  const menuPortal = open && models.length > 0 && menuStyle
    ? createPortal(
        <div
          className={`${menuClass}${direction === "up" ? " nb-dropup-menu--portal" : " nb-dropdown-menu--portal"} nodrag ${getThemePageClass()}`}
          style={menuStyle}
          onPointerDown={sp}
        >
          {models.map((m) => {
            const id = m.id || m.display_name
            const itemDisabled = Boolean(isItemDisabled?.(m))
            return (
              <ModelDropupItem
                key={id}
                model={m}
                active={value === id}
                disabled={itemDisabled}
                disabledHint={disabledHint}
                onSelect={(nextId) => {
                  onChange?.(nextId)
                  setOpen(false)
                }}
              />
            )
          })}
        </div>,
        getThemePortalRoot()
      )
    : null

  return (
    <div
      className={`st-model-dropup nodrag${open ? " st-model-dropup--open" : ""}`}
      title={title}
      ref={wrapRef}
    >
      {tag && <span className="st-model-tag cn-param-key">{tag}</span>}
      <div className="nb-dropup-wrap st-model-dropup-wrap">
        <button
          ref={anchorRef}
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
      {menuPortal}
    </div>
  )
}
