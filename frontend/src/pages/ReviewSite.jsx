import { useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useLocation } from "react-router-dom"
import { listPublicReviewVideos } from "../services/reviewPublicApi"
import {
  REVIEWER_NAME_KEY,
  ReviewerNameGate,
  useReviewerName,
} from "../components/review/ReviewerNameGate"
import VeloraShellBackground from "../components/common/VeloraShellBackground"
import { navigateWithReturn } from "../utils/navReturn"
import { encodePublicMediaUrl } from "../utils/encodePublicMediaUrl"
import "../styles/velora-brand.css"
import "./ReviewSite.css"

const SORT_OPTIONS = [
  { id: "newest", label: "最新发布" },
  { id: "rating", label: "评分最高" },
  { id: "engagement", label: "互动最多" },
]

function formatScore(v) {
  if (v == null || Number.isNaN(Number(v))) return "—"
  return Number(v).toFixed(1)
}

function formatRelativeTime(iso) {
  if (!iso) return ""
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ""
  const diff = Date.now() - t
  const m = Math.floor(diff / 60000)
  if (m < 1) return "刚刚"
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d} 天前`
  try {
    return new Date(iso).toLocaleDateString("zh-CN")
  } catch {
    return ""
  }
}

function publisherInitial(name) {
  const s = (name || "?").trim()
  return s.slice(0, 1).toUpperCase()
}

function sortVideos(list, sortId) {
  const arr = [...list]
  if (sortId === "rating") {
    arr.sort((a, b) => {
      const ra = a.avg_rating == null ? -1 : Number(a.avg_rating)
      const rb = b.avg_rating == null ? -1 : Number(b.avg_rating)
      if (rb !== ra) return rb - ra
      return new Date(b.published_at) - new Date(a.published_at)
    })
    return arr
  }
  if (sortId === "engagement") {
    arr.sort((a, b) => {
      const ea = (a.like_count || 0) + (a.dislike_count || 0) + (a.comment_count || 0)
      const eb = (b.like_count || 0) + (b.dislike_count || 0) + (b.comment_count || 0)
      if (eb !== ea) return eb - ea
      return new Date(b.published_at) - new Date(a.published_at)
    })
    return arr
  }
  // newest
  arr.sort((a, b) => new Date(b.published_at) - new Date(a.published_at))
  return arr
}

function VideoCard({ video, onOpen, isNewest }) {
  const thumb = video.thumbnail_url
    ? encodePublicMediaUrl(video.thumbnail_url)
    : null

  return (
    <button
      type="button"
      className="rs-card"
      onClick={() => onOpen(video.id)}
    >
      <div className="rs-card-thumb">
        {thumb ? (
          <img
            src={thumb}
            alt=""
            loading="lazy"
            onError={(e) => {
              e.currentTarget.style.display = "none"
              const fb = e.currentTarget.parentElement?.querySelector(".rs-thumb-fallback")
              if (fb) fb.style.display = "flex"
            }}
          />
        ) : null}
        <div
          className="rs-thumb-fallback"
          style={{ display: thumb ? "none" : "flex" }}
        >
          暂无封面
        </div>
        <div className="rs-card-thumb-veil" aria-hidden />
        <div className="rs-card-play" aria-hidden>
          <span />
        </div>
        {isNewest && <div className="rs-card-chip">最新</div>}
        {video.avg_rating != null && (
          <div className="rs-card-badge">★ {formatScore(video.avg_rating)}</div>
        )}
      </div>
      <div className="rs-card-body">
        <div className="rs-card-row">
          <div className="rs-avatar" aria-hidden>
            {publisherInitial(video.publisher_name)}
          </div>
          <div className="rs-card-copy">
            <div className="rs-card-title">{video.title}</div>
            <div className="rs-card-meta">
              <span>{video.publisher_name}</span>
              <span className="rs-dot">·</span>
              <span>{formatRelativeTime(video.published_at)}</span>
            </div>
            <div className="rs-card-stats">
              <span>赞 {video.like_count}</span>
              <span>踩 {video.dislike_count}</span>
              <span>评 {video.comment_count}</span>
            </div>
          </div>
        </div>
      </div>
    </button>
  )
}

export default function ReviewSite() {
  const navigate = useNavigate()
  const location = useLocation()
  const { name, setName, ready, askName } = useReviewerName()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")
  const [sortId, setSortId] = useState("newest")
  const [query, setQuery] = useState("")

  useEffect(() => {
    if (!ready) return
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setErr("")
      try {
        const data = await listPublicReviewVideos()
        if (!cancelled) setItems(data)
      } catch (e) {
        if (!cancelled) setErr(e.response?.data?.detail || "加载失败")
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [ready])

  const newestId = useMemo(() => {
    if (!items.length) return null
    return sortVideos(items, "newest")[0]?.id ?? null
  }, [items])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    let list = items
    if (q) {
      list = items.filter((v) => {
        const title = (v.title || "").toLowerCase()
        const pub = (v.publisher_name || "").toLowerCase()
        const desc = (v.description || "").toLowerCase()
        return title.includes(q) || pub.includes(q) || desc.includes(q)
      })
    }
    return sortVideos(list, sortId)
  }, [items, sortId, query])

  const openVideo = (id) => navigateWithReturn(navigate, location, `/review/${id}`)

  return (
    <div className="rs-page">
      <VeloraShellBackground />
      <ReviewerNameGate
        open={!ready || askName}
        initialName={name}
        onConfirm={(n) => {
          setName(n)
          try {
            localStorage.setItem(REVIEWER_NAME_KEY, n)
          } catch {
            /* ignore */
          }
        }}
      />

      <header className="rs-top">
        <Link to="/review" className="rs-brand-link">
          <img src="/velora-logo.png" alt="Velora" className="rs-logo" draggable={false} />
          <div className="rs-brand-text">
            <span className="velora-wordmark velora-wordmark--sm">Velora</span>
            <span className="rs-brand-sub">视频审阅</span>
          </div>
        </Link>
        <button type="button" className="rs-user" onClick={() => setName("", true)}>
          {name || "设置用户名"}
        </button>
      </header>
      <div className="rs-notice" role="note">
        <span className="rs-notice-dot" aria-hidden />
        <span>仅供公司内部审阅，请勿下载或外传</span>
      </div>

      <main className="rs-main">
        <div className="rs-section-head">
          <div>
            <h1 className="rs-section-title">待审阅</h1>
            <p className="rs-section-sub">
              默认按发布时间从新到旧；可切换评分 / 互动排序，或搜索标题与发布者
            </p>
          </div>
          {!loading && !err && (
            <div className="rs-section-count">{visible.length} / {items.length} 个视频</div>
          )}
        </div>

        {!loading && !err && items.length > 0 && (
          <div className="rs-toolbar">
            <div className="rs-sort" role="tablist" aria-label="排序">
              {SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  role="tab"
                  aria-selected={sortId === opt.id}
                  className={`rs-sort-btn${sortId === opt.id ? " rs-sort-btn--on" : ""}`}
                  onClick={() => setSortId(opt.id)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <input
              className="rs-search"
              type="search"
              placeholder="搜索标题 / 发布者…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        )}

        {loading && <div className="rs-empty">加载中…</div>}
        {!loading && err && <div className="rs-empty">{err}</div>}
        {!loading && !err && items.length === 0 && (
          <div className="rs-empty">暂无待审阅视频</div>
        )}
        {!loading && !err && items.length > 0 && visible.length === 0 && (
          <div className="rs-empty">没有匹配的视频</div>
        )}
        {!loading && !err && visible.length > 0 && (
          <div className="rs-grid">
            {visible.map((v) => (
              <VideoCard
                key={v.id}
                video={v}
                onOpen={openVideo}
                isNewest={v.id === newestId}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
