import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate, useParams, useLocation } from "react-router-dom"
import {
  getPublicReviewVideo,
  postPublicReviewComment,
} from "../services/reviewPublicApi"
import {
  REVIEWER_NAME_KEY,
  ReviewerNameGate,
  useReviewerName,
} from "../components/review/ReviewerNameGate"
import VeloraShellBackground from "../components/common/VeloraShellBackground"
import { goBackOr } from "../utils/navReturn"
import { encodePublicMediaUrl } from "../utils/encodePublicMediaUrl"
import "../styles/velora-brand.css"
import "./ReviewSite.css"

function formatTime(iso) {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleString("zh-CN")
  } catch {
    return iso
  }
}

export default function ReviewDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { name, setName, ready, askName } = useReviewerName()
  const [video, setVideo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")
  const [rating, setRating] = useState(5)
  const [liked, setLiked] = useState(null)
  const [comment, setComment] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [submitMsg, setSubmitMsg] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const data = await getPublicReviewVideo(id)
      setVideo(data)
    } catch (e) {
      setErr(e.response?.data?.detail || "加载失败")
      setVideo(null)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    if (!ready) return
    load()
  }, [ready, load])

  const handleSubmit = async () => {
    if (!name.trim()) {
      setName("", true)
      return
    }
    setSubmitting(true)
    setSubmitMsg("")
    try {
      await postPublicReviewComment(id, {
        reviewer_name: name.trim(),
        rating,
        liked,
        comment: comment.trim() || null,
      })
      setSubmitMsg("评价已提交")
      setComment("")
      await load()
    } catch (e) {
      setSubmitMsg(e.response?.data?.detail || "提交失败")
    } finally {
      setSubmitting(false)
    }
  }

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
        <div className="rs-top-left">
          <button
            type="button"
            className="rs-back"
            onClick={() => goBackOr(navigate, location, "/review")}
          >
            返回
          </button>
          <Link to="/review" className="rs-brand-link rs-brand-link--compact">
            <img src="/velora-logo.png" alt="Velora" className="rs-logo rs-logo--sm" draggable={false} />
            <span className="velora-wordmark velora-wordmark--sm">Velora</span>
          </Link>
        </div>
        <button type="button" className="rs-user" onClick={() => setName("", true)}>
          {name || "设置用户名"}
        </button>
      </header>
      <div className="rs-notice" role="note">
        <span className="rs-notice-dot" aria-hidden />
        <span>仅供公司内部审阅，请勿下载或外传</span>
      </div>

      <main className="rs-main rs-main--detail">
        {loading && <div className="rs-empty">加载中…</div>}
        {!loading && err && <div className="rs-empty">{err}</div>}
        {!loading && video && (
          <>
            <div
              className="rs-player-wrap"
              onContextMenu={(e) => e.preventDefault()}
            >
              <video
                className="rs-player"
                src={encodePublicMediaUrl(video.video_url)}
                poster={
                  video.thumbnail_url
                    ? encodePublicMediaUrl(video.thumbnail_url)
                    : undefined
                }
                controls
                controlsList="nodownload noplaybackrate noremoteplayback"
                disablePictureInPicture
                disableRemotePlayback
                playsInline
                preload="metadata"
                onContextMenu={(e) => e.preventDefault()}
                onDragStart={(e) => e.preventDefault()}
              />
            </div>
            <h2 className="rs-detail-title">{video.title}</h2>
            <div className="rs-detail-meta">
              发布者 {video.publisher_name} · {formatTime(video.published_at)} · ★{" "}
              {video.avg_rating != null ? Number(video.avg_rating).toFixed(1) : "—"} · 赞{" "}
              {video.like_count} · 踩 {video.dislike_count}
            </div>
            {video.description && <p className="rs-desc">{video.description}</p>}

            <section className="rs-form">
              <h3>写下评价</h3>
              <div className="rs-stars">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={`rs-star${rating >= n ? " rs-star--on" : ""}`}
                    onClick={() => setRating(n)}
                  >
                    ★
                  </button>
                ))}
                <span className="rs-star-label">{rating} 星</span>
              </div>
              <div className="rs-vote">
                <button
                  type="button"
                  className={`rs-vote-btn${liked === true ? " rs-vote-btn--on" : ""}`}
                  onClick={() => setLiked(liked === true ? null : true)}
                >
                  赞
                </button>
                <button
                  type="button"
                  className={`rs-vote-btn${liked === false ? " rs-vote-btn--on" : ""}`}
                  onClick={() => setLiked(liked === false ? null : false)}
                >
                  踩
                </button>
              </div>
              <textarea
                className="rs-comment-input"
                rows={3}
                placeholder="文字评论（可选）"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <button
                type="button"
                className="rs-submit"
                disabled={submitting}
                onClick={handleSubmit}
              >
                {submitting ? "提交中…" : "提交评价"}
              </button>
              {submitMsg && <div className="rs-submit-msg">{submitMsg}</div>}
            </section>

            <section className="rs-comments">
              <h3>评论（{video.comments?.length || 0}）</h3>
              {(video.comments || []).length === 0 && (
                <div className="rs-empty">暂无评论</div>
              )}
              {(video.comments || []).map((c) => (
                <article key={c.id} className="rs-comment">
                  <div className="rs-comment-head">
                    <strong>{c.reviewer_name}</strong>
                    <span>★ {c.rating}</span>
                    <span>
                      {c.liked === true ? "赞" : c.liked === false ? "踩" : ""}
                    </span>
                    <span className="rs-comment-time">{formatTime(c.created_at)}</span>
                  </div>
                  {c.comment && <p className="rs-comment-body">{c.comment}</p>}
                </article>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  )
}
