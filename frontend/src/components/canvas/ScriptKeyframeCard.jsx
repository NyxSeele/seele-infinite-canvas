import { ensureMediaUrl } from "../../utils/mediaTicket"
import { formatKeyframeTimeRange } from "../../utils/canvas/scriptTableKeyframes"
import { useLocale } from "../../utils/locale"
import ScriptRowPromptField from "./ScriptRowPromptField"
import "./ScriptKeyframeCard.css"

const sp = (e) => e.stopPropagation()

function statusLabel(t, status) {
  const map = {
    idle: t("canvas.script.statusPending"),
    generating: t("canvas.script.statusGenerating"),
    completed: t("canvas.script.statusDone"),
    failed: t("canvas.script.statusFailed"),
  }
  return map[status] || status
}

export default function ScriptKeyframeCard({
  keyframe,
  row,
  castLibrary,
  canDelete,
  onUpdate,
  onDelete,
  onGenerate,
  onPreview,
  onExpand,
  onLightbox,
  generating,
  showTime = true,
  showExtraActions = true,
}) {
  const { t } = useLocale()
  const kf = keyframe

  return (
    <article className={`st-kf-card st-kf-card--${kf.status || "idle"}`}>
      <div className="st-kf-card-head">
        <input
          className="st-kf-label-input nodrag cn-emphasis"
          value={kf.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          placeholder={t("canvas.script.cellLabel")}
          onPointerDown={sp}
        />
        {showTime && (
          <span className="st-kf-time cn-label">{formatKeyframeTimeRange(kf)}</span>
        )}
        <span className={`st-kf-status st-kf-status--${kf.status || "idle"}`}>
          {statusLabel(t, kf.status)}
        </span>
        {canDelete && (
          <button
            type="button"
            className="st-kf-del nodrag"
            onClick={onDelete}
            onPointerDown={sp}
            title={t("canvas.script.deleteKeyframe")}
          >
            ×
          </button>
        )}
      </div>

      <ScriptRowPromptField
        value={kf.prompt || kf.description || ""}
        mentions={kf.promptMentions || []}
        castLibrary={castLibrary}
        onChange={onUpdate}
        onPointerDown={sp}
      />

      <div className="st-kf-media-row nodrag">
        <div className="st-kf-media-block">
          <span className="st-kf-media-label cn-label">{t("canvas.script.filmResult")}</span>
          {kf.resultUrl ? (
            <button
              type="button"
              className="st-kf-result-btn"
              onClick={() => onLightbox(kf.resultUrl)}
              onPointerDown={sp}
              title={t("canvas.script.zoomIn")}
            >
              <img
                src={ensureMediaUrl(kf.resultUrl)}
                alt=""
                className="st-kf-thumb st-kf-thumb--result"
                draggable={false}
              />
            </button>
          ) : (
            <div className="st-kf-thumb-placeholder">—</div>
          )}
        </div>
      </div>

      <div className="st-kf-action-row nodrag">
        {showExtraActions && (
          <>
            <button
              type="button"
              className="st-kf-mini-btn"
              disabled={generating}
              onClick={onExpand}
              onPointerDown={sp}
            >
              {t("canvas.script.expandPrompt")}
            </button>
            <button
              type="button"
              className="st-kf-mini-btn"
              disabled={generating}
              onClick={onPreview}
              onPointerDown={sp}
            >
              {t("canvas.script.previewGen")}
            </button>
          </>
        )}
        <button
          type="button"
          className="st-kf-gen-btn nodrag"
          disabled={generating || kf.status === "generating"}
          onClick={onGenerate}
          onPointerDown={sp}
        >
          {kf.status === "generating"
            ? `${t("canvas.script.statusGenerating")}…`
            : kf.status === "completed"
              ? t("canvas.script.regenCell")
              : t("canvas.script.genThisCell")}
        </button>
      </div>

      {kf.error && <p className="st-kf-error">{kf.error}</p>}
    </article>
  )
}
