import { useCallback, useEffect, useRef, useState } from "react"
import { useLocale } from "../../utils/locale"
import { saveAsWord } from "../../utils/canvas/saveAsWord"
import "./NodeCardDotsMenu.css"

const sp = (e) => e.stopPropagation()

export default function NodeCardDotsMenu({
  text = "",
  filenamePrefix = "export",
  visible = true,
  extraItems = [],
}) {
  const { t } = useLocale()
  const [menuOpen, setMenuOpen] = useState(false)
  const [copyDone, setCopyDone] = useState(false)
  const menuRef = useRef(null)
  const copyTimerRef = useRef(null)

  const hasText = Boolean(text?.trim())

  useEffect(() => {
    if (!menuOpen) return undefined
    const close = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener("mousedown", close)
    return () => document.removeEventListener("mousedown", close)
  }, [menuOpen])

  useEffect(() => () => clearTimeout(copyTimerRef.current), [])

  const handleCopyAll = useCallback(
    async (e) => {
      sp(e)
      if (!hasText) return
      try {
        await navigator.clipboard.writeText(text)
        setCopyDone(true)
        clearTimeout(copyTimerRef.current)
        copyTimerRef.current = setTimeout(() => setCopyDone(false), 2000)
      } catch {
        /* ignore */
      }
      setMenuOpen(false)
    },
    [hasText, text]
  )

  const handleSaveWord = useCallback(
    (e) => {
      sp(e)
      if (!hasText) return
      saveAsWord(text, `${filenamePrefix}_${new Date().toLocaleDateString()}`)
      setMenuOpen(false)
    },
    [hasText, text, filenamePrefix]
  )

  if (!visible) return null

  return (
    <div ref={menuRef} className="ncd-menu-wrap nodrag">
      <button
        type="button"
        className="ncd-dots-btn nodrag"
        onPointerDown={sp}
        onClick={(e) => {
          sp(e)
          setMenuOpen((v) => !v)
        }}
        aria-label={t("canvas.common.moreActions")}
      >
        ⋯
      </button>
      {menuOpen && (
        <div className="ncd-dropdown nodrag" onPointerDown={sp}>
          <button
            type="button"
            className="ncd-dropdown-item"
            disabled={!hasText}
            onClick={handleCopyAll}
          >
            {copyDone ? t("canvas.text.copied") : t("canvas.text.copyAll")}
          </button>
          <button
            type="button"
            className="ncd-dropdown-item"
            disabled={!hasText}
            onClick={handleSaveWord}
          >
            {t("canvas.text.saveWord")}
          </button>
          {extraItems.map((item) => (
            <button
              key={item.key || item.label}
              type="button"
              className="ncd-dropdown-item"
              disabled={item.disabled}
              onClick={(e) => {
                sp(e)
                item.onClick?.(e)
                setMenuOpen(false)
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
