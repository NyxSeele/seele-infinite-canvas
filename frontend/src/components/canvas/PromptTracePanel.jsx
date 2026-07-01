import { useCallback, useEffect, useRef, useState } from "react"
import { API_BASE } from "../../services/api"
import { useLocale } from "../../utils/locale"
import "./PromptTracePanel.css"

const LAYER_META = {
  1: { key: "l1", titleKey: "canvas.trace.l1", className: "prompt-trace-layer--l1" },
  2: { key: "l2", titleKey: "canvas.trace.l2", className: "prompt-trace-layer--l2" },
  3: { key: "l3", titleKey: "canvas.trace.l3", className: "prompt-trace-layer--l3" },
  4: { key: "l4", title: "L4 Workflow", className: "prompt-trace-layer--l4" },
}

const EMPTY_LAYERS = { 1: null, 2: null, 3: null, 4: null }

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
    layers: { ...layers },
  }
}

function LayerBlock({ layerNum, entry, comparePrompt }) {
  const { t } = useLocale()
  const meta = LAYER_META[layerNum]
  const layerTitle = meta.titleKey ? t(meta.titleKey) : meta.title
  const [collapsed, setCollapsed] = useState(false)

  if (!entry) {
    return (
      <div className={`prompt-trace-layer ${meta.className}`}>
        <div className="prompt-trace-layer-head">
          <span className="prompt-trace-chevron">▸</span>
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
        <span className="prompt-trace-chevron">{collapsed ? "▸" : "▾"}</span>
        <span className="prompt-trace-layer-title">{layerTitle}</span>
        <span className="prompt-trace-layer-tag">{entry.tag}</span>
      </div>
      {!collapsed && (
        <div className="prompt-trace-layer-body">
          {layerNum === 1 && (
            <>
              <div className="prompt-trace-kv"><span className="k">model</span><span className="v">{d.model ?? "—"}</span></div>
              {d.display_prompt ? (
                <div className="prompt-trace-kv">
                  <span className="k">{t("canvas.trace.displayDesc")}</span>
                  <span className="v">{d.display_prompt}</span>
                </div>
              ) : null}
              <div className="prompt-trace-kv">
                <span className="k">{t("canvas.trace.genPrompt")}</span>
                <span className="v">{d.prompt ?? "—"}</span>
              </div>
              {d.denoise != null && (
                <div className="prompt-trace-kv"><span className="k">denoise</span><span className="v">{d.denoise}</span></div>
              )}
              <div className="prompt-trace-kv"><span className="k">ratio</span><span className="v">{d.ratio ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">resolution</span><span className="v">{d.resolution ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">count</span><span className="v">{d.count ?? "—"}</span></div>
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
          {layerNum === 4 && (
            <>
              <div className="prompt-trace-kv"><span className="k">positive</span><span className="v">{d.positive_prompt ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">workflow_mode</span><span className="v">{d.workflow_mode ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">reference_count</span><span className="v">{d.reference_count ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">steps</span><span className="v">{d.steps ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">cfg</span><span className="v">{d.cfg ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">denoise</span><span className="v">{d.denoise ?? "—"}</span></div>
              <div className="prompt-trace-kv">
                <span className="k">size</span>
                <span className="v">{d.width != null && d.height != null ? `${d.width}×${d.height}` : "—"}</span>
              </div>
              <div className="prompt-trace-kv"><span className="k">batch</span><span className="v">{d.batch_size ?? "—"}</span></div>
              <div className="prompt-trace-kv"><span className="k">model_file</span><span className="v">{d.model_file ?? "—"}</span></div>
              {d.reference_filename && (
                <div className="prompt-trace-kv"><span className="k">ref_file</span><span className="v">{d.reference_filename}</span></div>
              )}
              {d.ksampler_latent && (
                <div className="prompt-trace-kv"><span className="k">ksampler_latent</span><span className="v">{JSON.stringify(d.ksampler_latent)}</span></div>
              )}
            </>
          )}
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
  const [pos, setPos] = useState({ x: null, y: null })
  const dragRef = useRef(null)
  const panelRef = useRef(null)
  const sessionsRef = useRef(new Map())
  const [activeTraceId, setActiveTraceId] = useState(null)

  const applyTraceMessage = useCallback((msg) => {
    const layer = msg.layer
    const entry = { tag: msg.tag, ts: msg.ts, data: msg.data }
    const traceId = msg.data?.trace_id || `legacy-${msg.ts}-${layer}`

    if (layer === 1) {
      const session = { ...EMPTY_LAYERS, 1: entry }
      sessionsRef.current.set(traceId, session)
      setActiveTraceId(traceId)
      setLatest(session)
      setHistory((prev) => {
        const item = createSessionFromLayers({ 1: entry }, msg.ts)
        item.id = traceId
        return [item, ...prev.filter((s) => s.id !== traceId)].slice(0, 50)
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

    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        applyTraceMessage(msg)
      } catch {
        /* ignore malformed */
      }
    }

    es.onerror = () => {
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
        title="Prompt Trace"
        onClick={() => setOpen(true)}
      >
        PT
      </button>
    )
  }

  return (
    <div ref={panelRef} className="prompt-trace-panel" style={panelStyle}>
      <div className="prompt-trace-header" onMouseDown={onDragStart}>
        <span className="prompt-trace-title">Prompt Trace</span>
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
            {!latest[1] && !latest[2] && !latest[3] && !latest[4] ? (
              <div className="prompt-trace-empty">
                {t("canvas.trace.waitTask")}
                <br />
                {t("canvas.trace.connecting")}
              </div>
            ) : (
              [1, 2, 3, 4].map((n) => (
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
  const complete = layers[1] && layers[2] && layers[3] && layers[4]

  return (
    <div className="prompt-trace-history-item">
      <div
        className="prompt-trace-history-head"
        onClick={() => setOpen((o) => !o)}
        role="button"
        tabIndex={0}
      >
        <span className="prompt-trace-chevron">{open ? "▾" : "▸"}</span>
        <span className={`prompt-trace-status-dot${complete ? "" : " pending"}`} />
        <span className="prompt-trace-history-meta">{formatTime(session.ts)} · {label}</span>
      </div>
      {open && (
        <div className="prompt-trace-history-detail">
          {[1, 2, 3, 4].map((n) => (
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
