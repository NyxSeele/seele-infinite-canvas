import { useCallback, useEffect, useMemo, useState } from "react"
import ReactMarkdown from "react-markdown"
import api, { API_BASE } from "../../services/api"
import { appendMediaTicket, stripMediaTicket } from "../../utils/mediaTicket"
import { normalizeAdminModel } from "./modelUtils"
import { formatApiError } from "./formatApiError"
import "./FeedbackAnalysis.css"

const PAGE_SIZE = 50

function formatDate(iso) {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleString("zh-CN")
  } catch {
    return iso
  }
}

function formatGenerationSeconds(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "—"
  return `${Number(seconds).toFixed(1)}秒`
}

function topTag(tagCounts) {
  const entries = Object.entries(tagCounts || {})
  if (!entries.length) return "—"
  entries.sort((a, b) => b[1] - a[1])
  const [tag, count] = entries[0]
  return `${tag}（${count}）`
}

function ratingLabel(rating) {
  if (rating === 1) return "满意"
  if (rating === 0) return "不满意"
  return "—"
}

function ratingBadgeClass(rating) {
  if (rating === 1) return "adm-badge--done"
  if (rating === 0) return "adm-badge--error"
  return "adm-badge--disabled"
}

function formatParamsSummary(params) {
  if (!params || typeof params !== "object") return "—"
  const parts = []
  if (params.ratio) parts.push(`比例 ${params.ratio}`)
  if (params.quality) parts.push(`清晰度 ${params.quality}`)
  if (params.resolution) parts.push(`分辨率 ${params.resolution}`)
  if (params.duration) parts.push(`${params.duration}s`)
  if (params.mode) parts.push(params.mode)
  if (params.width && params.height) parts.push(`${params.width}×${params.height}`)
  if (params.has_reference) parts.push(`参考图×${params.reference_count || 1}`)
  return parts.length ? parts.join(" · ") : "—"
}

function mediaDisplayUrl(record) {
  const raw = record.result_url || record.result
  if (!raw) return ""
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    if (!raw.includes("/api/view") && !raw.includes("/api/uploads")) {
      return raw
    }
  }
  const stripped = stripMediaTicket(raw)
  const relative = stripped.startsWith("/") ? stripped : `/${stripped}`
  const base = API_BASE || ""
  const target = base ? `${base}${relative}` : relative
  return appendMediaTicket(target)
}

function TrendsChart({ series }) {
  const points = series || []
  if (!points.length) return <div className="adm-empty">暂无趋势数据</div>
  const maxTotal = Math.max(...points.map((p) => p.total), 1)
  const width = 640
  const height = 120
  const pad = 8
  const step = points.length > 1 ? (width - pad * 2) / (points.length - 1) : 0
  const coords = points.map((p, i) => {
    const x = pad + i * step
    const y = height - pad - (p.total / maxTotal) * (height - pad * 2)
    return { x, y, ...p }
  })
  const line = coords.map((c) => `${c.x},${c.y}`).join(" ")
  return (
    <div className="feedback-trends">
      <svg viewBox={`0 0 ${width} ${height}`} className="feedback-trends__svg" aria-hidden>
        <polyline points={line} fill="none" stroke="currentColor" strokeWidth="2" />
        {coords.map((c) => (
          <circle key={c.date} cx={c.x} cy={c.y} r="3" fill="currentColor" />
        ))}
      </svg>
      <div className="feedback-trends__labels">
        <span>{points[0]?.date}</span>
        <span>{points[points.length - 1]?.date}</span>
      </div>
    </div>
  )
}

export default function FeedbackAnalysis() {
  const [stats, setStats] = useState(null)
  const [trends, setTrends] = useState(null)
  const [records, setRecords] = useState([])
  const [recordsTotal, setRecordsTotal] = useState(0)
  const [history, setHistory] = useState([])
  const [modelMap, setModelMap] = useState({})
  const [loadingStats, setLoadingStats] = useState(true)
  const [loadingRecords, setLoadingRecords] = useState(true)
  const [ratingFilter, setRatingFilter] = useState("")
  const [modelFilter, setModelFilter] = useState("")
  const [taskTypeFilter, setTaskTypeFilter] = useState("")
  const [sinceFilter, setSinceFilter] = useState("")
  const [untilFilter, setUntilFilter] = useState("")
  const [expandedPrompts, setExpandedPrompts] = useState({})
  const [expandedDiffs, setExpandedDiffs] = useState({})
  const [analysis, setAnalysis] = useState("")
  const [analysisJson, setAnalysisJson] = useState(null)
  const [visionCount, setVisionCount] = useState(0)
  const [visionMeta, setVisionMeta] = useState([])
  const [llmModelId, setLlmModelId] = useState("")
  const [expandedSamples, setExpandedSamples] = useState({})
  const [analyzeState, setAnalyzeState] = useState("idle")
  const [analyzeError, setAnalyzeError] = useState("")
  const [showHistory, setShowHistory] = useState(false)

  const filterParams = useMemo(() => {
    const params = {}
    if (sinceFilter) params.since = new Date(sinceFilter).toISOString()
    if (untilFilter) {
      const end = new Date(untilFilter)
      end.setHours(23, 59, 59, 999)
      params.until = end.toISOString()
    }
    if (taskTypeFilter) params.task_type = taskTypeFilter
    return params
  }, [sinceFilter, untilFilter, taskTypeFilter])

  const modelOptions = useMemo(() => {
    const ids = new Set()
    ;(stats?.by_model || []).forEach((row) => ids.add(row.model_id))
    records.forEach((row) => ids.add(row.model_id))
    return Array.from(ids).filter(Boolean).sort()
  }, [stats, records])

  const displayModelName = useCallback(
    (modelId) => modelMap[modelId] || modelId || "—",
    [modelMap],
  )

  const loadModels = useCallback(async () => {
    try {
      const res = await api.get("/api/admin/models")
      const rows = res.data?.models || []
      const map = {}
      rows.forEach((raw) => {
        const m = normalizeAdminModel(raw)
        map[m.id] = m.display_name
      })
      setModelMap(map)
    } catch {
      setModelMap({})
    }
  }, [])

  const loadStats = useCallback(async () => {
    setLoadingStats(true)
    try {
      const [statsRes, trendsRes] = await Promise.all([
        api.get("/api/admin/feedback/stats", { params: filterParams }),
        api.get("/api/admin/feedback/trends", { params: { days: 30 } }),
      ])
      setStats(statsRes.data)
      setTrends(trendsRes.data)
    } catch {
      setStats(null)
      setTrends(null)
    } finally {
      setLoadingStats(false)
    }
  }, [filterParams])

  const loadHistory = useCallback(async () => {
    try {
      const res = await api.get("/api/admin/feedback/analyses", { params: { limit: 20 } })
      setHistory(res.data?.items || [])
    } catch {
      setHistory([])
    }
  }, [])

  const loadRecords = useCallback(async () => {
    setLoadingRecords(true)
    try {
      const params = {
        limit: PAGE_SIZE,
        offset: 0,
        ...filterParams,
      }
      if (ratingFilter !== "") params.rating = Number(ratingFilter)
      if (modelFilter) params.model_id = modelFilter
      const res = await api.get("/api/admin/feedback/records", { params })
      setRecords(res.data?.items || [])
      setRecordsTotal(res.data?.total || 0)
    } catch {
      setRecords([])
      setRecordsTotal(0)
    } finally {
      setLoadingRecords(false)
    }
  }, [ratingFilter, modelFilter, filterParams])

  useEffect(() => {
    loadModels()
    loadHistory()
  }, [loadModels, loadHistory])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  useEffect(() => {
    loadRecords()
  }, [loadRecords])

  const analyzeParams = useMemo(() => {
    const params = { ...filterParams }
    if (ratingFilter !== "") params.rating = Number(ratingFilter)
    if (modelFilter) params.model_id = modelFilter
    return params
  }, [filterParams, ratingFilter, modelFilter])

  const satisfiedRate = stats?.total
    ? `${Math.round((stats.satisfied / stats.total) * 100)}%`
    : "—"

  const canAnalyze = recordsTotal >= 10
  const analyzeDisabled = !canAnalyze || analyzeState === "loading"

  const handleAnalyze = async () => {
    if (!canAnalyze || analyzeState === "loading") return
    setAnalyzeState("loading")
    setAnalyzeError("")
    try {
      const res = await api.post("/api/admin/feedback/analyze", null, {
        params: analyzeParams,
      })
      setAnalysis(res.data?.analysis || "")
      setAnalysisJson(res.data?.analysis_json || null)
      setVisionCount(res.data?.vision_count || 0)
      setVisionMeta(res.data?.vision_meta || [])
      setLlmModelId(res.data?.llm_model_id || "")
      setExpandedSamples({})
      setAnalyzeState("done")
      loadHistory()
    } catch (e) {
      setAnalyzeError(formatApiError(e.response?.data?.detail, "AI 分析失败"))
      setAnalyzeState("idle")
    }
  }

  const togglePrompt = (taskId) => {
    setExpandedPrompts((prev) => ({ ...prev, [taskId]: !prev[taskId] }))
  }

  const toggleDiff = (taskId) => {
    setExpandedDiffs((prev) => ({ ...prev, [taskId]: !prev[taskId] }))
  }

  return (
    <div className="feedback-page">
      <div className="adm-page-header feedback-page__header">
        <h2 className="adm-page-title" style={{ marginBottom: 0 }}>生成反馈</h2>
        <div className="feedback-header-actions">
          <button
            type="button"
            className="adm-btn"
            onClick={() => setShowHistory((v) => !v)}
          >
            {showHistory ? "隐藏历史" : "分析历史"}
          </button>
          <button
            type="button"
            className="adm-btn adm-btn--primary feedback-analyze-btn"
            disabled={analyzeDisabled}
            onClick={handleAnalyze}
          >
            {analyzeState === "loading" && <span className="feedback-analyze-spinner" aria-hidden />}
            {canAnalyze
              ? analyzeState === "loading"
                ? "分析中…"
                : "AI 分析"
              : `当前筛选下数据不足（${recordsTotal}/10）`}
          </button>
        </div>
      </div>

      <div className="adm-filter-bar feedback-filter-bar feedback-filter-bar--top">
        <select
          className="feedback-model-select"
          value={taskTypeFilter}
          onChange={(e) => setTaskTypeFilter(e.target.value)}
        >
          <option value="">全部类型</option>
          <option value="image">图像</option>
          <option value="video">视频</option>
        </select>
        <input
          type="date"
          className="feedback-date-input"
          value={sinceFilter}
          onChange={(e) => setSinceFilter(e.target.value)}
          aria-label="开始日期"
        />
        <input
          type="date"
          className="feedback-date-input"
          value={untilFilter}
          onChange={(e) => setUntilFilter(e.target.value)}
          aria-label="结束日期"
        />
      </div>

      {loadingStats ? (
        <div className="adm-loading">加载统计数据…</div>
      ) : !stats ? (
        <div className="adm-empty">加载统计数据失败</div>
      ) : (
        <>
          <div className="adm-stats-grid feedback-stats-grid">
            <div className="adm-stat-card">
              <div className="adm-stat-label">总评价数</div>
              <div className="adm-stat-value accent">{stats.total}</div>
            </div>
            <div className="adm-stat-card">
              <div className="adm-stat-label">满意率</div>
              <div className="adm-stat-value">{satisfiedRate}</div>
            </div>
            <div className="adm-stat-card">
              <div className="adm-stat-label">不满意数</div>
              <div className="adm-stat-value">{stats.unsatisfied}</div>
            </div>
            <div className="adm-stat-card">
              <div className="adm-stat-label">最常见问题标签</div>
              <div className="adm-stat-value feedback-top-tag">{topTag(stats.tag_counts)}</div>
            </div>
          </div>

          <section className="feedback-section">
            <h3 className="feedback-section__title">近 30 天评价趋势</h3>
            <TrendsChart series={trends?.series} />
          </section>
        </>
      )}

      {stats?.tag_counts_by_model && Object.keys(stats.tag_counts_by_model).length > 0 ? (
        <section className="feedback-section">
          <h3 className="feedback-section__title">模型 × 问题分布</h3>
          <div className="adm-table-wrap">
            <table className="adm-table feedback-heatmap-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>问题标签</th>
                  <th>次数</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stats.tag_counts_by_model).flatMap(([modelId, tags]) =>
                  Object.entries(tags)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 5)
                    .map(([tag, count]) => (
                      <tr key={`${modelId}-${tag}`}>
                        <td>{displayModelName(modelId)}</td>
                        <td>{tag}</td>
                        <td>{count}</td>
                      </tr>
                    )),
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="feedback-section">
        <h3 className="feedback-section__title">按模型满意率</h3>
        <div className="adm-table-wrap">
          <table className="adm-table feedback-model-table">
            <thead>
              <tr>
                <th>模型名</th>
                <th>总评价</th>
                <th>满意</th>
                <th>不满意</th>
                <th>满意率</th>
              </tr>
            </thead>
            <tbody>
              {(stats?.by_model || []).length === 0 ? (
                <tr>
                  <td colSpan={5} className="adm-empty">暂无评价数据</td>
                </tr>
              ) : (
                stats.by_model.map((row) => {
                  const unsatisfied = row.total - row.satisfied
                  const pct = Math.round(row.rate * 100)
                  const lowSample = row.total < 20
                  return (
                    <tr key={row.model_id} className={lowSample ? "feedback-row--low-sample" : ""}>
                      <td>
                        {displayModelName(row.model_id)}
                        {lowSample ? <span className="feedback-low-sample">样本不足</span> : null}
                      </td>
                      <td>{row.total}</td>
                      <td>{row.satisfied}</td>
                      <td>{unsatisfied}</td>
                      <td>
                        <div className="feedback-rate-cell">
                          <div className="feedback-rate-bar" aria-hidden>
                            <span className="feedback-rate-bar__fill" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="feedback-rate-text">{pct}%</span>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {stats?.tag_cooccurrence?.length ? (
        <section className="feedback-section">
          <h3 className="feedback-section__title">不满意标签共现</h3>
          <div className="feedback-cooccurrence">
            {stats.tag_cooccurrence.map((item) => (
              <span key={item.tags.join("-")} className="feedback-cooccurrence__chip">
                {item.tags.join(" + ")}（{item.count}）
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <section className="feedback-section">
        <div className="feedback-section__head">
          <h3 className="feedback-section__title">评价记录</h3>
          <span className="feedback-section__meta">共 {recordsTotal} 条</span>
        </div>

        <div className="adm-filter-bar feedback-filter-bar">
          <div className="feedback-filter-group">
            {[
              { value: "", label: "全部" },
              { value: "1", label: "满意" },
              { value: "0", label: "不满意" },
            ].map((opt) => (
              <button
                key={opt.value || "all"}
                type="button"
                className={`adm-btn adm-btn--sm feedback-filter-btn${
                  ratingFilter === opt.value ? " feedback-filter-btn--active" : ""
                }`}
                onClick={() => setRatingFilter(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <select
            className="feedback-model-select"
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
          >
            <option value="">全部模型</option>
            {modelOptions.map((id) => (
              <option key={id} value={id}>
                {displayModelName(id)}
              </option>
            ))}
          </select>
        </div>

        {loadingRecords ? (
          <div className="adm-loading">加载评价记录…</div>
        ) : records.length === 0 ? (
          <div className="adm-empty">暂无评价记录</div>
        ) : (
          <div className="feedback-records">
            {records.map((record) => {
              const expanded = !!expandedPrompts[record.task_id]
              const diffOpen = !!expandedDiffs[record.task_id]
              const mediaUrl = mediaDisplayUrl(record)
              return (
                <article key={record.task_id} className="feedback-record">
                  <div className="feedback-record__input">
                    <span className="feedback-record__label">原始输入</span>
                    <p>{record.original_input || "—"}</p>
                  </div>
                  <div className="feedback-record__prompt">
                    <button
                      type="button"
                      className="feedback-prompt-toggle"
                      onClick={() => toggleDiff(record.task_id)}
                    >
                      {diffOpen ? "收起 Prompt 对比" : "展开 Prompt 对比"}
                    </button>
                    {diffOpen ? (
                      <div className="feedback-prompt-diff">
                        <div>
                          <span className="feedback-record__label">原始</span>
                          <pre className="feedback-prompt-body">{record.original_input || "—"}</pre>
                        </div>
                        <div>
                          <span className="feedback-record__label">编译后</span>
                          <pre className="feedback-prompt-body">{record.compiled_prompt || "—"}</pre>
                        </div>
                      </div>
                    ) : null}
                    <button
                      type="button"
                      className="feedback-prompt-toggle"
                      onClick={() => togglePrompt(record.task_id)}
                    >
                      {expanded ? "收起编译后 prompt" : "展开编译后 prompt"}
                    </button>
                    {expanded ? (
                      <pre className="feedback-prompt-body">{record.compiled_prompt || "—"}</pre>
                    ) : null}
                  </div>
                  {record.rating_comment ? (
                    <p className="feedback-record__comment">补充：{record.rating_comment}</p>
                  ) : null}
                  <p className="feedback-record__params">参数：{formatParamsSummary(record.generation_params)}</p>
                  {mediaUrl ? (
                    <div className="feedback-record__media">
                      {record.task_type === "video" ? (
                        <video src={mediaUrl} controls preload="metadata" className="feedback-media" />
                      ) : (
                        <img src={mediaUrl} alt="生成结果" className="feedback-media" />
                      )}
                    </div>
                  ) : null}
                  <div className="feedback-record__meta">
                    <span>{record.task_type}</span>
                    <span>{displayModelName(record.model_id)}</span>
                    <span className={`adm-badge ${ratingBadgeClass(record.user_rating)}`}>
                      {ratingLabel(record.user_rating)}
                    </span>
                    <span className="feedback-record__tags">
                      {(record.rating_tags || []).length
                        ? record.rating_tags.join("、")
                        : "无标签"}
                    </span>
                    <span>生成耗时：{formatGenerationSeconds(record.generation_seconds)}</span>
                    <span>{formatDate(record.rated_at)}</span>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>

      {(analysis || analyzeError) && (
        <section className="feedback-section feedback-analysis">
          <h3 className="feedback-section__title">AI 分析结果</h3>
          {analyzeError ? (
            <div className="feedback-analysis__error">{analyzeError}</div>
          ) : (
            <>
              {visionCount > 0 ? (
                <p className="feedback-analysis__vision-meta">
                  本次已对照 {visionCount} 张生成结果图进行分析
                  {llmModelId ? (
                    <span className="feedback-analysis__vision-skipped">
                      （模型：{displayModelName(llmModelId)}）
                    </span>
                  ) : null}
                  {visionMeta.some((item) => item.vision === "skipped") ? (
                    <span className="feedback-analysis__vision-skipped">
                      （{visionMeta.filter((item) => item.vision === "skipped").length} 个样本因下载或抽帧失败被跳过）
                    </span>
                  ) : null}
                </p>
              ) : llmModelId ? (
                <p className="feedback-analysis__vision-meta">
                  使用模型：{displayModelName(llmModelId)}
                </p>
              ) : null}
              {analysisJson ? (
                <div className="feedback-analysis__cards">
                  {analysisJson.issues?.length ? (
                    <div className="feedback-analysis-card">
                      <h4>主要问题</h4>
                      <ul>
                        {analysisJson.issues.map((item, i) => (
                          <li key={i}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {analysisJson.good_patterns?.length ? (
                    <div className="feedback-analysis-card">
                      <h4>有效模式</h4>
                      <ul>
                        {analysisJson.good_patterns.map((item, i) => (
                          <li key={i}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {analysisJson.actions?.length ? (
                    <div className="feedback-analysis-card">
                      <h4>改进行动</h4>
                      <ul>
                        {analysisJson.actions.map((item, i) => (
                          <li key={i}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {analysisJson?.per_sample?.length ? (
                <div className="feedback-per-sample">
                  <h4 className="feedback-per-sample__title">逐条调优建议（{analysisJson.per_sample.length}）</h4>
                  {analysisJson.per_sample.map((sample, index) => {
                    const taskId = sample.task_id || `sample-${index}`
                    const open = !!expandedSamples[taskId]
                    const diagnosis = sample.prompt_diagnosis || sample.diagnosis || ""
                    const patch = sample.suggested_prompt_patch || sample.prompt_patch || ""
                    const issues = Array.isArray(sample.visual_issues)
                      ? sample.visual_issues
                      : sample.visual_issues
                        ? [String(sample.visual_issues)]
                        : []
                    const hints = Array.isArray(sample.param_hints)
                      ? sample.param_hints
                      : sample.param_hints
                        ? [String(sample.param_hints)]
                        : []
                    return (
                      <details
                        key={taskId}
                        className="feedback-per-sample__item"
                        open={open}
                        onToggle={(e) => {
                          setExpandedSamples((prev) => ({
                            ...prev,
                            [taskId]: e.currentTarget.open,
                          }))
                        }}
                      >
                        <summary>
                          <span className="feedback-per-sample__id">{taskId}</span>
                          {diagnosis ? (
                            <span className="feedback-per-sample__summary">{diagnosis}</span>
                          ) : (
                            <span className="feedback-per-sample__summary">点击查看详情</span>
                          )}
                        </summary>
                        <div className="feedback-per-sample__body">
                          {issues.length ? (
                            <div>
                              <span className="feedback-record__label">画面问题</span>
                              <ul>
                                {issues.map((item, i) => (
                                  <li key={i}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                          {diagnosis ? (
                            <div>
                              <span className="feedback-record__label">Prompt 诊断</span>
                              <p>{diagnosis}</p>
                            </div>
                          ) : null}
                          {patch ? (
                            <div>
                              <span className="feedback-record__label">建议修改</span>
                              <pre className="feedback-prompt-body">{patch}</pre>
                            </div>
                          ) : null}
                          {hints.length ? (
                            <div>
                              <span className="feedback-record__label">参数建议</span>
                              <ul>
                                {hints.map((item, i) => (
                                  <li key={i}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                        </div>
                      </details>
                    )
                  })}
                </div>
              ) : null}
              <div className="feedback-analysis__markdown">
                <ReactMarkdown>{analysis}</ReactMarkdown>
              </div>
            </>
          )}
        </section>
      )}

      {showHistory && history.length > 0 ? (
        <section className="feedback-section">
          <h3 className="feedback-section__title">历史分析</h3>
          <div className="feedback-history">
            {history.map((item) => (
              <details key={item.id} className="feedback-history__item">
                <summary>
                  {formatDate(item.created_at)} · {item.record_count} 条 · vision {item.vision_count}
                </summary>
                {item.analysis_json?.per_sample?.length ? (
                  <p className="feedback-analysis__vision-meta">
                    含 {item.analysis_json.per_sample.length} 条逐样本调优建议
                  </p>
                ) : null}
                <div className="feedback-analysis__markdown">
                  <ReactMarkdown>{item.analysis}</ReactMarkdown>
                </div>
              </details>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}
