import { useEffect, useRef, useState } from "react"
import "./WorkspaceDropSelect.css"

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M3 7l2.5 2.5L11 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Chevron({ open }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden
      className={`wds-chevron${open ? " wds-chevron--open" : ""}`}
    >
      <path d="M3 4.5 6 7.5 9 4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
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
  const wrapRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => {
      if (!wrapRef.current?.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => { if (e.key === "Escape") setOpen(false) }
    document.addEventListener("mousedown", onDoc)
    window.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDoc)
      window.removeEventListener("keydown", onKey)
    }
  }, [open])

  const selected = options.find((o) => o.value === value)
  const label = selected?.label ?? value

  return (
    <div ref={wrapRef} className={`wds-wrap${className ? ` ${className}` : ""}`}>
      <button
        type="button"
        className={`wds-trigger${open ? " wds-trigger--open" : ""}`}
        onClick={() => setOpen((v) => !v)}
      >
        {prefixIcon && <span className="wds-prefix">{prefixIcon}</span>}
        <span className="wds-label">{label}</span>
        <Chevron open={open} />
      </button>
      {open && (
        <div className={`wds-menu wds-menu--${placement}`} role="listbox">
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
              <span className="wds-custom-label">自定义</span>
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
        </div>
      )}
    </div>
  )
}
