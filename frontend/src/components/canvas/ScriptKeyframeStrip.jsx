import { ensureMediaUrl } from "../../utils/mediaTicket"
import { useLocale } from "../../utils/locale"
import "./ScriptKeyframeStrip.css"

const STATUS_DOT = {
  idle: "st-kf-chip--idle",
  generating: "st-kf-chip--generating",
  completed: "st-kf-chip--completed",
  failed: "st-kf-chip--failed",
}

const sp = (e) => e.stopPropagation()

export default function ScriptKeyframeStrip({ keyframes = [], onLightbox }) {
  const { t } = useLocale()

  if (!keyframes.length) return null

  return (
    <div className="st-kf-strip nodrag" onPointerDown={sp}>
      {keyframes.map((kf) => {
        const thumb = kf.resultUrl
        const title = kf.resultUrl
          ? t("canvas.script.clickFilm")
          : kf.label || t("canvas.script.storyboardCell")
        return (
          <button
            key={kf.id}
            type="button"
            className={`st-kf-chip ${STATUS_DOT[kf.status] || STATUS_DOT.idle}`}
            onClick={() => thumb && onLightbox?.(thumb)}
            onPointerDown={sp}
            title={title}
            disabled={!thumb}
          >
            <span className="st-kf-chip-label cn-label">{kf.label || t("canvas.script.cell")}</span>
            <div className="st-kf-chip-thumb-wrap">
              {thumb ? (
                <img
                  src={ensureMediaUrl(thumb)}
                  alt=""
                  className="st-kf-chip-thumb"
                  draggable={false}
                />
              ) : (
                <span className="st-kf-chip-placeholder">
                  {kf.status === "generating" ? "…" : "—"}
                </span>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}
