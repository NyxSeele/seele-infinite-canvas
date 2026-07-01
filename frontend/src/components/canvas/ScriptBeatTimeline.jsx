import { ensureMediaUrl } from "../../utils/mediaTicket"
import { rowHasBeatPrompts } from "../../utils/canvas/scriptTableKeyframes"
import { useLocale } from "../../utils/locale"
import "./ScriptBeatTimeline.css"

const sp = (e) => e.stopPropagation()

export default function ScriptBeatTimeline({
  row,
  keyframes = [],
  splitting = false,
  splitSource = "",
  onLightbox,
  onUpdateBeatPrompt,
  onUpdateBeatLabel,
  onDeleteKeyframe,
  onAddKeyframe,
  canAddKeyframe = true,
  readOnly = false,
}) {
  const { t } = useLocale()
  const hasBeatPrompts = row
    ? rowHasBeatPrompts(row)
    : keyframes.some((kf) => (kf.prompt || kf.description || "").trim())

  if (splitting) {
    return (
      <div className="st-beat-timeline st-beat-timeline--loading nodrag" onPointerDown={sp}>
        <p className="st-beat-timeline-msg cn-body">{t("canvas.script.beatSplitting")}</p>
      </div>
    )
  }

  if (!keyframes.length || !hasBeatPrompts) {
    return (
      <div className="st-beat-timeline st-beat-timeline--empty nodrag" onPointerDown={sp}>
        <p className="st-beat-timeline-msg cn-muted">
          {t("canvas.script.beatNotSplit")}
        </p>
      </div>
    )
  }

  const canDelete = keyframes.length > 1
  const splitSourceLabel = splitSource === "llm"
    ? t("canvas.script.beatSplitAi")
    : t("canvas.script.beatSplitRules")

  return (
    <div className="st-beat-timeline nodrag" onPointerDown={sp}>
      <div className="st-beat-timeline-head">
        {splitSource && (
          <p className="st-beat-timeline-source cn-label">
            {t("canvas.script.beatSplitPrefix", { source: splitSourceLabel })}
          </p>
        )}
        <p className="st-beat-timeline-hint cn-muted">
          {t("canvas.script.beatEditHint")}
        </p>
      </div>
      <div
        className="st-beat-timeline-grid"
        style={{
          gridTemplateColumns: `repeat(${Math.max(1, keyframes.length)}, minmax(0, 1fr))`,
        }}
      >
        {keyframes.map((kf) => {
          const thumb = kf.resultUrl
          const prompt = (kf.prompt || kf.description || "").trim()
          return (
            <div key={kf.id} className={`st-beat-item st-beat-item--${kf.status || "idle"}`}>
              <div className="st-beat-item-head">
                <input
                  className="st-beat-label-input nodrag cn-emphasis"
                  value={kf.label || ""}
                  placeholder={t("canvas.script.cellLabel")}
                  disabled={readOnly}
                  onChange={(e) => onUpdateBeatLabel?.(kf.id, e.target.value)}
                  onPointerDown={sp}
                />
                {canDelete && (
                  <button
                    type="button"
                    className="st-beat-del nodrag"
                    title={t("canvas.script.deleteCell")}
                    disabled={readOnly}
                    onClick={() => onDeleteKeyframe?.(kf.id)}
                    onPointerDown={sp}
                  >
                    ×
                  </button>
                )}
              </div>

              <div className="st-beat-media-row">
                <div className="st-beat-media-block">
                  <span className="st-beat-media-label cn-label">{t("canvas.script.storyboard")}</span>
                  <div className="st-beat-media-frame">
                    <button
                      type="button"
                      className="st-beat-thumb-btn st-beat-result-btn"
                      disabled={!thumb}
                      onClick={() => thumb && onLightbox?.(thumb)}
                      onPointerDown={sp}
                      title={t("canvas.script.filmPreview")}
                    >
                      {thumb ? (
                        <img
                          src={ensureMediaUrl(thumb)}
                          alt=""
                          className="st-beat-thumb"
                          draggable={false}
                        />
                      ) : (
                        <span className="st-beat-thumb-ph">
                          {kf.status === "generating" ? "…" : t("canvas.script.storyboard")}
                        </span>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {onUpdateBeatPrompt ? (
                <textarea
                  className="st-beat-prompt-edit nodrag nowheel cn-body"
                  value={prompt}
                  rows={4}
                  placeholder={t("canvas.script.cellDesc")}
                  readOnly={readOnly}
                  onChange={(e) => onUpdateBeatPrompt?.(kf.id, e.target.value)}
                  onPointerDown={sp}
                />
              ) : (
                <p className="st-beat-prompt cn-body" title={prompt}>
                  {prompt || t("canvas.script.descPending")}
                </p>
              )}
              {kf.actionNote && (
                <p className="st-beat-action cn-label" title={kf.actionNote}>
                  {kf.actionNote}
                </p>
              )}
              {kf.error && (
                <p className="st-beat-error">{kf.error}</p>
              )}
            </div>
          )
        })}
      </div>
      {canAddKeyframe && onAddKeyframe && (
        <button
          type="button"
          className="st-beat-add-btn nodrag"
          disabled={readOnly}
          onClick={onAddKeyframe}
          onPointerDown={sp}
        >
          {t("canvas.script.addCell")}
        </button>
      )}
    </div>
  )
}
