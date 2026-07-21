import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useCanvasStore } from "../stores"
import {
  compareNetworkResults,
  formatMbps,
  formatMs,
  formatSeconds,
  loadNetworkTestHistory,
  runFullNetworkTest,
  saveNetworkTestHistory,
} from "../services/networkSpeedTest"
import "./NetworkTest.css"

const DEFAULT_CF_URL = "https://velora.seele0420.cloud"
const DEFAULT_AD_URL = "https://u1066791-81ad-fb224913.bjb2.seetacloud.com:8443"

function ResultMetrics({ result }) {
  if (!result) {
    return <p className="nt-empty">尚未测试</p>
  }

  if (result.error) {
    return <p className="nt-error">{result.error}</p>
  }

  return (
    <div className="nt-metrics">
      <div className="nt-metric">
        <div className="nt-metric-title">Ping（/api/health ×10）</div>
        <div className="nt-metric-value">
          avg {formatMs(result.ping?.avg)} · p95 {formatMs(result.ping?.p95)}
        </div>
        <div className="nt-metric-sub">
          min {formatMs(result.ping?.min)} · max {formatMs(result.ping?.max)}
        </div>
      </div>
      <div className="nt-metric">
        <div className="nt-metric-title">TTFB</div>
        <div className="nt-metric-value">{formatMs(result.ttfbMs)}</div>
      </div>
      <div className="nt-metric">
        <div className="nt-metric-title">下载（100MB）</div>
        <div className="nt-metric-value">{formatMbps(result.download?.mbps)}</div>
        <div className="nt-metric-sub">耗时 {formatSeconds(result.download?.seconds)}</div>
      </div>
      <div className="nt-metric">
        <div className="nt-metric-title">上传（100MB）</div>
        <div className="nt-metric-value">{formatMbps(result.upload?.mbps)}</div>
        <div className="nt-metric-sub">耗时 {formatSeconds(result.upload?.seconds)}</div>
      </div>
    </div>
  )
}

function HistoryItem({ entry }) {
  const [open, setOpen] = useState(false)
  const timeLabel = useMemo(() => {
    try {
      return new Date(entry.timestamp).toLocaleString("zh-CN")
    } catch {
      return entry.timestamp
    }
  }, [entry.timestamp])

  const cfSummary = entry.cloudflare?.error
    ? "失败"
    : entry.cloudflare
      ? `↓${entry.cloudflare.download?.mbps?.toFixed(1) ?? "—"} ↑${entry.cloudflare.upload?.mbps?.toFixed(1) ?? "—"} MB/s`
      : "—"
  const adSummary = entry.autodl?.error
    ? "失败"
    : entry.autodl
      ? `↓${entry.autodl.download?.mbps?.toFixed(1) ?? "—"} ↑${entry.autodl.upload?.mbps?.toFixed(1) ?? "—"} MB/s`
      : "—"

  const renderSide = (label, data) => (
    <div className="nt-history-col">
      <h4>{label}</h4>
      {!data ? (
        <p className="nt-empty">无数据</p>
      ) : data.error ? (
        <p className="nt-error">{data.error}</p>
      ) : (
        <ul>
          <li>Base URL: {data.baseUrl || "—"}</li>
          <li>Ping avg: {formatMs(data.ping?.avg)}</li>
          <li>Ping p95: {formatMs(data.ping?.p95)}</li>
          <li>TTFB: {formatMs(data.ttfbMs)}</li>
          <li>Download: {formatMbps(data.download?.mbps)}</li>
          <li>Upload: {formatMbps(data.upload?.mbps)}</li>
        </ul>
      )}
    </div>
  )

  return (
    <div className="nt-history-item">
      <button type="button" className="nt-history-summary" onClick={() => setOpen((v) => !v)}>
        <span>{timeLabel}</span>
        <span className="nt-history-meta">
          CF: {cfSummary} · AutoDL: {adSummary}
        </span>
      </button>
      {open ? (
        <div className="nt-history-body">
          <div className="nt-history-grid">
            {renderSide("Cloudflare", entry.cloudflare)}
            {renderSide("AutoDL Public", entry.autodl)}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function TestColumn({
  title,
  accentClass,
  baseUrl,
  onBaseUrlChange,
  running,
  status,
  result,
  onStart,
  hint,
  placeholder,
}) {
  return (
    <section className={`nt-card ${accentClass}`}>
      <h2>{title}</h2>
      <div className="nt-field">
        <label htmlFor={`${title}-base-url`}>Base URL</label>
        <input
          id={`${title}-base-url`}
          className="nt-input"
          type="url"
          placeholder={placeholder}
          value={baseUrl}
          onChange={(e) => onBaseUrlChange(e.target.value)}
          disabled={running}
        />
        {hint ? <p className="nt-field-hint">{hint}</p> : null}
      </div>
      <button type="button" className="nt-btn nt-btn--primary" disabled={running} onClick={onStart}>
        {running ? "测试中…" : "开始测试"}
      </button>
      {status ? <p className="nt-status">{status}</p> : null}
      <ResultMetrics result={result} />
    </section>
  )
}

export default function NetworkTest() {
  const navigate = useNavigate()
  const theme = useCanvasStore((s) => s.theme)

  const [cfUrl, setCfUrl] = useState(() => localStorage.getItem("velora-network-test-cf-url") || DEFAULT_CF_URL)
  const [adUrl, setAdUrl] = useState(() => localStorage.getItem("velora-network-test-ad-url") || DEFAULT_AD_URL)
  const [cfRunning, setCfRunning] = useState(false)
  const [adRunning, setAdRunning] = useState(false)
  const [cfStatus, setCfStatus] = useState("")
  const [adStatus, setAdStatus] = useState("")
  const [cfResult, setCfResult] = useState(null)
  const [adResult, setAdResult] = useState(null)
  const [history, setHistory] = useState(() => loadNetworkTestHistory())

  useEffect(() => {
    localStorage.setItem("velora-network-test-cf-url", cfUrl)
  }, [cfUrl])

  useEffect(() => {
    localStorage.setItem("velora-network-test-ad-url", adUrl)
  }, [adUrl])

  const running = cfRunning || adRunning

  const runSide = useCallback(async (side, baseUrl, setRunning, setStatus, setResult) => {
    if (!baseUrl.trim()) {
      setResult({ error: "请先填写 Base URL" })
      return null
    }

    setRunning(true)
    setStatus("准备测试…")
    setResult(null)

    try {
      const result = await runFullNetworkTest(baseUrl, ({ phase, message, speedMbps, percent, elapsedSec, stalled }) => {
        if (phase === "ping") setStatus(message || "Ping 测试中…")
        if (phase === "download") {
          const speedPart = speedMbps > 0 ? ` · ${speedMbps.toFixed(2)} MB/s` : ""
          const elapsedPart = elapsedSec > 0 ? ` · ${Math.round(elapsedSec)}s` : ""
          const stallPart = stalled ? " · 传输暂停，可能在等待网络/Tunnel" : ""
          setStatus(`${message || "下载测试中…"}${speedPart}${elapsedPart}${stallPart}`)
        }
        if (phase === "upload" || phase === "preparing" || phase === "uploading") {
          const speedPart = speedMbps > 0 ? ` · ${speedMbps.toFixed(2)} MB/s` : ""
          const percentPart = percent > 0 ? ` · ${percent.toFixed(1)}%` : ""
          const elapsedPart = elapsedSec > 0 ? ` · ${Math.round(elapsedSec)}s` : ""
          const stallPart = stalled ? " · 传输暂停，可能在等待 Tunnel/网络" : ""
          setStatus(`${message || "上传测试中…"}${percentPart}${speedPart}${elapsedPart}${stallPart}`)
        }
      })
      setResult(result)
      setStatus("测试完成")
      return result
    } catch (err) {
      const message = err?.message || "测试失败"
      setResult({ error: message, baseUrl: baseUrl.trim() })
      setStatus("")
      return { error: message, baseUrl: baseUrl.trim() }
    } finally {
      setRunning(false)
    }
  }, [])

  const persistHistory = useCallback((cf, ad) => {
    const entry = {
      id: `${Date.now()}`,
      timestamp: new Date().toISOString(),
      cloudflare: cf,
      autodl: ad,
    }
    const next = saveNetworkTestHistory(entry)
    setHistory(next)
  }, [])

  const handleRunCloudflare = useCallback(async () => {
    const result = await runSide("cloudflare", cfUrl, setCfRunning, setCfStatus, setCfResult)
    if (result && !result.error) {
      persistHistory(result, adResult)
    } else if (result?.error) {
      persistHistory(result, adResult)
    }
  }, [adResult, cfUrl, persistHistory, runSide])

  const handleRunAutodl = useCallback(async () => {
    const result = await runSide("autodl", adUrl, setAdRunning, setAdStatus, setAdResult)
    if (result) {
      persistHistory(cfResult, result)
    }
  }, [adUrl, cfResult, persistHistory, runSide])

  const handleRunBoth = useCallback(async () => {
    const [cf, ad] = await Promise.all([
      runSide("cloudflare", cfUrl, setCfRunning, setCfStatus, setCfResult),
      runSide("autodl", adUrl, setAdRunning, setAdStatus, setAdResult),
    ])
    persistHistory(cf, ad)
  }, [adUrl, cfUrl, persistHistory, runSide])

  const comparisonRows = useMemo(() => {
    if (!cfResult || !adResult || cfResult.error || adResult.error) return []
    return compareNetworkResults(cfResult, adResult)
  }, [cfResult, adResult])

  return (
    <div className={`nt-page rf-page rf-page--${theme}`}>
      <div className="nt-shell">
        <header className="nt-header">
          <div>
            <h1>网络性能测试</h1>
            <p className="nt-subtitle">
              对比 Cloudflare Tunnel 与 AutoDL 公网映射的 API 延迟、TTFB、下载与上传速度。全部基于浏览器 fetch 与 performance.now()。
            </p>
          </div>
          <div className="nt-header-actions">
            <button type="button" className="nt-btn nt-btn--ghost" onClick={() => navigate("/admin")}>
              返回管理后台
            </button>
            <button type="button" className="nt-btn nt-btn--ghost" onClick={() => navigate("/workspace")}>
              返回工作区
            </button>
            <button type="button" className="nt-btn nt-btn--primary" disabled={running} onClick={handleRunBoth}>
              两侧同时测试
            </button>
          </div>
        </header>

        <div className="nt-grid">
          <TestColumn
            title="Cloudflare"
            accentClass="nt-card--cf"
            baseUrl={cfUrl}
            onBaseUrlChange={setCfUrl}
            running={cfRunning}
            status={cfStatus}
            result={cfResult}
            onStart={handleRunCloudflare}
            placeholder="https://velora.seele0420.cloud"
            hint="Cloudflare Tunnel 公网域名，只填协议+域名（不要带 /api 路径）。流量：浏览器 → Cloudflare → cloudflared → Nginx :6006 → 后端。"
          />
          <TestColumn
            title="AutoDL Public"
            accentClass="nt-card--ad"
            baseUrl={adUrl}
            onBaseUrlChange={setAdUrl}
            running={adRunning}
            status={adStatus}
            result={adResult}
            onStart={handleRunAutodl}
            placeholder="https://xxxx.seetacloud.com:8443"
            hint="AutoDL 控制台「自定义服务」里的公网映射地址，同样只填 Base URL。"
          />
        </div>

        {comparisonRows.length > 0 ? (
          <section className="nt-panel">
            <h3>对比结果</h3>
            <div className="nt-table-wrap">
              <table className="nt-table">
                <thead>
                  <tr>
                    <th>项目</th>
                    <th>Cloudflare</th>
                    <th>AutoDL</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisonRows.map((row) => (
                    <tr key={row.key}>
                      <td>{row.label}</td>
                      <td>
                        {row.cfValid
                          ? row.unit === "ms"
                            ? formatMs(row.cf)
                            : formatMbps(row.cf)
                          : "—"}
                        {row.cfNote ? <span className="nt-note nt-note--cf">{row.cfNote}</span> : null}
                      </td>
                      <td>
                        {row.adValid
                          ? row.unit === "ms"
                            ? formatMs(row.ad)
                            : formatMbps(row.ad)
                          : "—"}
                        {row.adNote ? <span className="nt-note">{row.adNote}</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        <section className="nt-panel">
          <h3>历史记录（最近 20 次）</h3>
          {history.length === 0 ? (
            <p className="nt-empty">暂无历史记录</p>
          ) : (
            <div className="nt-history-list">
              {history.map((entry) => (
                <HistoryItem key={entry.id || entry.timestamp} entry={entry} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
