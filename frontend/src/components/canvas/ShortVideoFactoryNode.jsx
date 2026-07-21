import { memo, useCallback, useEffect, useRef, useState } from "react"
import { Handle, Position } from "reactflow"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { submitShortVideoGenerate, fetchShortVideoTask } from "../../services/shortVideoApi"
import { useLocale } from "../../utils/locale"
import "./CanvasShared.css"
import "./GenerationCardNode.css"
import "./ShortVideoFactoryNode.css"

const POLL_MS = 2000
const MAX_POLLS = 120

function ShortVideoFactoryNode({ id, data, selected }) {
  const { t } = useLocale()
  const [topic, setTopic] = useState(data.topic || "")
  const [segmentCount, setSegmentCount] = useState(data.segmentCount ?? 3)
  const [aspect, setAspect] = useState(data.aspect || "9:16")
  const [enableTts, setEnableTts] = useState(data.enableTts !== false)
  const [voiceName, setVoiceName] = useState(data.voiceName || "zh-CN-XiaoxiaoNeural")
  const [burnCaptions, setBurnCaptions] = useState(Boolean(data.burnCaptions))
  const [bgm, setBgm] = useState(data.bgm || "none")
  const [visualSource, setVisualSource] = useState(data.visualSource || "slide")
  const [status, setStatus] = useState(data.status || "input")
  const [taskId, setTaskId] = useState(data.taskId || null)
  const [videoUrl, setVideoUrl] = useState(data.videoUrl || null)
  const [error, setError] = useState(data.error || null)
  const pollRef = useRef(null)

  const persist = useCallback(
    (patch) => {
      data.onUpdate?.(id, patch)
    },
    [data, id],
  )

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const pollTask = useCallback(
    (nextTaskId) => {
      stopPolling()
      let attempts = 0
      pollRef.current = setInterval(async () => {
        attempts += 1
        try {
          const payload = await fetchShortVideoTask(nextTaskId)
          if (payload.status === "completed" && payload.result_url) {
            const url = ensureMediaUrl(payload.result_url)
            setStatus("completed")
            setVideoUrl(url)
            setError(null)
            persist({
              status: "completed",
              taskId: nextTaskId,
              videoUrl: url,
              error: null,
            })
            stopPolling()
            return
          }
          if (payload.status === "failed") {
            const message = payload.error || t("canvas.shortVideo.failed")
            setStatus("failed")
            setError(message)
            persist({ status: "failed", taskId: nextTaskId, error: message })
            stopPolling()
            return
          }
          if (attempts >= MAX_POLLS) {
            setStatus("failed")
            setError(t("canvas.shortVideo.timeout"))
            persist({ status: "failed", taskId: nextTaskId, error: t("canvas.shortVideo.timeout") })
            stopPolling()
          }
        } catch (err) {
          if (attempts >= MAX_POLLS) {
            setStatus("failed")
            setError(err?.message || t("canvas.shortVideo.failed"))
            persist({ status: "failed", taskId: nextTaskId, error: err?.message || "" })
            stopPolling()
          }
        }
      }, POLL_MS)
    },
    [persist, stopPolling, t],
  )

  const handleGenerate = useCallback(async () => {
    const trimmed = topic.trim()
    if (!trimmed) return
    setStatus("pending")
    setError(null)
    setVideoUrl(null)
    persist({
      topic: trimmed,
      segmentCount,
      aspect,
      enableTts,
      voiceName,
      burnCaptions,
      bgm,
      visualSource,
      status: "pending",
      videoUrl: null,
      error: null,
    })
    try {
      const payload = await submitShortVideoGenerate({
        topic: trimmed,
        segment_count: segmentCount,
        aspect,
        enable_tts: enableTts,
        voice_name: voiceName,
        burn_captions: burnCaptions,
        bgm,
        visual_source: visualSource,
      })
      setTaskId(payload.task_id)
      persist({ taskId: payload.task_id, status: "pending" })
      pollTask(payload.task_id)
    } catch (err) {
      setStatus("failed")
      setError(err?.response?.data?.detail || err?.message || t("canvas.shortVideo.failed"))
      persist({ status: "failed", error: err?.message || "" })
    }
  }, [
    aspect,
    bgm,
    burnCaptions,
    enableTts,
    persist,
    pollTask,
    segmentCount,
    t,
    topic,
    visualSource,
    voiceName,
  ])

  return (
    <div className={`gn2-card svf-node${selected ? " gn2-card--selected" : ""}`}>
      <Handle type="target" position={Position.Left} id="tgt-left" className="gn2-handle" />
      <div className="gn2-header">
        <span className="gn2-title">{t("canvas.shortVideo.title")}</span>
        <button type="button" className="gn2-delete-btn" onClick={() => data.onDelete?.(id)} aria-label="delete">
          ×
        </button>
      </div>
      <div className="svf-body">
        <label className="svf-field">
          <span>{t("canvas.shortVideo.topic")}</span>
          <textarea
            className="svf-textarea nodrag"
            rows={2}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder={t("canvas.shortVideo.topicPlaceholder")}
          />
        </label>
        <div className="svf-row">
          <label className="svf-field svf-field--compact">
            <span>{t("canvas.shortVideo.segments")}</span>
            <input
              className="svf-input nodrag"
              type="number"
              min={1}
              max={12}
              value={segmentCount}
              onChange={(e) => setSegmentCount(Number(e.target.value) || 3)}
            />
          </label>
          <label className="svf-field svf-field--compact">
            <span>{t("canvas.shortVideo.aspect")}</span>
            <select className="svf-input nodrag" value={aspect} onChange={(e) => setAspect(e.target.value)}>
              <option value="9:16">9:16</option>
              <option value="16:9">16:9</option>
              <option value="1:1">1:1</option>
            </select>
          </label>
        </div>
        <div className="svf-row">
          <label className="svf-check nodrag">
            <input type="checkbox" checked={enableTts} onChange={(e) => setEnableTts(e.target.checked)} />
            <span>{t("canvas.shortVideo.enableTts")}</span>
          </label>
          <label className="svf-check nodrag">
            <input type="checkbox" checked={burnCaptions} onChange={(e) => setBurnCaptions(e.target.checked)} />
            <span>{t("canvas.shortVideo.burnCaptions")}</span>
          </label>
        </div>
        <label className="svf-field">
          <span>{t("canvas.shortVideo.visualSource")}</span>
          <select className="svf-input nodrag" value={visualSource} onChange={(e) => setVisualSource(e.target.value)}>
            <option value="slide">{t("canvas.shortVideo.visualSlide")}</option>
            <option value="stock">{t("canvas.shortVideo.visualStock")}</option>
          </select>
        </label>
        <label className="svf-field">
          <span>{t("canvas.shortVideo.voice")}</span>
          <input
            className="svf-input nodrag"
            value={voiceName}
            onChange={(e) => setVoiceName(e.target.value)}
            disabled={!enableTts}
          />
        </label>
        <button
          type="button"
          className="svf-generate-btn nodrag"
          onClick={handleGenerate}
          disabled={status === "pending" || !topic.trim()}
        >
          {status === "pending" ? t("canvas.shortVideo.generating") : t("canvas.shortVideo.generate")}
        </button>
        {error && <div className="svf-error">{error}</div>}
        <div className="gn2-preview svf-preview">
          {videoUrl ? (
            <video className="gn2-result-video" src={videoUrl} controls playsInline loop muted />
          ) : (
            <div className="svf-placeholder">{t("canvas.shortVideo.previewPlaceholder")}</div>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="src-right" className="gn2-handle" />
    </div>
  )
}

export default memo(ShortVideoFactoryNode)
