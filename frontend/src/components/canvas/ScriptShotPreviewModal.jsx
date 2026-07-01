import { useCallback, useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { useCanvasStore } from "../../stores"
import { useLocale } from "../../utils/locale"
import "../../pages/Canvas.css"
import "./ScriptShotPreviewModal.css"

const sp = (e) => e.stopPropagation()

export default function ScriptShotPreviewModal({
  open,
  title,
  pkg,
  loading = false,
  sourceLabel = "",
  onClose,
  onExpandLlm,
  onConfirmGenerate,
  confirmLabel,
  commitDisabled = false,
}) {
  const { t } = useLocale()
  const theme = useCanvasStore((s) => s.theme)
  const [expertEdit, setExpertEdit] = useState(false)
  const [draft, setDraft] = useState(pkg?.fullText || "")

  const resolvedTitle = title ?? t("canvas.script.previewTitle")
  const resolvedConfirmLabel = confirmLabel ?? t("canvas.script.confirmGen")

  useEffect(() => {
    if (open && pkg) {
      setDraft(pkg.fullText || "")
      setExpertEdit(false)
    }
  }, [open, pkg])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(draft || pkg?.fullText || "")
    } catch {
      /* ignore */
    }
  }, [draft, pkg])

  if (!open || !pkg) return null

  return createPortal(
    <div className={`rf-page rf-page--${theme} st-preview-overlay st-preview-overlay--${theme} nodrag nopan`} onClick={onClose} onPointerDown={sp}>
      <div
        className={`st-preview-modal st-preview-modal--${theme} nodrag`}
        onClick={sp}
        onPointerDown={sp}
        onDoubleClick={sp}
      >
        <div className="st-preview-head">
          <h3 className="st-preview-title cn-title">{resolvedTitle}</h3>
          {sourceLabel && <span className="st-preview-source cn-label">{sourceLabel}</span>}
          <button type="button" className="st-preview-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="st-preview-actions nodrag">
          <button
            type="button"
            className="st-preview-btn"
            disabled={commitDisabled || loading}
            onClick={() => onExpandLlm?.()}
          >
            {loading ? t("canvas.script.expanding") : t("canvas.script.llmExpand")}
          </button>
          <button type="button" className="st-preview-btn st-preview-btn--muted" onClick={handleCopy}>
            {t("canvas.script.copyFull")}
          </button>
          <label className="st-preview-expert-toggle">
            <input
              type="checkbox"
              checked={expertEdit}
              disabled={commitDisabled}
              onChange={(e) => setExpertEdit(e.target.checked)}
            />
            {t("canvas.script.expertEdit")}
          </label>
        </div>

        <div className="st-preview-body scrollable-content nowheel">
          {expertEdit ? (
            <textarea
              className="st-preview-editor nodrag nowheel"
              value={draft}
              readOnly={commitDisabled}
              onChange={(e) => setDraft(e.target.value)}
            />
          ) : (
            <>
              <section className="st-preview-section">
                <h4 className="st-preview-section-title cn-section-title">{t("canvas.script.basicSettings")}</h4>
                <pre className="st-preview-pre cn-body">{pkg.basic}</pre>
              </section>
              <section className="st-preview-section">
                <h4 className="st-preview-section-title cn-section-title">{t("canvas.script.moodQuality")}</h4>
                <pre className="st-preview-pre cn-body">{pkg.atmosphere}</pre>
              </section>
              <section className="st-preview-section">
                <h4 className="st-preview-section-title cn-section-title">{t("canvas.script.visualContent")}</h4>
                <pre className="st-preview-pre cn-body">{pkg.frames}</pre>
              </section>
            </>
          )}
        </div>

        <div className="st-preview-footer nodrag">
          <button type="button" className="st-preview-btn st-preview-btn--muted" onClick={onClose}>
            {t("canvas.common.cancel")}
          </button>
          <button
            type="button"
            className="st-preview-btn st-preview-btn--primary"
            disabled={commitDisabled || loading}
            onClick={() =>
              onConfirmGenerate?.({
                ...pkg,
                fullText: expertEdit ? draft : pkg.fullText,
                apiDescription: expertEdit ? draft : pkg.apiDescription,
              })
            }
          >
            {resolvedConfirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}
