import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useStore } from "reactflow"
import { useLocale } from "../../utils/locale"
import {
  SCRIPT_QUALITY_PRESETS,
  getQualityPreset,
  normalizeQualityPresetId,
} from "../../utils/canvas/scriptQualityPresets"
import { styleReferenceSummary } from "../../utils/canvas/styleReferenceFormat"
import { closeCanvasDropdown, openCanvasDropdown } from "./canvasDropdownCoordinator"
import { useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_DROPDOWN } from "../../utils/zIndexLayers"
import { IconQualityStyle, IconStyleRef } from "./CanvasTopbarIcons"
import "./VideoStylePicker.css"

const sp = (e) => e.stopPropagation()

export default function VideoStylePicker({
  value = "auto",
  styleReference = null,
  onPresetChange,
  onUploadClick,
  disabled = false,
  readOnly = false,
  showUploadSection = true,
  title,
}) {
  const { t } = useLocale()
  const [open, setOpen] = useState(false)
  const [menuStyle, setMenuStyle] = useState(null)
  const wrapRef = useRef(null)
  const anchorRef = useRef(null)
  const listRef = useRef(null)
  const [showScrollHint, setShowScrollHint] = useState(false)
  const viewportTransform = useStore((s) => s.transform)

  const presetId = normalizeQualityPresetId(value)
  const preset = getQualityPreset(presetId)
  const hasUpload = showUploadSection && !!styleReference
  const uploadSummary = hasUpload ? styleReferenceSummary(styleReference) : ""

  const displayName = useMemo(() => {
    const name = preset?.name || t("canvas.stylePicker.auto")
    if (!showUploadSection) return name
    if (hasUpload && presetId === "auto") {
      return t("canvas.stylePicker.refOnly")
    }
    if (hasUpload) return `${name} · ${t("canvas.stylePicker.refShort")}`
    return name
  }, [preset, presetId, hasUpload, showUploadSection, t])

  const triggerText = useMemo(
    () => t("canvas.stylePicker.tagValue", { name: displayName }),
    [displayName, t]
  )

  const isActive = showUploadSection
    ? presetId !== "auto" || hasUpload
    : presetId !== "auto"

  const triggerTitle = title
    || (hasUpload ? uploadSummary : t("canvas.stylePicker.title"))

  const updateScrollHint = useCallback(() => {
    const el = listRef.current
    if (!el) {
      setShowScrollHint(false)
      return
    }
    const canScroll = el.scrollHeight > el.clientHeight + 2
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 8
    setShowScrollHint(canScroll && !atBottom)
  }, [])

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
    const menuWidth = 280
    const left = Math.min(rect.left, window.innerWidth - menuWidth - 12)
    setMenuStyle({
      position: "fixed",
      left: Math.max(12, left),
      top: rect.bottom + 6,
      width: menuWidth,
      zIndex: Z_DROPDOWN,
    })
    return true
  }, [])

  useEffect(() => {
    if (!open) return undefined

    const closeSelf = () => setOpen(false)
    openCanvasDropdown(closeSelf)
    if (!updateMenuPosition()) {
      setOpen(false)
      return undefined
    }

    const isInside = (e) => {
      const path = e.composedPath?.() || []
      if (wrapRef.current && path.includes(wrapRef.current)) return true
      const menu = document.querySelector(".vsp-menu-portal")
      return menu && path.includes(menu)
    }

    const onPointerDown = (e) => {
      if (!isInside(e)) setOpen(false)
    }

    let rafId = 0
    const tick = () => {
      if (!updateMenuPosition()) {
        setOpen(false)
        return
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)

    document.addEventListener("pointerdown", onPointerDown, true)
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true)
      cancelAnimationFrame(rafId)
      closeCanvasDropdown(closeSelf)
    }
  }, [open, updateMenuPosition, viewportTransform])

  const handlePresetSelect = (id) => {
    if (readOnly || disabled) return
    onPresetChange?.(id)
    setOpen(false)
  }

  const handleUpload = (e) => {
    sp(e)
    if (readOnly || disabled) return
    setOpen(false)
    onUploadClick?.()
  }

  const menuVisible = open && Boolean(menuStyle)
  const { mounted: menuMounted, closing: menuClosing } = useOverlayMount(menuVisible)

  useEffect(() => {
    if (!open) {
      setShowScrollHint(false)
      return undefined
    }
    if (!menuMounted) return undefined

    let raf2 = 0
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => updateScrollHint())
    })

    const el = listRef.current
    if (!el) {
      return () => {
        cancelAnimationFrame(raf1)
        cancelAnimationFrame(raf2)
      }
    }

    const ro = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(() => updateScrollHint())
      : null
    ro?.observe(el)
    el.addEventListener("scroll", updateScrollHint, { passive: true })
    return () => {
      cancelAnimationFrame(raf1)
      cancelAnimationFrame(raf2)
      ro?.disconnect()
      el.removeEventListener("scroll", updateScrollHint)
    }
  }, [open, menuMounted, updateScrollHint])

  const menuClasses = overlayClassNames({
    mounted: menuMounted,
    closing: menuClosing,
    open: menuVisible,
    base: `vsp-menu vsp-menu-portal ${getThemePageClass()}`,
    enterClass: menuVisible && !menuClosing ? "motion-popover-in" : "",
    exitClass: menuClosing ? "motion-popover-out" : "",
  })

  const menu = menuMounted && menuStyle
    ? createPortal(
        <div className={menuClasses} style={menuStyle} onPointerDown={sp}>
          <div className="vsp-menu-header">{t("canvas.stylePicker.presetSection")}</div>
          <div className={`vsp-preset-scroll-wrap${showScrollHint ? " vsp-preset-scroll-wrap--more" : ""}`}>
            <div
              ref={listRef}
              className="vsp-preset-list"
              role="listbox"
              aria-label={t("canvas.stylePicker.presetSection")}
              onScroll={updateScrollHint}
            >
              {SCRIPT_QUALITY_PRESETS.map((p) => {
                const selected = p.id === presetId
                return (
                  <button
                    key={p.id}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    className={`vsp-preset-item${selected ? " vsp-preset-item--active" : ""}`}
                    onClick={() => handlePresetSelect(p.id)}
                    disabled={readOnly}
                  >
                    <span className="vsp-preset-item-name">{p.name}</span>
                    {p.atmosphereNote ? (
                      <span className="vsp-preset-item-hint">{p.atmosphereNote}</span>
                    ) : p.id === "auto" ? (
                      <span className="vsp-preset-item-hint">{t("canvas.stylePicker.autoHint")}</span>
                    ) : null}
                    {selected ? <span className="vsp-preset-check" aria-hidden>✓</span> : null}
                  </button>
                )
              })}
            </div>
            {showScrollHint ? (
              <div className="vsp-scroll-hint" aria-hidden>
                {t("canvas.stylePicker.scrollMore")}
              </div>
            ) : null}
          </div>
          {showUploadSection ? (
            <>
              <div className="vsp-menu-divider" />
              <button
                type="button"
                className={`vsp-upload-row${hasUpload ? " vsp-upload-row--active" : ""}`}
                onClick={handleUpload}
                disabled={readOnly || disabled}
                aria-label={hasUpload ? t("canvas.stylePicker.manageUpload") : t("canvas.stylePicker.uploadVideo")}
              >
                <span className="vsp-upload-icon" aria-hidden>
                  <IconStyleRef />
                </span>
                <span className="vsp-upload-text">
                  <span className="vsp-upload-title">
                    {hasUpload
                      ? t("canvas.stylePicker.manageUpload")
                      : t("canvas.stylePicker.uploadVideo")}
                  </span>
                  <span className="vsp-upload-hint">
                    {hasUpload
                      ? uploadSummary || t("canvas.styleRef.uploadHint")
                      : t("canvas.styleRef.uploadHint")}
                  </span>
                </span>
                {hasUpload ? <span className="vsp-upload-dot" aria-hidden /> : null}
              </button>
            </>
          ) : null}
        </div>,
        getThemePortalRoot()
      )
    : null

  return (
    <div className="vsp-wrap nodrag nopan" ref={wrapRef}>
      <button
        ref={anchorRef}
        type="button"
        className={`vsp-trigger nodrag nopan${open ? " vsp-trigger--open" : ""}${isActive ? " vsp-trigger--active" : ""}`}
        disabled={disabled}
        title={triggerTitle}
        onPointerDown={sp}
        onClick={(e) => {
          sp(e)
          if (!disabled) setOpen((v) => !v)
        }}
      >
        <span className="vsp-trigger-icon" aria-hidden>
          <IconQualityStyle />
        </span>
        <span className="vsp-trigger-label">{triggerText}</span>
        {hasUpload ? <span className="vsp-trigger-dot" aria-hidden /> : null}
      </button>
      {menu}
    </div>
  )
}
