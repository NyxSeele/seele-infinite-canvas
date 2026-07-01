import { useLocale } from "../../utils/locale"
import { useCanvasStore } from "../../stores"
import "./PromptIntentConfirm.css"

const sp = (e) => e.stopPropagation()

export default function PromptIntentConfirm({
  open,
  loading,
  result,
  editedPrompt = "",
  onEditedPromptChange,
  contextLabel = "",
  onCancel,
  onConfirm,
  onSwitchScreenplay,
}) {
  const { t } = useLocale()
  const theme = useCanvasStore((s) => s.theme)

  if (!open) return null

  const isScreenplay = result?.intent === "screenplay"
  const showGenPrompt = !isScreenplay && (editedPrompt || "").trim().length > 0
  const canForceGen = isScreenplay || showGenPrompt
  const displayContextLabel = contextLabel || t("canvas.intent.currentCard")

  return (
    <div
      className={`pic-backdrop nodrag rf-page rf-page--${theme}`}
      onPointerDown={sp}
      role="presentation"
    >
      <div className="pic-dialog nodrag" onPointerDown={sp}>
        <h3 className="pic-title">{t("canvas.intent.title")}</h3>
        <p className="pic-sub cn-muted">
          {t("canvas.intent.analyzed", { contextLabel: displayContextLabel })}
        </p>

        {loading ? (
          <p className="pic-loading">{t("canvas.intent.recognizing")}</p>
        ) : (
          <>
            <div className="pic-row">
              <span className="cn-param-key">{t("canvas.intent.type")}</span>
              <span className="pic-value">{result?.intent_label || "—"}</span>
              {result?.confidence != null && (
                <span className="pic-conf cn-muted">
                  {t("canvas.intent.confidence", {
                    n: Math.round(Number(result.confidence) * 100),
                  })}
                </span>
              )}
            </div>
            {result?.summary && (
              <p className="pic-summary cn-body">{result.summary}</p>
            )}
            {(result?.warnings || []).map((w) => (
              <p key={w} className="pic-warn">
                {w}
              </p>
            ))}
            {showGenPrompt && (
              <div className="pic-prompt-block">
                <span className="cn-param-key">{t("canvas.intent.promptLabel")}</span>
                <textarea
                  className="pic-prompt-edit nodrag nowheel"
                  value={editedPrompt}
                  onChange={(e) => onEditedPromptChange?.(e.target.value)}
                  rows={Math.min(10, Math.max(4, Math.ceil(editedPrompt.length / 40)))}
                />
              </div>
            )}
            {isScreenplay && (
              <p className="pic-hint cn-body">
                {t("canvas.intent.screenplayWorkflowPrefix")}
                <strong>{t("canvas.prompt.script")}</strong>
                {t("canvas.intent.screenplayWorkflowSuffix")}
              </p>
            )}
          </>
        )}

        <div className="pic-actions nodrag">
          <button type="button" className="pic-btn pic-btn--ghost" onClick={onCancel}>
            {t("canvas.common.cancel")}
          </button>
          {isScreenplay && onSwitchScreenplay && (
            <button
              type="button"
              className="pic-btn pic-btn--secondary"
              disabled={loading || !canForceGen}
              onClick={() => onConfirm?.(editedPrompt)}
            >
              {t("canvas.intent.forceGen")}
            </button>
          )}
          {isScreenplay && onSwitchScreenplay ? (
            <button
              type="button"
              className="pic-btn pic-btn--primary"
              disabled={loading}
              onClick={onSwitchScreenplay}
            >
              {t("canvas.intent.switchScript")}
            </button>
          ) : (
            <button
              type="button"
              className="pic-btn pic-btn--primary"
              disabled={loading || !canForceGen}
              onClick={() => onConfirm?.(editedPrompt)}
            >
              {showGenPrompt ? t("canvas.intent.confirmGen") : t("canvas.intent.forceGen")}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
