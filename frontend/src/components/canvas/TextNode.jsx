import { useState, useRef, useCallback, useEffect } from "react"
import { useCanvasStore } from "../../stores"
import { TEXT_MODES } from "../../utils/canvas/nodeHelpers"
import { classifyPromptIntent } from "../../services/promptIntentApi"
import { isScreenplayLike, PASTE_HINT_MIN } from "../../utils/canvas/promptIntentConfig"
import { useLocale } from "../../utils/locale"
import { useCanvasNodeWheel } from "./canvasScrollHelpers"
import TextWorkflowEdgePlugs from "./TextWorkflowEdgePlugs"
import "./canvasNodeLayout.css"
import "./TextNode.css"

const MenuIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <rect x="1" y="2.5" width="11" height="1.2" rx="0.6" fill="currentColor"/>
    <rect x="1" y="5.9" width="11" height="1.2" rx="0.6" fill="currentColor"/>
    <rect x="1" y="9.3" width="11" height="1.2" rx="0.6" fill="currentColor"/>
  </svg>
)

const CLASSIFY_DEBOUNCE_MS = 700

function readPrompt(data) {
  return data.prompt ?? data.content ?? ""
}

function readTextMode(data) {
  return data.textMode === TEXT_MODES.SCREENPLAY ? TEXT_MODES.SCREENPLAY : TEXT_MODES.CHAT
}

export default function TextNode({ id, data, selected }) {
  const { t } = useLocale()
  const syncPromptBar = useCanvasStore((s) => s.syncPromptBar)
  const [editing, setEditing] = useState(false)
  const [labelEditing, setLabelEditing] = useState(false)
  const [label, setLabel] = useState(data.label || "Text")
  const [textMode, setTextMode] = useState(() => readTextMode(data))
  const [screenplayHint, setScreenplayHint] = useState(null)
  const textareaRef = useRef(null)
  const wrapperRef = useRef(null)
  useCanvasNodeWheel(wrapperRef)
  const labelRef = useRef(null)
  const classifyTimerRef = useRef(null)
  const lastClassifiedRef = useRef("")

  const prompt = readPrompt(data)

  useEffect(() => {
    setTextMode(readTextMode(data))
  }, [data.textMode])

  useEffect(() => {
    if (editing) textareaRef.current?.focus()
  }, [editing])

  useEffect(() => {
    if (labelEditing) {
      labelRef.current?.focus()
      labelRef.current?.select()
    }
  }, [labelEditing])

  useEffect(() => {
    if (textMode === TEXT_MODES.SCREENPLAY) {
      setScreenplayHint(null)
    }
  }, [textMode])

  const updateData = useCallback((patch) => {
    if (data.onUpdate) data.onUpdate(id, patch)
  }, [id, data])

  const scheduleScreenplayHintCheck = useCallback(
    (text, { force = false } = {}) => {
      const trimmed = (text || "").trim()
      clearTimeout(classifyTimerRef.current)
      if (textMode === TEXT_MODES.SCREENPLAY) {
        setScreenplayHint(null)
        return
      }
      if (!force && trimmed.length < PASTE_HINT_MIN) {
        setScreenplayHint(null)
        return
      }
      if (trimmed === lastClassifiedRef.current && !force) return

      classifyTimerRef.current = setTimeout(async () => {
        lastClassifiedRef.current = trimmed
        try {
          const result = await classifyPromptIntent(trimmed, {
            context: "text",
            currentTextMode: textMode,
          })
          if (isScreenplayLike(result)) {
            setScreenplayHint({
              summary: result.summary || t("canvas.text.scriptSummaryDefault"),
            })
          } else {
            setScreenplayHint(null)
          }
        } catch {
          setScreenplayHint(null)
        }
      }, CLASSIFY_DEBOUNCE_MS)
    },
    [textMode, t]
  )

  useEffect(() => {
    scheduleScreenplayHintCheck(prompt)
    return () => clearTimeout(classifyTimerRef.current)
  }, [prompt, scheduleScreenplayHintCheck])

  const handleDoubleClick = useCallback((e) => {
    e.stopPropagation()
    setEditing(true)
  }, [])

  const handleBlur = useCallback(() => {
    setEditing(false)
  }, [])

  const handleChange = useCallback((e) => {
    const value = e.target.value
    updateData({ prompt: value, content: value })
    syncPromptBar(id, value)
  }, [updateData, syncPromptBar, id])

  const handlePaste = useCallback(
    (e) => {
      const pasted = e.clipboardData?.getData("text") || ""
      if (pasted.trim().length >= 80) {
        const next = `${prompt}${pasted}`
        scheduleScreenplayHintCheck(next, { force: true })
      }
    },
    [prompt, scheduleScreenplayHintCheck]
  )

  const handleLabelBlur = useCallback(() => {
    setLabelEditing(false)
    updateData({ label })
  }, [label, updateData])

  const handleLabelChange = useCallback((e) => {
    setLabel(e.target.value)
  }, [])

  const setMode = useCallback(
    (mode) => {
      setTextMode(mode)
      updateData({ textMode: mode })
      if (mode === TEXT_MODES.SCREENPLAY) setScreenplayHint(null)
    },
    [updateData]
  )

  const sp = (e) => e.stopPropagation()
  const isScreenplay = textMode === TEXT_MODES.SCREENPLAY

  return (
    <div className={`tn-wrapper${selected ? " tn-wrapper--selected" : ""}`} ref={wrapperRef}>
      <TextWorkflowEdgePlugs nodeId={id} nodeType="text-note" selected={selected} />
      <div className="tn-label-row">
        <MenuIcon />
        {labelEditing ? (
          <input
            ref={labelRef}
            className="tn-label-input nodrag"
            value={label}
            onChange={handleLabelChange}
            onBlur={handleLabelBlur}
            onPointerDown={sp}
            onClick={sp}
            onKeyDown={(e) => { sp(e); if (e.key === "Enter") labelRef.current?.blur() }}
          />
        ) : (
          <span
            className="tn-label-text"
            onDoubleClick={(e) => { sp(e); setLabelEditing(true) }}
          >
            {label}
          </span>
        )}
      </div>

      <div
        className={`tn-root${editing ? " tn-root--editing" : ""}`}
        onDoubleClick={handleDoubleClick}
      >
        <div className="tn-mode-row nodrag" onPointerDown={sp} onClick={sp}>
          <button
            type="button"
            className={`tn-mode-btn${!isScreenplay ? " tn-mode-btn--active" : ""}`}
            onClick={() => setMode(TEXT_MODES.CHAT)}
          >
            {t("canvas.text.chat")}
          </button>
          <button
            type="button"
            className={`tn-mode-btn${isScreenplay ? " tn-mode-btn--active" : ""}`}
            onClick={() => setMode(TEXT_MODES.SCREENPLAY)}
          >
            {t("canvas.text.script")}
          </button>
        </div>

        {screenplayHint && !isScreenplay && (
          <div className="tn-screenplay-banner nodrag" onPointerDown={sp}>
            <p className="tn-screenplay-banner-text">
              {t("canvas.text.scriptBanner", { summary: screenplayHint.summary })}
            </p>
            <button
              type="button"
              className="tn-screenplay-banner-btn"
              onClick={() => setMode(TEXT_MODES.SCREENPLAY)}
            >
              {t("canvas.text.switchScript")}
            </button>
            <button
              type="button"
              className="tn-screenplay-banner-dismiss"
              onClick={() => setScreenplayHint(null)}
              aria-label={t("canvas.common.closeTip")}
            >
              ×
            </button>
          </div>
        )}

        <div className="cn-content-slot tn-content-slot">
          {editing ? (
            <textarea
              ref={textareaRef}
              className="tn-textarea cn-edit-match nodrag nowheel"
              value={prompt}
              onChange={handleChange}
              onPaste={handlePaste}
              onBlur={handleBlur}
              onPointerDown={sp}
              onClick={sp}
              placeholder={isScreenplay ? t("canvas.text.scriptIdeaPh") : t("canvas.text.chatPh")}
            />
          ) : (
            <div className="tn-display cn-edit-match">
              {prompt || (
                <span className="tn-placeholder">
                  {isScreenplay ? t("canvas.text.scriptDblClickPh") : t("canvas.text.dblClickEdit")}
                </span>
              )}
            </div>
          )}
        </div>

        {isScreenplay && (
          <p className="tn-mode-hint">{t("canvas.text.scriptHint")}</p>
        )}
      </div>
    </div>
  )
}
