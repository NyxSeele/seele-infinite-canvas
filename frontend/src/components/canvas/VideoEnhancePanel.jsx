import { useState } from "react"
import { useLocale } from "../../utils/locale"
import "./VideoEnhancePanel.css"

function LabelWithTip({ label, tip, tipKey, openTipKey, onToggleTip }) {
  if (!tip) {
    return <span className="video-enhance-panel-label">{label}</span>
  }
  const isOpen = openTipKey === tipKey
  return (
    <span className="video-enhance-panel-label-row">
      <span className="video-enhance-panel-label">{label}</span>
      <button
        type="button"
        className={`video-enhance-panel-info-btn nodrag nopan${isOpen ? " is-open" : ""}`}
        onClick={(e) => {
          e.stopPropagation()
          onToggleTip(tipKey)
        }}
        onPointerDown={(e) => e.stopPropagation()}
        aria-label={label}
        aria-expanded={isOpen}
      >
        ⓘ
      </button>
    </span>
  )
}

function FieldBlock({ children, tip, tipKey, openTipKey }) {
  return (
    <div className="video-enhance-panel-field-block">
      {children}
      {tip && openTipKey === tipKey ? (
        <div className="video-enhance-panel-info-banner">{tip}</div>
      ) : null}
    </div>
  )
}

function AdvancedFields({
  t,
  disabled,
  upscaleFactor,
  strength,
  inputNoiseScale,
  batchSize,
  colorCorrection,
  modelSize,
  onUpscaleChange,
  onStrengthChange,
  onInputNoiseScaleChange,
  onBatchSizeChange,
  onColorCorrectionChange,
  onModelSizeChange,
  compact = false,
}) {
  const [openTipKey, setOpenTipKey] = useState(null)
  const toggleTip = (key) => {
    setOpenTipKey((prev) => (prev === key ? null : key))
  }

  const rowClass = compact
    ? "video-enhance-panel-compact-field"
    : "video-enhance-panel-row"
  const selectClass = compact
    ? "video-enhance-panel-select video-enhance-panel-select--compact nodrag nopan"
    : "video-enhance-panel-select nodrag nopan"

  const labelProps = { openTipKey, onToggleTip: toggleTip }

  return (
    <>
      <div className={rowClass}>
        <LabelWithTip label={t("canvas.video.enhanceUpscale")} />
        <select
          className={selectClass}
          value={String(upscaleFactor)}
          disabled={disabled}
          onChange={(e) => onUpscaleChange?.(Number(e.target.value))}
        >
          <option value="1">{t("canvas.video.enhanceUpscale1x")}</option>
          <option value="1.5">1.5x</option>
          <option value="2">2x</option>
          <option value="3">3x</option>
        </select>
      </div>
      <div className={rowClass}>
        <LabelWithTip label={t("canvas.video.enhanceStrength")} />
        <select
          className={selectClass}
          value={strength}
          disabled={disabled}
          onChange={(e) => onStrengthChange?.(e.target.value)}
        >
          <option value="normal">{t("canvas.video.enhanceStrengthNormal")}</option>
          <option value="sharp">{t("canvas.video.enhanceStrengthSharp")}</option>
        </select>
      </div>
      <div className="video-enhance-panel-fine-divider">
        <span>{t("canvas.video.enhanceFineControl")}</span>
      </div>
      <FieldBlock
        tipKey="noise"
        tip={t("canvas.video.enhanceNoiseScaleTip")}
        openTipKey={openTipKey}
      >
        <div className={rowClass}>
          <LabelWithTip
            label={t("canvas.video.enhanceNoiseScale")}
            tip={t("canvas.video.enhanceNoiseScaleTip")}
            tipKey="noise"
            {...labelProps}
          />
          <input
            type="range"
            className="video-enhance-panel-slider nodrag nopan"
            min="0"
            max="1"
            step="0.05"
            value={inputNoiseScale}
            disabled={disabled}
            onChange={(e) => onInputNoiseScaleChange?.(Number(e.target.value))}
          />
          <span className="video-enhance-panel-slider-value">{inputNoiseScale.toFixed(2)}</span>
        </div>
      </FieldBlock>
      <FieldBlock
        tipKey="batch"
        tip={t("canvas.video.enhanceBatchSizeTip")}
        openTipKey={openTipKey}
      >
        <div className={rowClass}>
          <LabelWithTip
            label={t("canvas.video.enhanceBatchSize")}
            tip={t("canvas.video.enhanceBatchSizeTip")}
            tipKey="batch"
            {...labelProps}
          />
          <select
            className={selectClass}
            value={String(batchSize)}
            disabled={disabled}
            onChange={(e) => onBatchSizeChange?.(Number(e.target.value))}
          >
            <option value="4">4</option>
            <option value="8">8</option>
            <option value="16">16</option>
          </select>
        </div>
      </FieldBlock>
      <FieldBlock
        tipKey="color"
        tip={t("canvas.video.enhanceColorCorrectionTip")}
        openTipKey={openTipKey}
      >
        <div className={rowClass}>
          <LabelWithTip
            label={t("canvas.video.enhanceColorCorrection")}
            tip={t("canvas.video.enhanceColorCorrectionTip")}
            tipKey="color"
            {...labelProps}
          />
          <select
            className={selectClass}
            value={colorCorrection}
            disabled={disabled}
            onChange={(e) => onColorCorrectionChange?.(e.target.value)}
          >
            <option value="lab">lab</option>
            <option value="none">{t("canvas.video.colorCorrectionNone")}</option>
          </select>
        </div>
      </FieldBlock>
      <FieldBlock
        tipKey="model"
        tip={t("canvas.video.enhanceModelSizeTip")}
        openTipKey={openTipKey}
      >
        <div className={rowClass}>
          <LabelWithTip
            label={t("canvas.video.enhanceModelSize")}
            tip={t("canvas.video.enhanceModelSizeTip")}
            tipKey="model"
            {...labelProps}
          />
          <select
            className={selectClass}
            value={modelSize}
            disabled={disabled}
            onChange={(e) => onModelSizeChange?.(e.target.value)}
          >
            <option value="3b">3B</option>
            <option value="7b">7B</option>
          </select>
        </div>
      </FieldBlock>
    </>
  )
}

function AdvancedTabButton({ expanded, onClick, label }) {
  return (
    <button
      type="button"
      className={`video-enhance-panel-advanced-tab nodrag nopan${expanded ? " is-expanded" : ""}`}
      onClick={onClick}
    >
      {label}
    </button>
  )
}

export default function VideoEnhancePanel({
  variant = "panel",
  videoReady = false,
  isEnhancing = false,
  isAnalyzing = false,
  hasEnhanced = false,
  manualMode = false,
  advancedOpen = false,
  reasoning = "",
  upscaleFactor = 2,
  strength = "normal",
  inputNoiseScale = 0.25,
  batchSize = 8,
  colorCorrection = "lab",
  modelSize = "7b",
  error = null,
  onManualModeChange,
  onAdvancedOpenChange,
  onUpscaleChange,
  onStrengthChange,
  onInputNoiseScaleChange,
  onBatchSizeChange,
  onColorCorrectionChange,
  onModelSizeChange,
  onOneClick,
  onCancel,
}) {
  const { t } = useLocale()
  const [localAdvancedOpen, setLocalAdvancedOpen] = useState(false)
  const isControlled = typeof onAdvancedOpenChange === "function"
  const expanded = isControlled ? advancedOpen : localAdvancedOpen
  const toggleAdvanced = () => {
    const next = !expanded
    if (isControlled) onAdvancedOpenChange(next)
    else setLocalAdvancedOpen(next)
  }

  const busy = isEnhancing || isAnalyzing
  const actionDisabled = !videoReady || busy || hasEnhanced
  const fieldsDisabled = !manualMode || busy
  const isCompact = variant === "panel"
  const advancedLabel = t("canvas.video.enhanceAdvanced")

  const primaryLabel = isAnalyzing
    ? t("canvas.video.enhanceAnalyzing")
    : isEnhancing
      ? t("canvas.video.enhancing")
      : t("canvas.video.enhanceOneClick")

  const advancedBlock = expanded ? (
    <div className="video-enhance-panel-advanced">
      {reasoning ? (
        <p className="video-enhance-panel-reasoning">{reasoning}</p>
      ) : null}
      <label className="video-enhance-panel-manual-toggle nodrag nopan">
        <input
          type="checkbox"
          checked={manualMode}
          disabled={busy}
          onChange={(e) => onManualModeChange?.(e.target.checked)}
        />
        <span>{t("canvas.video.enhanceManualMode")}</span>
      </label>
      <AdvancedFields
        t={t}
        disabled={fieldsDisabled}
        compact={isCompact}
        upscaleFactor={upscaleFactor}
        strength={strength}
        inputNoiseScale={inputNoiseScale}
        batchSize={batchSize}
        colorCorrection={colorCorrection}
        modelSize={modelSize}
        onUpscaleChange={onUpscaleChange}
        onStrengthChange={onStrengthChange}
        onInputNoiseScaleChange={onInputNoiseScaleChange}
        onBatchSizeChange={onBatchSizeChange}
        onColorCorrectionChange={onColorCorrectionChange}
        onModelSizeChange={onModelSizeChange}
      />
    </div>
  ) : null

  if (isCompact) {
    return (
      <div
        className="video-enhance-panel video-enhance-panel--panel video-enhance-panel--compact nodrag nopan"
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        {!videoReady ? (
          <span className="video-enhance-panel-hint video-enhance-panel-hint--inline">
            {t("canvas.video.enhanceNeedVideo")}
          </span>
        ) : (
          <div className="video-enhance-panel-compact-row">
            <button
              type="button"
              className="video-enhance-panel-btn video-enhance-panel-btn--primary video-enhance-panel-btn--compact-action nodrag nopan"
              disabled={actionDisabled}
              onClick={onOneClick}
            >
              {primaryLabel}
            </button>
            <AdvancedTabButton
              expanded={expanded}
              onClick={toggleAdvanced}
              label={advancedLabel}
            />
          </div>
        )}
        {advancedBlock}
        {error ? <p className="video-enhance-panel-error">{error}</p> : null}
      </div>
    )
  }

  return (
    <div
      className={`video-enhance-panel video-enhance-panel--${variant} nodrag nopan`}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {!videoReady ? (
        <p className="video-enhance-panel-hint">{t("canvas.video.enhanceNeedVideo")}</p>
      ) : (
        <>
          <button
            type="button"
            className="video-enhance-panel-btn video-enhance-panel-btn--primary nodrag nopan video-enhance-panel-btn--block"
            disabled={actionDisabled}
            onClick={onOneClick}
          >
            {primaryLabel}
          </button>
          <AdvancedTabButton
            expanded={expanded}
            onClick={toggleAdvanced}
            label={advancedLabel}
          />
          {advancedBlock}
        </>
      )}
      {error ? <p className="video-enhance-panel-error">{error}</p> : null}
      {onCancel ? (
        <div className="video-enhance-panel-actions">
          <button
            type="button"
            className="video-enhance-panel-btn video-enhance-panel-btn--ghost nodrag nopan"
            onClick={onCancel}
          >
            {t("canvas.video.enhanceCancel")}
          </button>
        </div>
      ) : null}
    </div>
  )
}
