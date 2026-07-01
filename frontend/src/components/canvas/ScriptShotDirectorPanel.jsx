import { useState } from "react"
import { SHOT_DIRECTOR_FIELDS, shotDirectorSummary } from "../../utils/canvas/shotDirectorFields"
import { useLocale } from "../../utils/locale"
import "./ScriptShotDirectorPanel.css"

const sp = (e) => e.stopPropagation()

export default function ScriptShotDirectorPanel({ row, onUpdateRow, readOnly = false }) {
  const { t } = useLocale()
  const [expanded, setExpanded] = useState(false)
  const summary = shotDirectorSummary(row)
  const hasCollapsedPreview =
    !!summary || !!(row.soundNote || "").trim() || !!(row.atmosphereNote || "").trim()

  return (
    <section className="st-shot-director nodrag" onPointerDown={sp}>
      <div className="st-shot-director-head">
        <span className="st-shot-director-title cn-param-key">{t("canvas.script.directorParams")}</span>
        <button
          type="button"
          className="st-director-toggle nodrag"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? t("canvas.common.collapse") : t("canvas.common.expand")}
        </button>
      </div>
      {!expanded && hasCollapsedPreview && (
        <p
          className="st-director-summary cn-body"
          title={[summary, row.soundNote, row.atmosphereNote].filter((s) => s?.trim()).join(" · ")}
        >
          {row.soundNote?.trim() && (
            <span>
              <span className="cn-param-key">{t("canvas.script.soundNote")}</span>
              <span> {row.soundNote.trim()}</span>
            </span>
          )}
          {row.atmosphereNote?.trim() && (
            <span>
              {(row.soundNote?.trim()) && <span className="cn-muted"> · </span>}
              <span className="cn-param-key">{t("canvas.script.qualityMood")}</span>
              <span> {row.atmosphereNote.trim()}</span>
            </span>
          )}
          {SHOT_DIRECTOR_FIELDS.filter(({ key }) => row[key]?.trim()).map(
            ({ key, label }, i) => (
              <span key={key}>
                {(i > 0 || row.soundNote?.trim() || row.atmosphereNote?.trim()) && (
                  <span className="cn-muted"> · </span>
                )}
                <span className="cn-param-key">{label}</span>
                <span> {row[key].trim()}</span>
              </span>
            )
          )}
        </p>
      )}
      {expanded && (
        <div className="st-director-grid">
          <label className="st-director-field st-director-field--wide">
            <span className="st-director-label cn-param-key">{t("canvas.script.soundNote")}</span>
            <input
              className="st-director-input nodrag"
              value={row.soundNote || ""}
              placeholder={t("canvas.script.soundNotePh")}
              disabled={readOnly}
              onChange={(e) => onUpdateRow(row.id, { soundNote: e.target.value })}
              onPointerDown={sp}
            />
          </label>
          <label className="st-director-field st-director-field--wide">
            <span className="st-director-label cn-param-key">{t("canvas.script.qualityMood")}</span>
            <input
              className="st-director-input nodrag"
              value={row.atmosphereNote || ""}
              placeholder={t("canvas.script.atmosphereNotePh")}
              disabled={readOnly}
              onChange={(e) => onUpdateRow(row.id, { atmosphereNote: e.target.value })}
              onPointerDown={sp}
            />
          </label>
          {SHOT_DIRECTOR_FIELDS.map(({ key, label, placeholder }) => (
            <label key={key} className="st-director-field">
              <span className="st-director-label cn-param-key">{label}</span>
              <input
                className="st-director-input nodrag"
                value={row[key] || ""}
                placeholder={placeholder}
                disabled={readOnly}
                onChange={(e) => onUpdateRow(row.id, { [key]: e.target.value })}
                onPointerDown={sp}
              />
            </label>
          ))}
        </div>
      )}
    </section>
  )
}
