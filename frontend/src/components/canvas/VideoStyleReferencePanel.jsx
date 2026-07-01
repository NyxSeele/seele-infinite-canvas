import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useCanvasStore } from "../../stores"
import { useLocale } from "../../utils/locale"
import {
  deleteStyleReference,
  resolveStyleReferenceTarget,
  updateStyleReference,
  uploadStyleReference,
} from "../../services/styleReferenceApi"
import "./StyleReferencePanel.css"

function SummaryField({ label, value }) {
  if (!value?.trim()) return null
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  )
}

export default function VideoStyleReferencePanel({
  open,
  onClose,
  projectId,
  nodeId,
  scriptTableRef = null,
  styleReference = null,
  readOnly = false,
  onStyleReferenceChange,
}) {
  const { t } = useLocale()
  const theme = useCanvasStore((s) => s.theme)

  const fileRef = useRef(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [keywords, setKeywords] = useState([])

  const target = projectId && nodeId
    ? resolveStyleReferenceTarget({ projectId, nodeId, scriptTableRef })
    : null

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  useEffect(() => {
    if (open && styleReference?.style_keywords) {
      setKeywords([...styleReference.style_keywords])
    } else if (open && !styleReference) {
      setKeywords([])
    }
  }, [open, styleReference])

  const handleUpload = useCallback(
    async (file) => {
      if (!file || !target || readOnly) return
      setError("")
      setAnalyzing(true)
      try {
        const ref = await uploadStyleReference(target, file)
        onStyleReferenceChange?.(ref)
        setKeywords(ref?.style_keywords ? [...ref.style_keywords] : [])
      } catch (e) {
        const detail = e?.response?.data?.detail
        setError(typeof detail === "string" ? detail : t("canvas.styleRef.analyzeFailed"))
      } finally {
        setAnalyzing(false)
      }
    },
    [target, readOnly, onStyleReferenceChange, t]
  )

  const onFileChange = (e) => {
    const file = e.target.files?.[0]
    if (file) handleUpload(file)
    e.target.value = ""
  }

  const onDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file) handleUpload(file)
  }

  const removeKeyword = (kw) => {
    setKeywords((prev) => prev.filter((k) => k !== kw))
  }

  const handleSave = async () => {
    if (!target || !styleReference || readOnly) return
    setSaving(true)
    setError("")
    try {
      const updated = await updateStyleReference(target, { style_keywords: keywords })
      onStyleReferenceChange?.(updated)
    } catch (e) {
      const detail = e?.response?.data?.detail
      setError(typeof detail === "string" ? detail : t("canvas.styleRef.saveFailed"))
    } finally {
      setSaving(false)
    }
  }

  const handleClear = async () => {
    if (!target || readOnly) return
    if (!window.confirm(t("canvas.styleRef.clearConfirm"))) return
    setError("")
    try {
      await deleteStyleReference(target)
      onStyleReferenceChange?.(null)
      setKeywords([])
    } catch (e) {
      const detail = e?.response?.data?.detail
      setError(typeof detail === "string" ? detail : t("canvas.styleRef.clearFailed"))
    }
  }

  if (!open) return null

  const themeClass = theme === "light" ? "rf-page--light" : "rf-page--dark"

  return createPortal(
    <div
      className={`srp-overlay ${themeClass}`}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.()
      }}
    >
      <div className="srp-modal" role="dialog" aria-labelledby="vsrp-title">
        <div id="vsrp-title" className="srp-title">
          {t("canvas.styleRef.title")}
        </div>
        <p className="srp-desc">{t("canvas.styleRef.videoDesc")}</p>

        <div className="srp-body">
          {analyzing ? (
            <div className="srp-loading">
              <div className="srp-spinner" />
              <span>{t("canvas.styleRef.analyzing")}</span>
            </div>
          ) : styleReference ? (
            <>
              {styleReference.display_summary ? (
                <p className="srp-desc srp-desc--summary">{styleReference.display_summary}</p>
              ) : null}
              <dl className="srp-summary">
                <SummaryField label={t("canvas.styleRef.colorTone")} value={styleReference.color_tone} />
                <SummaryField label={t("canvas.styleRef.lighting")} value={styleReference.lighting} />
                <SummaryField
                  label={t("canvas.styleRef.shotLanguage")}
                  value={styleReference.shot_language}
                />
                <SummaryField label={t("canvas.styleRef.atmosphere")} value={styleReference.atmosphere} />
              </dl>
              {keywords.length > 0 ? (
                <div className="srp-chips">
                  {keywords.map((kw) => (
                    <span key={kw} className="srp-chip">
                      {kw}
                      {!readOnly ? (
                        <button type="button" onClick={() => removeKeyword(kw)} aria-label="Remove">
                          ×
                        </button>
                      ) : null}
                    </span>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            !readOnly && (
              <div
                className="srp-drop"
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDrop}
                onClick={() => fileRef.current?.click()}
              >
                <div className="srp-drop-label">{t("canvas.styleRef.uploadLabel")}</div>
                <div className="srp-drop-hint">{t("canvas.styleRef.uploadHint")}</div>
              </div>
            )
          )}
        </div>

        <div className="srp-actions">
          <button type="button" className="srp-btn" onClick={() => onClose?.()}>
            {t("canvas.styleRef.close")}
          </button>
          {styleReference && !readOnly ? (
            <>
              <button
                type="button"
                className="srp-btn"
                onClick={() => fileRef.current?.click()}
                disabled={analyzing}
              >
                {t("canvas.styleRef.reupload")}
              </button>
              <button
                type="button"
                className="srp-btn srp-btn--primary"
                onClick={handleSave}
                disabled={saving || analyzing}
              >
                {saving ? t("canvas.styleRef.saving") : t("canvas.styleRef.save")}
              </button>
              <button type="button" className="srp-btn srp-btn--danger" onClick={handleClear}>
                {t("canvas.styleRef.clear")}
              </button>
            </>
          ) : null}
        </div>

        {error ? <div className="srp-error">{error}</div> : null}

        <input
          ref={fileRef}
          type="file"
          className="srp-hidden-input"
          accept="video/mp4,video/quicktime,.mp4,.mov"
          onChange={onFileChange}
        />
      </div>
    </div>,
    document.body
  )
}
