import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_DROPDOWN } from "../../utils/zIndexLayers"
import "./WorkspaceDropSelect.css"

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M3 7l2.5 2.5L11 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function WorkspaceDropSelect({
  value,
  options,
  onChange,
  prefixIcon = null,
  customOption = null,
  onCustomChange,
  customValue = "",
  className = "",
  placement = "bottom",
}) {
  const [open, setOpen] = useState(false)
  const [menuStyle, setMenuStyle] = useState(null)
  const wrapRef = useRef(null)
  const triggerRef = useRef(null)
  const menuRef = useRef(null)
  const { mounted, closing } = useOverlayMount(open)

  const updateMenuPosition = useCallback(() => {
    const el = triggerRef.current
    if (!el) return false
    const rect = el.getBoundingClientRect()
    const style = {
      position: "fixed",
      left: rect.left,
      minWidth: Math.max(rect.width, 168),
      zIndex: Z_DROPDOWN,
    }
    if (placement === "top") {
      style.bottom = window.innerHeight - rect.top + 8
      style.top = "auto"
    } else {
      style.top = rect.bottom + 8
    }
    setMenuStyle(style)
    return true
  }, [placement])

  useEffect(() => {
    if (!open) {
      setMenuStyle(null)
      return undefined
    }
    updateMenuPosition()

    const onDoc = (e) => {
      const path = e.composedPath?.() || []
      if (wrapRef.current && path.includes(wrapRef.current)) return
      if (menuRef.current && path.includes(menuRef.current)) return
      setOpen(false)
    }
    const onKey = (e) => { if (e.key === "Escape") setOpen(false) }

    let rafId = 0
    const tick = () => {
      updateMenuPosition()
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)

    document.addEventListener("mousedown", onDoc)
    window.addEventListener("keydown", onKey)
    window.addEventListener("resize", updateMenuPosition)
    window.addEventListener("scroll", updateMenuPosition, true)
    return () => {
      cancelAnimationFrame(rafId)
      document.removeEventListener("mousedown", onDoc)
      window.removeEventListener("keydown", onKey)
      window.removeEventListener("resize", updateMenuPosition)
      window.removeEventListener("scroll", updateMenuPosition, true)
    }
  }, [open, updateMenuPosition])

  const selected = options.find((o) => o.value === value)
  const label = selected?.label ?? value

  const menuClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: `wds-menu wds-menu-portal ws-overlay-root wds-menu--${placement} ${getThemePageClass()}`,
    enterClass: open && !closing
      ? (placement === "top" ? "motion-popover-in motion-popover-in--top" : "motion-popover-in")
      : "",
    exitClass: closing
      ? (placement === "top" ? "motion-popover-out motion-popover-out--top" : "motion-popover-out")
      : "",
  })

  const menu = mounted && menuStyle
    ? createPortal(
        <div ref={menuRef} className={menuClasses} style={menuStyle} role="listbox">
          {options.map((opt) => {
            const active = opt.value === value
            return (
              <button
                key={opt.value}
                type="button"
                className={`wds-item${active ? " wds-item--active" : ""}`}
                onClick={() => {
                  onChange?.(opt.value)
                  setOpen(false)
                }}
              >
                <span className="wds-item-mark">
                  {active ? <CheckIcon /> : <span className="wds-dot" />}
                </span>
                {opt.icon && <span className="wds-item-icon">{opt.icon}</span>}
                <span className="wds-item-text">{opt.label}</span>
              </button>
            )
          })}
          {customOption && (
            <div className="wds-custom-row">
              <span className="wds-item-mark">
                {value === "custom" ? <CheckIcon /> : <span className="wds-dot" />}
              </span>
              <input
                type="number"
                className="wds-custom-input"
                min={1}
                max={200}
                value={customValue}
                onChange={(e) => {
                  onCustomChange?.(e.target.value)
                  onChange?.("custom")
                }}
                onFocus={() => onChange?.("custom")}
              />
              <span className="wds-custom-suffix">{customOption.suffix || "集"}</span>
            </div>
          )}
        </div>,
        getThemePortalRoot(),
      )
    : null

  return (
    <div ref={wrapRef} className={`wds-wrap${className ? ` ${className}` : ""}`}>
      <button
        ref={triggerRef}
        type="button"
        className={`wds-trigger${open ? " wds-trigger--open" : ""}`}
        onClick={() => setOpen((v) => !v)}
      >
        {prefixIcon && <span className="wds-prefix">{prefixIcon}</span>}
        <span className="wds-label">{label}</span>
      </button>
      {menu}
    </div>
  )
}
