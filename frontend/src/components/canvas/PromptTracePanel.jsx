import { useCallback, useEffect, useRef, useState } from "react"
import { API_BASE } from "../../services/api"
import { useLocale } from "../../utils/locale"
import "./PromptTracePanel.css"

const LAYER_META = {
  0: { key: "l0", titleKey: "canvas.trace.l0", className: "prompt-trace-layer--l0" },
  1: { key: "l1", titleKey: "canvas.trace.l1", className: "prompt-trace-layer--l1" },
  2: { key: "l2", titleKey: "canvas.trace.l2", className: "prompt-trace-layer--l2" },
  3: { key: "l3", titleKey: "canvas.trace.l3", className: "prompt-trace-layer--l3" },
  4: { key: "l4", titleKey: "canvas.trace.l4", className: "prompt-trace-layer--l4" },
}

const EMPTY_LAYERS = { 0: null, 1: null, 2: null, 3: null, 4: null }

function formatTime(ts) {
  if (!ts) return ""
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString("zh-CN", { hour12: false })
}

/** 与后端 strip_mention_tokens 对齐：比较前去掉 @ 提及 */
const MENTION_STRIP_RE = /\s*@\S+/g

function stripMentionsForCompare(text) {
  if (text == null) return ""
  return String(text)
    .replace(MENTION_STRIP_RE, "")
    .replace(/\s+/g, " ")
    .trim()
}

function promptsMatch(a, b) {
  if (a == null || b == null) return null
  return stripMentionsForCompare(a) === stripMentionsForCompare(b)
}

function hasTranslation(layer3) {
  if (!layer3?.data) return false
  const { before, after, optimized } = layer3.data
  if (optimized === true) return true
  return before != null && after != null && String(before).trim() !== String(after).trim()
}

function createSessionFromLayers(layers, ts) {
  return {
    id: `${ts || Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    ts: ts || Date.now() / 1000,
    layers: { ...EMPTY_LAYERS, ...layers },
  }
}

function resolveTaskType(layers) {
  return (
    layers[1]?.data?.task_type
    || layers[0]?.data?.task_type
    || layers[4]?.data?.task_type
    || "image"
  )
}

function isSessionComplete(layers) {
  const taskType = resolveTaskType(layers)
  if (taskType === "video_lut") return Boolean(layers[1] && layers[4])
  if (taskType === "video_enhance") return Boolean(layers[1] && layers[4])
  return Boolean(layers[1] && layers[2] && layers[3] && layers[4])
}

function TraceKv({ label, value }) {
  if (value == null || value === "") return null
  return (
    <div className="prompt-trace-kv">
      <span className="k">{label}</span>
      <span className="v">{value}</span>
    </div>
  )
}

function Layer4Body({ d }) {
  const taskType = d.task_type || "image"
  if (taskType === "video_lut") {
    return (
      <>
        <TraceKv label="task_type" value={taskType} />
        <TraceKv label="workflow_mode" value={d.workflow_mode} />
        <TraceKv label="lut_preset" value={d.lut_preset} />
        <TraceKv label="cube_path" value={d.cube_path} />
        <TraceKv label="source_url" value={d.source_url} />
        <TraceKv label="ffmpeg_filter" value={d.ffmpeg_filter} />
      </>
    )
  }
  if (taskType === "video_enhance") {
    return (
      <>
        <TraceKv label="task_type" value={taskType} />
        <TraceKv label="workflow_mode" value={d.workflow_mode} />
        <TraceKv label="provider" value={d.provider || d.model_file} />
        <TraceKv label="upscale_factor" value={d.upscale_factor} />
        <TraceKv label="strength" value={d.strength} />
        <TraceKv label="batch_size" value={d.batch_size} />
        <TraceKv label="color_correction" value={d.color_correction} />
        <TraceKv label="model_size" value={d.model_size} />
      </>
    )
  }
  if (taskType === "video") {
    return (
      <>
        <TraceKv label="task_type" value={taskType} />
        <TraceKv label="positive" value={d.positive_prompt} />
        <TraceKv label="workflow_mode" value={d.workflow_mode} />
        <TraceKv label="duration" value={d.duration} />
        <TraceKv label="size" value={d.width != null && d.height != null ? `${d.width}×${d.height}` : null} />
        <TraceKv label="model_file" value={d.model_file} />
      </>
    )
  }
  return (
    <>
      <TraceKv label="task_type" value={taskType} />
      <TraceKv label="positive" value={d.positive_prompt} />
      <TraceKv label="workflow_mode" value={d.workflow_mode} />
      <TraceKv label="reference_count" value={d.reference_count} />
      <TraceKv label="steps" value={d.steps} />
      <TraceKv label="cfg" value={d.cfg} />
      <TraceKv label="denoise" value={d.denoise} />
      <TraceKv label="size" value={d.width != null && d.height != null ? `${d.width}×${d.height}` : null} />
      <TraceKv label="batch" value={d.batch_size} />
      <TraceKv label="model_file" value={d.model_file} />
      {d.reference_filename && <TraceKv label="ref_file" value={d.reference_filename} />}
      {d.ksampler_latent && (
        <TraceKv label="ksampler_latent" value={JSON.stringify(d.ksampler_latent)} />
      )}
    </>
  )
}

function LayerBlock({ layerNum, entry, comparePrompt }) {
  const { t } = useLocale()
  const meta = LAYER_META[layerNum]
  const layerTitle = t(meta.titleKey)
  const [collapsed, setCollapsed] = useState(false)

  if (!entry) {
    return (
      <div className={`prompt-trace-layer ${meta.className}`}>
        <div className="prompt-trace-layer-head">
          <span className="prompt-trace-layer-title">{layerTitle}</span>
        </div>
        <div className="prompt-trace-layer-body prompt-trace-empty">{t("canvas.trace.waiting")}</div>
      </div>
    )
  }

  const d = entry.data || {}

  return (
    <div className={`prompt-trace-layer ${meta.className}`}>
      <div
        className="prompt-trace-layer-head"
        onClick={() => setCollapsed((c) => !c)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && setCollapsed((c) => !c)}
      >
        <span className="prompt-trace-layer-title">{layerTitle}</span>
        <span className="prompt-trace-layer-tag">{entry.tag}</span>
      </div>
      {!collapsed && (
        <div className="prompt-trace-layer-body">
          {layerNum === 0 && (
            <>
              <TraceKv label="quality_preset_id" value={d.quality_preset_id} />
              <TraceKv label="shot_number" value={d.shot_number} />
              <TraceKv label="display_prompt" value={d.display_prompt} />
              <TraceKv label="positive" value={d.positive} />
              <TraceKv label="negative" value={d.negative} />
            </>
          )}
          {layerNum === 1 && (
            <>
              <TraceKv label="task_type" value={d.task_type} />
              <TraceKv label="model" value={d.model} />
              {d.display_prompt ? (
                <TraceKv label={t("canvas.trace.displayDesc")} value={d.display_prompt} />
              ) : null}
              <TraceKv label={t("canvas.trace.genPrompt")} value={d.prompt} />
              <TraceKv label="quality_preset_id" value={d.quality_preset_id} />
              {d.video_url && <TraceKv label="video_url" value={d.video_url} />}
              {d.lut_preset && <TraceKv label="lut_preset" value={d.lut_preset} />}
              {d.upscale_factor != null && <TraceKv label="upscale_factor" value={d.upscale_factor} />}
              {d.denoise != null && <TraceKv label="denoise" value={d.denoise} />}
              <TraceKv label="ratio" value={d.ratio} />
              <TraceKv label="resolution" value={d.resolution} />
              <TraceKv label="count" value={d.count} />
            </>
          )}
          {layerNum === 2 && (
            <>
              <div className="prompt-trace-kv"><span className="k">model</span><span className="v">{d.model ?? "—"}</span></div>
              <div className="prompt-trace-kv">
                <span className="k">prompt</span>
                <span className="v">{d.prompt ?? "—"}</span>
                {comparePrompt != null && (
                  <span className={promptsMatch(comparePrompt, d.prompt) ? " prompt-trace-match-ok" : " prompt-trace-match-bad"}>
                    {promptsMatch(comparePrompt, d.prompt)
                      ? t("canvas.trace.matchL1")
                      : t("canvas.trace.mismatchL1")}
                  </span>
                )}
              </div>
              <div className="prompt-trace-kv"><span className="k">ratio</span><span className="v">{d.ratio ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">count</span><span className="v">{d.count ?? "—"}</span></div>
            </>
          )}
          {layerNum === 3 && (
            hasTranslation(entry) ? (
              <>
                <div className="prompt-trace-kv"><span className="k">before</span><span className="v">{d.before}</span></div>
                <div className="prompt-trace-kv"><span className="k">after</span><span className="v">{d.after}</span></div>
                {d.negative_before && (
                  <TraceKv label="negative_before" value={d.negative_before} />
                )}
                {d.negative_after && (
                  <TraceKv label="negative_after" value={d.negative_after} />
                )}
                {d.optimized === true && (
                  <div className="prompt-trace-kv"><span className="k">status</span><span className="v">{t("canvas.trace.optimized")}</span></div>
                )}
              </>
            ) : (
              <>
                <div className="prompt-trace-kv"><span className="v">{t("canvas.trace.noTranslate")}</span></div>
                {d.optimize_note && (
                  <div className="prompt-trace-kv"><span className="k">note</span><span className="v">{d.optimize_note}</span></div>
                )}
                {d.before && (
                  <div className="prompt-trace-kv"><span className="k">prompt</span><span className="v">{d.before}</span></div>
                )}
              </>
            )
          )}
          {layerNum === 4 && <Layer4Body d={d} />}
        </div>
      )}
    </div>
  )
}

export default function PromptTracePanel() {
  const { t } = useLocale()
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState("latest")
  const [latest, setLatest] = useState({ ...EMPTY_LAYERS })
  const [history, setHistory] = useState([])
  const [sseError, setSseError] = useState(null)
  const [pos, setPos] = useState({ x: null, y: null })
  const dragRef = useRef(null)
  const panelRef = useRef(null)
  const sessionsRef = useRef(new Map())
  const [activeTraceId, setActiveTraceId] = useState(null)

  const applyTraceMessage = useCallback((msg) => {
    const layer = msg.layer
    const entry = { tag: msg.tag, ts: msg.ts, data: msg.data }
    const traceId = msg.data?.trace_id || `legacy-${msg.ts}-${layer}`

    if (layer === 0) {
      const prevSession = sessionsRef.current.get(traceId) || { ...EMPTY_LAYERS }
      const nextSession = { ...prevSession, 0: entry }
      sessionsRef.current.set(traceId, nextSession)
      setActiveTraceId(traceId)
      setLatest(nextSession)
      setHistory((prev) => {
        const idx = prev.findIndex((s) => s.id === traceId)
        if (idx === -1) {
          const item = createSessionFromLayers({ 0: entry }, msg.ts)
          item.id = traceId
          return [item, ...prev].slice(0, 50)
        }
        const updated = {
          ...prev[idx],
          layers: { ...prev[idx].layers, 0: entry },
          ts: prev[idx].ts || msg.ts,
        }
        const rest = prev.filter((_, i) => i !== idx)
        return [updated, ...rest]
      })
      return
    }

    if (layer === 1) {
      const prevSession = sessionsRef.current.get(traceId) || { ...EMPTY_LAYERS }
      const nextSession = { ...prevSession, 1: entry }
      sessionsRef.current.set(traceId, nextSession)
      setActiveTraceId(traceId)
      setLatest(nextSession)
      setHistory((prev) => {
        const idx = prev.findIndex((s) => s.id === traceId)
        if (idx === -1) {
          const item = createSessionFromLayers({ ...prevSession, 1: entry }, msg.ts)
          item.id = traceId
          return [item, ...prev].slice(0, 50)
        }
        const updated = {
          ...prev[idx],
          layers: { ...prev[idx].layers, 1: entry },
          ts: prev[idx].ts || msg.ts,
        }
        const rest = prev.filter((_, i) => i !== idx)
        return [updated, ...rest]
      })
      return
    }

    const prevSession = sessionsRef.current.get(traceId) || { ...EMPTY_LAYERS }
    const nextSession = { ...prevSession, [layer]: entry }
    sessionsRef.current.set(traceId, nextSession)

    setHistory((prev) => {
      if (!prev.length) {
        const item = createSessionFromLayers({ [layer]: entry }, msg.ts)
        item.id = traceId
        return [item]
      }
      const idx = prev.findIndex((s) => s.id === traceId)
      if (idx === -1) {
        const item = createSessionFromLayers(nextSession, msg.ts)
        item.id = traceId
        return [item, ...prev].slice(0, 50)
      }
      const updated = {
        ...prev[idx],
        layers: { ...prev[idx].layers, [layer]: entry },
        ts: prev[idx].ts || msg.ts,
      }
      const rest = prev.filter((_, i) => i !== idx)
      return [updated, ...rest]
    })

    setActiveTraceId((current) => {
      const showId = current || traceId
      if (traceId === showId || !current) {
        setLatest(nextSession)
        return traceId
      }
      return current
    })
  }, [])

  useEffect(() => {
    const url = `${API_BASE}/api/debug/trace/stream`
    const es = new EventSource(url)
    setSseError(null)

    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        setSseError(null)
        applyTraceMessage(msg)
      } catch {
        /* ignore malformed */
      }
    }

    es.onerror = () => {
      setSseError("error")
      /* EventSource auto-reconnects */
    }

    return () => es.close()
  }, [applyTraceMessage])

  const handleClear = () => {
    setLatest({ ...EMPTY_LAYERS })
    setHistory([])
    sessionsRef.current = new Map()
    setActiveTraceId(null)
  }

  const onDragStart = (e) => {
    if (e.target.closest("button")) return
    const panel = panelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      originX: pos.x ?? rect.left,
      originY: pos.y ?? rect.top,
    }
    e.preventDefault()
  }

  useEffect(() => {
    const onMove = (e) => {
      if (!dragRef.current) return
      const { startX, startY, originX, originY } = dragRef.current
      setPos({
        x: originX + (e.clientX - startX),
        y: originY + (e.clientY - startY),
      })
    }
    const onUp = () => {
      dragRef.current = null
    }
    window.addEventListener("mousemove", onMove)
    window.addEventListener("mouseup", onUp)
    return () => {
      window.removeEventListener("mousemove", onMove)
      window.removeEventListener("mouseup", onUp)
    }
  }, [])

  const panelStyle = {
    ...(pos.x != null && pos.y != null
      ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" }
      : { left: 16, top: "calc(50vh + 210px)", right: "auto", bottom: "auto" }),
  }

  const fabStyle = {
    ...(pos.x != null && pos.y != null
      ? { left: pos.x + 280, top: pos.y + 440, right: "auto", bottom: "auto" }
      : { left: 18, top: "calc(50vh + 168px)", right: "auto", bottom: "auto" }),
  }

  const l1Prompt = latest[1]?.data?.prompt

  if (!open) {
    return (
      <button
        type="button"
        className="prompt-trace-fab"
        style={fabStyle}
        title={t("canvas.trace.title")}
        onClick={() => setOpen(true)}
      >
        PT
      </button>
    )
  }

  return (
    <div ref={panelRef} className="prompt-trace-panel" style={panelStyle}>
      <div className="prompt-trace-header" onMouseDown={onDragStart}>
        <span className="prompt-trace-title">{t("canvas.trace.title")}</span>
        <div className="prompt-trace-actions">
          <button type="button" onClick={handleClear}>{t("canvas.trace.clear")}</button>
          <button type="button" onClick={() => setOpen(false)}>{t("canvas.common.close")}</button>
        </div>
      </div>
      <div className="prompt-trace-tabs">
        <button
          type="button"
          className={tab === "latest" ? "active" : ""}
          onClick={() => setTab("latest")}
        >
          {t("canvas.trace.latest")}
        </button>
        <button
          type="button"
          className={tab === "history" ? "active" : ""}
          onClick={() => setTab("history")}
        >
          {t("canvas.trace.history")}
        </button>
      </div>
      <div className="prompt-trace-body">
        {tab === "latest" && (
          <>
            {!latest[0] && !latest[1] && !latest[2] && !latest[3] && !latest[4] ? (
              <div className="prompt-trace-empty">
                {t("canvas.trace.waitTask")}
                <br />
                {sseError ? (
                  <span className="prompt-trace-error">{t("canvas.trace.sseError")}</span>
                ) : (
                  t("canvas.trace.connecting")
                )}
              </div>
            ) : (
              [0, 1, 2, 3, 4].map((n) => (
                <LayerBlock
                  key={n}
                  layerNum={n}
                  entry={latest[n]}
                  comparePrompt={n === 2 ? l1Prompt : undefined}
                />
              ))
            )}
          </>
        )}
        {tab === "history" && (
          history.length === 0 ? (
            <div className="prompt-trace-empty">{t("canvas.trace.noHistory")}</div>
          ) : (
            history.map((session) => (
              <HistorySession key={session.id} session={session} />
            ))
          )
        )}
      </div>
    </div>
  )
}

function HistorySession({ session }) {
  const { t } = useLocale()
  const [open, setOpen] = useState(false)
  const layers = session.layers || {}
  const l1 = layers[1]?.data
  const label = l1?.prompt
    ? `${String(l1.prompt).slice(0, 36)}${String(l1.prompt).length > 36 ? "…" : ""}`
    : formatTime(session.ts) || t("canvas.trace.unnamedTask")
  const complete = isSessionComplete(layers)

  return (
    <div className="prompt-trace-history-item">
      <div
        className="prompt-trace-history-head"
        onClick={() => setOpen((o) => !o)}
        role="button"
        tabIndex={0}
      >
        <span className={`prompt-trace-status-dot${complete ? "" : " pending"}`} />
        <span className="prompt-trace-history-meta">{formatTime(session.ts)} · {label}</span>
      </div>
      {open && (
        <div className="prompt-trace-history-detail">
          {[0, 1, 2, 3, 4].map((n) => (
            <LayerBlock
              key={n}
              layerNum={n}
              entry={layers[n]}
              comparePrompt={n === 2 ? layers[1]?.data?.prompt : undefined}
            />
          ))}
        </div>
      )}
    </div>
  )
}
