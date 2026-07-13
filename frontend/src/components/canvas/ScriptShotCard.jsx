import { useEffect, useMemo, useRef, useState } from "react"
import { MAX_SHOT_DURATION, rowDirectImageReady } from "../../utils/canvas/scriptTableKeyframes"
import { getRetryPolicy } from "../../utils/canvas/generationRetryPolicy"
import { applyQualityPresetToRow } from "../../utils/canvas/scriptQualityPresets"
import { useLocale } from "../../utils/locale"
import ScriptRowPromptField from "./ScriptRowPromptField"
import ScriptShotDirectorPanel from "./ScriptShotDirectorPanel"
import VideoStylePicker from "./VideoStylePicker"
import { closeCanvasDropdown, openCanvasDropdown } from "./canvasDropdownCoordinator"
import "./ScriptShotCard.css"
import "./ScriptKeyframeCard.css"
import "./NodeBanner.css"
import "./VideoStylePicker.css"

function statusLabel(t, status) {
  const map = {
    idle: t("canvas.script.statusPending"),
    pending: t("canvas.script.statusPending"),
    generating: t("canvas.script.statusGenerating"),
    completed: t("canvas.script.statusDone"),
    failed: t("canvas.script.statusFailed"),
  }
  return map[status] || status
}

const DragHandleIcon = () => (
  <svg width="12" height="16" viewBox="0 0 12 16" fill="none" aria-hidden>
    <circle cx="4" cy="4" r="1.2" fill="currentColor" />
    <circle cx="8" cy="4" r="1.2" fill="currentColor" />
    <circle cx="4" cy="8" r="1.2" fill="currentColor" />
    <circle cx="8" cy="8" r="1.2" fill="currentColor" />
    <circle cx="4" cy="12" r="1.2" fill="currentColor" />
    <circle cx="8" cy="12" r="1.2" fill="currentColor" />
  </svg>
)

const sp = (e) => e.stopPropagation()

export default function ScriptShotCard({
  row,
  rowsCount,
  castLibrary,
  sceneLibrary = [],
  batchRunning,
  beatCardKeyframeCount = 0,
  onUpdateRow,
  onDeleteRow,
  onOpenBeatCard,
  onGenerateDirectImage,
  onGenerateDirectVideo,
  onRetryDirect,
  onExpandPrompt,
  onOpenPreview,
  readOnly = false,
  dragOver = false,
  onDragHandleStart,
  onDragOver,
  onDrop,
  onDragEnd,
}) {
  const { t } = useLocale()
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef(null)
  const directReady = rowDirectImageReady(row)
  const generating =
    batchRunning || row.directStatus === "generating" || row.status === "generating"
  const rowStatus = row.directStatus || row.status || "idle"
  const shotPrompt = (row.prompt || row.description || "").trim()
  const presetId = row.qualityPresetId || "auto"
  const sceneOptions = (sceneLibrary || []).filter((s) => s?.name)
  const showRetry = row.directStatus === "failed" || row.status === "failed"
  const retryPolicy = useMemo(
    () => getRetryPolicy(row.error || ""),
    [row.error]
  )

  useEffect(() => {
    if (!moreOpen) return undefined
    const closeSelf = () => setMoreOpen(false)
    openCanvasDropdown(closeSelf)
    const close = (e) => {
      if (moreRef.current && !moreRef.current.contains(e.target)) setMoreOpen(false)
    }
    document.addEventListener("mousedown", close)
    return () => {
      document.removeEventListener("mousedown", close)
      closeCanvasDropdown(closeSelf)
    }
  }, [moreOpen])

  return (
    <article
      className={`st-shot-card st-shot-card--${rowStatus}${readOnly ? " st-shot-card--readonly" : ""}${dragOver ? " st-shot-card--drag-over" : ""}`}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {!readOnly && onDragHandleStart && (
        <div
          role="button"
          tabIndex={0}
          className="st-shot-drag-handle nodrag"
          draggable
          onDragStart={onDragHandleStart}
          onDragEnd={onDragEnd}
          onPointerDown={sp}
          aria-label={t("canvas.script.dragShot")}
        >
          <DragHandleIcon />
        </div>
      )}

      <div className="st-shot-card-head nodrag">
        <div className="st-shot-card-meta">
          <label className="st-shot-card-shot">
            <span className="cn-label">{t("canvas.script.shot")}</span>
            <input
              type="number"
              min={1}
              className="st-shot-num-input nodrag"
              value={row.shotNumber ?? 1}
              disabled={readOnly}
              onChange={(e) => onUpdateRow(row.id, { shotNumber: Number(e.target.value) || 1 })}
              onPointerDown={sp}
            />
          </label>
          <label className="st-shot-card-dur">
            <span className="cn-label">
              {row.duration ?? 8}s
              <span className="st-shot-dur-cap cn-muted">
                {" "}
                / {t("canvas.script.maxSec", { s: MAX_SHOT_DURATION })}
              </span>
            </span>
            <input
              type="range"
              min={2}
              max={MAX_SHOT_DURATION}
              step={1}
              className="st-shot-dur-slider nodrag"
              value={Math.min(MAX_SHOT_DURATION, row.duration ?? 8)}
              disabled={readOnly}
              onChange={(e) => onUpdateRow(row.id, { duration: Number(e.target.value) || 8 })}
              onPointerDown={sp}
            />
          </label>
          <VideoStylePicker
            value={presetId}
            showUploadSection={false}
            readOnly={readOnly}
            title={t("canvas.script.shotStyleTitle")}
            onPresetChange={(id) => onUpdateRow(row.id, applyQualityPresetToRow(row, id))}
          />
          <span className={`st-kf-status st-kf-status--${rowStatus}`}>
            {statusLabel(t, rowStatus)}
          </span>
          {sceneOptions.length > 0 ? (
            <label className="st-shot-card-scene nodrag">
              <span className="cn-label">{t("canvas.script.scene")}</span>
              <select
                className="st-shot-scene-select nodrag"
                value={row.locationId || ""}
                disabled={readOnly}
                onChange={(e) => onUpdateRow(row.id, { locationId: e.target.value || null })}
                onPointerDown={sp}
              >
                <option value="">{t("canvas.script.sceneUnassigned")}</option>
                {sceneOptions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}{!s.imageUrl ? ` (${t("canvas.script.castPending")})` : ""}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
        <div className="st-shot-card-head-right" ref={moreRef}>
          <div className="st-shot-actions">
            <button
              type="button"
              className="st-shot-action-btn"
              disabled={generating}
              onClick={() => onOpenPreview?.(row, null)}
              onPointerDown={sp}
            >
              {t("canvas.script.reviewPrompt")}
            </button>
            <button
              type="button"
              className="st-shot-action-btn"
              disabled={readOnly || generating || !shotPrompt}
              onClick={() => onOpenBeatCard?.(row, { create: true })}
              onPointerDown={sp}
            >
              {t("canvas.script.splitToMultiShot")}
            </button>
            <button
              type="button"
              className="st-shot-action-btn st-shot-more-btn"
              onClick={() => setMoreOpen((v) => !v)}
              onPointerDown={sp}
            >
              {t("canvas.script.moreActions")}
            </button>
            {moreOpen && (
              <div className="st-shot-more-menu nodrag" onPointerDown={sp}>
                <button
                  type="button"
                  disabled={readOnly || generating}
                  onClick={() => {
                    setMoreOpen(false)
                    onExpandPrompt?.(row, null)
                  }}
                >
                  {t("canvas.script.aiExpand")}
                </button>
                <button
                  type="button"
                  className="st-shot-more-danger"
                  disabled={readOnly || rowsCount <= 1}
                  onClick={() => {
                    setMoreOpen(false)
                    onDeleteRow(row.id)
                  }}
                >
                  {t("canvas.common.delete")}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="st-shot-card-body nodrag">
        <ScriptRowPromptField
          value={shotPrompt}
          mentions={row.promptMentions || []}
          castLibrary={castLibrary}
          readOnly={readOnly}
          onChange={(patch) => onUpdateRow(row.id, patch)}
          onPointerDown={sp}
          placeholder={t("canvas.script.shotPlotPh")}
        />
        {row.error && <p className="st-shot-card-error">{row.error}</p>}
        {row.beatCardNodeId && beatCardKeyframeCount > 0 && (
          <button type="button" className="st-shot-beat-link nodrag" onClick={() => onOpenBeatCard?.(row)} onPointerDown={sp}>
            {t("canvas.script.beatCardOpen", { n: beatCardKeyframeCount })}
          </button>
        )}
      </div>

      <ScriptShotDirectorPanel row={row} readOnly={readOnly} onUpdateRow={onUpdateRow} />

      <div className="st-shot-card-foot nodrag">
        <button
          type="button"
          className="st-shot-gen-storyboard"
          disabled={readOnly || generating || !shotPrompt}
          onClick={() => onGenerateDirectImage?.(row)}
          onPointerDown={sp}
        >
          {generating ? t("canvas.script.storyboardGenerating") : t("canvas.script.genStoryboard")}
        </button>
        <button
          type="button"
          className="st-shot-gen-video"
          disabled={readOnly || !directReady || generating}
          onClick={() => onGenerateDirectVideo?.(row)}
          onPointerDown={sp}
        >
          {t("canvas.script.genVideo")}
        </button>
        {showRetry && (
          <button
            type="button"
            className="st-shot-retry-btn"
            disabled={readOnly || generating || !retryPolicy.retryable}
            title={
              !retryPolicy.retryable
                ? t("canvas.gen.retryBlocked", { reason: retryPolicy.reason })
                : undefined
            }
            onClick={() => onRetryDirect?.(row)}
            onPointerDown={sp}
          >
            {t("canvas.script.retryShot")}
          </button>
        )}
      </div>
    </article>
  )
}
