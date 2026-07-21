import { useCallback, useEffect, useState } from "react"
import { useTeamStore } from "../../stores"
import { fetchTaskRecords } from "../../services/tasksApi"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import {
  filterGenHistory,
  filterPersonalHistory,
  formatHistoryTime,
  mapTaskRecordsToHistory,
  readGenHistory,
} from "../../utils/canvas/genHistory"
import "./GenHistoryVideoPicker.css"

function HistoryThumb({ item }) {
  const [broken, setBroken] = useState(false)
  const url = ensureMediaUrl(item.mediaUrl)
  if (broken) {
    return <div className="rp-gh-thumb rp-gh-thumb--broken">无法预览</div>
  }
  return (
    <video
      src={url}
      className="rp-gh-thumb"
      muted
      playsInline
      preload="metadata"
      onError={() => setBroken(true)}
    />
  )
}

function dedupeByUrl(items) {
  const seen = new Set()
  const out = []
  for (const item of items) {
    const key = (item.mediaUrl || "").split("?")[0]
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(item)
  }
  return out
}

export async function loadVideoHistoryItems(scope, activeTeamId) {
  if (scope === "team") {
    if (!activeTeamId) return []
    const records = await fetchTaskRecords({ teamId: activeTeamId, limit: 200 })
    return dedupeByUrl(
      mapTaskRecordsToHistory(records).filter((h) => h.kind === "video"),
    )
  }
  const local = filterGenHistory(
    filterPersonalHistory(readGenHistory([], {})),
    "video",
  )
  let server = []
  try {
    const records = await fetchTaskRecords({ limit: 200 })
    server = mapTaskRecordsToHistory(records).filter((h) => h.kind === "video")
  } catch {
    server = []
  }
  return dedupeByUrl([...local, ...server])
}

/**
 * Click-to-select video grid from personal/team generation history.
 */
export default function GenHistoryVideoPicker({
  selectedId,
  onSelect,
  disabled,
  scope: scopeProp,
  onScopeChange,
}) {
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const [scopeInternal, setScopeInternal] = useState("mine")
  const scope = scopeProp ?? scopeInternal
  const setScope = onScopeChange ?? setScopeInternal
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setItems(await loadVideoHistoryItems(scope, activeTeamId))
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [scope, activeTeamId])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="rp-gh">
      <div className="rp-gh-scopes">
        <button
          type="button"
          className={`rp-source-tab${scope === "mine" ? " rp-source-tab--active" : ""}`}
          disabled={disabled}
          onClick={() => setScope("mine")}
        >
          个人
        </button>
        <button
          type="button"
          className={`rp-source-tab${scope === "team" ? " rp-source-tab--active" : ""}`}
          disabled={disabled || !activeTeamId}
          onClick={() => setScope("team")}
          title={activeTeamId ? undefined : "当前无团队"}
        >
          团队
        </button>
      </div>

      {loading ? (
        <p className="rp-hint">加载生成历史…</p>
      ) : items.length === 0 ? (
        <p className="rp-hint">
          {scope === "team" ? "暂无团队视频生成记录" : "暂无个人视频生成历史"}
        </p>
      ) : (
        <div className="rp-gh-grid">
          {items.map((item) => {
            const active = selectedId === item.id
            return (
              <button
                key={item.id}
                type="button"
                className={`rp-gh-card${active ? " rp-gh-card--active" : ""}`}
                disabled={disabled}
                onClick={() => onSelect?.(item)}
              >
                <HistoryThumb item={item} />
                <div className="rp-gh-meta">
                  <span className="rp-gh-title" title={item.title || item.prompt}>
                    {item.title || item.prompt || "视频"}
                  </span>
                  <span className="rp-gh-time">{formatHistoryTime(item.ts)}</span>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
