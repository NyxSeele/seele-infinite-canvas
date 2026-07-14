import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { message } from "antd"
import { useCanvasStore } from "../stores"
import WorkspaceTopbar from "../components/workspace/WorkspaceTopbar"
import {
  importReviewVideoFromUrl,
  listMyReviewVideos,
  presignReviewVideoUpload,
  publishReviewVideo,
  unpublishReviewVideo,
  uploadReviewThumbnail,
} from "../services/reviewApi"
import { uploadToPresignedUrl } from "../services/teamFilesApi"
import GenHistoryVideoPicker from "../components/review/GenHistoryVideoPicker"
import { goBackOr, navigateWithReturn } from "../utils/navReturn"
import "./Workspace.css"
import "./ReviewPublish.css"

function formatBytes(n) {
  const v = Number(n) || 0
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`
  if (v < 1024 * 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(1)} MB`
  return `${(v / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatTime(iso) {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleString("zh-CN")
  } catch {
    return iso
  }
}

export default function ReviewPublish() {
  const navigate = useNavigate()
  const location = useLocation()
  const theme = useCanvasStore((s) => s.theme)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [formOpen, setFormOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [videoSource, setVideoSource] = useState("upload") // upload | url | history
  const [videoUrl, setVideoUrl] = useState("")
  const [videoFileName, setVideoFileName] = useState("")
  const [historySelectedId, setHistorySelectedId] = useState(null)
  const [thumbnailUrl, setThumbnailUrl] = useState("")
  const [uploadingThumb, setUploadingThumb] = useState(false)
  const [uploadingVideo, setUploadingVideo] = useState(false)
  const [videoProgress, setVideoProgress] = useState(0)
  const [saving, setSaving] = useState(false)
  const thumbInputRef = useRef(null)
  const videoInputRef = useRef(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setItems(await listMyReviewVideos())
    } catch (err) {
      message.error(err.response?.data?.detail || "加载失败")
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const resetForm = () => {
    setTitle("")
    setDescription("")
    setVideoSource("upload")
    setVideoUrl("")
    setVideoFileName("")
    setHistorySelectedId(null)
    setThumbnailUrl("")
    setVideoProgress(0)
  }

  const onThumbChange = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    if (!file.type.startsWith("image/")) {
      message.warning("请选择图片作为封面")
      return
    }
    setUploadingThumb(true)
    try {
      const uploaded = await uploadReviewThumbnail(file)
      setThumbnailUrl(uploaded.public_url)
      message.success("封面已上传")
    } catch (err) {
      message.error(err.response?.data?.detail || err.message || "封面上传失败")
    } finally {
      setUploadingThumb(false)
    }
  }

  const onVideoFileChange = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    if (!file.type.startsWith("video/") && !/\.(mp4|webm|mov|mkv|avi|m4v)$/i.test(file.name)) {
      message.warning("请选择视频文件")
      return
    }
    setUploadingVideo(true)
    setVideoProgress(0)
    setVideoFileName(file.name)
    try {
      const contentType = file.type || "video/mp4"
      const presign = await presignReviewVideoUpload({
        filename: file.name,
        content_type: contentType,
        size_bytes: file.size,
      })
      await uploadToPresignedUrl(
        presign.upload_url,
        file,
        presign.content_type || contentType,
        setVideoProgress,
      )
      setVideoUrl(presign.public_url)
      message.success("视频已上传")
    } catch (err) {
      setVideoUrl("")
      setVideoFileName("")
      message.error(err.response?.data?.detail || err.message || "视频上传失败")
    } finally {
      setUploadingVideo(false)
    }
  }

  const onHistorySelect = async (item) => {
    if (!item?.mediaUrl || uploadingVideo) return
    setHistorySelectedId(item.id)
    setUploadingVideo(true)
    setVideoProgress(0)
    setVideoFileName(item.title || item.prompt || "生成历史视频")
    try {
      const imported = await importReviewVideoFromUrl(item.mediaUrl)
      setVideoUrl(imported.public_url)
      setVideoProgress(100)
      message.success(imported.rehosted ? "已转存到 R2，可发布" : "已选用该视频")
      if (!title.trim() && (item.title || item.prompt)) {
        setTitle(String(item.title || item.prompt).slice(0, 200))
      }
    } catch (err) {
      setVideoUrl("")
      setHistorySelectedId(null)
      setVideoFileName("")
      message.error(err.response?.data?.detail || err.message || "选用失败")
    } finally {
      setUploadingVideo(false)
    }
  }

  const handlePublish = async () => {
    if (!title.trim()) {
      message.warning("请填写标题")
      return
    }
    if (!videoUrl.trim().startsWith("http")) {
      const tip =
        videoSource === "upload"
          ? "请先上传本地视频"
          : videoSource === "history"
            ? "请先从生成历史选择视频"
            : "请粘贴可公开访问的 http(s) 视频链接"
      message.warning(tip)
      return
    }
    setSaving(true)
    try {
      await publishReviewVideo({
        title: title.trim(),
        description: description.trim() || null,
        video_url: videoUrl.trim(),
        thumbnail_url: thumbnailUrl.trim() || null,
      })
      message.success("已发布")
      setFormOpen(false)
      resetForm()
      await refresh()
    } catch (err) {
      const detail = err.response?.data?.detail
      message.error(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg).join("; ")
            : "发布失败",
      )
    } finally {
      setSaving(false)
    }
  }

  const handleUnpublish = async (item) => {
    if (!window.confirm(`确认撤回「${item.title}」？公开页将不再展示；若视频存于本站 R2，将一并删除以释放空间。`)) return
    try {
      const res = await unpublishReviewVideo(item.id)
      const deleted = res?.r2_deleted?.length
      message.success(deleted ? "已撤回，并已从 R2 删除文件" : "已撤回")
      await refresh()
    } catch (err) {
      message.error(err.response?.data?.detail || "撤回失败")
    }
  }

  const busy = saving || uploadingVideo || uploadingThumb

  return (
    <div className={`ws-page ws-page--scroll rf-page--${theme}`}>
      <WorkspaceTopbar
        onBack={() => goBackOr(navigate, location, "/workspace")}
        title="视频审阅 · 我的发布"
      />
      <div className="rp-body">
        <div className="rp-toolbar">
          <button
            type="button"
            className="rp-btn rp-btn--primary"
            onClick={() => {
              resetForm()
              setFormOpen(true)
            }}
          >
            发布新视频
          </button>
          <button
            type="button"
            className="rp-link"
            onClick={() => navigateWithReturn(navigate, location, "/review")}
          >
            打开公开展示页
          </button>
        </div>

        {loading ? (
          <div className="rp-empty">加载中…</div>
        ) : items.length === 0 ? (
          <div className="rp-empty">暂无发布，点击上方发布新视频</div>
        ) : (
          <div className="rp-list">
            {items.map((v) => (
              <article key={v.id} className={`rp-card${!v.is_active ? " rp-card--off" : ""}`}>
                <div className="rp-thumb">
                  {v.thumbnail_url ? (
                    <img src={v.thumbnail_url} alt="" onError={(e) => { e.currentTarget.style.display = "none" }} />
                  ) : (
                    <span>无封面</span>
                  )}
                </div>
                <div className="rp-main">
                  <div className="rp-title">
                    {v.title}
                    {!v.is_active && <span className="rp-badge">已下架</span>}
                  </div>
                  <div className="rp-meta">{formatTime(v.published_at)}</div>
                  <div className="rp-stats">
                    均分 {v.avg_rating ?? "—"} · 赞 {v.like_count} · 踩 {v.dislike_count} · 评 {v.comment_count}
                  </div>
                  <div className="rp-url" title={v.video_url}>{v.video_url}</div>
                </div>
                <div className="rp-actions">
                  {v.is_active && (
                    <button type="button" className="rp-btn rp-btn--danger" onClick={() => handleUnpublish(v)}>
                      撤回发布
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      {formOpen && (
        <div className="rp-modal-overlay" onClick={() => !busy && setFormOpen(false)}>
          <div className="rp-modal" onClick={(e) => e.stopPropagation()}>
            <h3>发布视频</h3>
            <label className="rp-field">
              <span>标题</span>
              <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
            </label>
            <label className="rp-field">
              <span>描述（可选）</span>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
            </label>

            <div className="rp-field">
              <span>视频来源</span>
              <div className="rp-source-tabs">
                <button
                  type="button"
                  className={`rp-source-tab${videoSource === "upload" ? " rp-source-tab--active" : ""}`}
                  disabled={uploadingVideo}
                  onClick={() => setVideoSource("upload")}
                >
                  本地上传
                </button>
                <button
                  type="button"
                  className={`rp-source-tab${videoSource === "history" ? " rp-source-tab--active" : ""}`}
                  disabled={uploadingVideo}
                  onClick={() => setVideoSource("history")}
                >
                  生成历史
                </button>
                <button
                  type="button"
                  className={`rp-source-tab${videoSource === "url" ? " rp-source-tab--active" : ""}`}
                  disabled={uploadingVideo}
                  onClick={() => setVideoSource("url")}
                >
                  粘贴 URL
                </button>
              </div>
            </div>

            {videoSource === "upload" ? (
              <div className="rp-field">
                <span>本地视频文件</span>
                <div className="rp-thumb-row">
                  <button
                    type="button"
                    className="rp-btn"
                    disabled={uploadingVideo}
                    onClick={() => videoInputRef.current?.click()}
                  >
                    {uploadingVideo ? `上传中 ${videoProgress}%` : "选择视频"}
                  </button>
                  <input
                    ref={videoInputRef}
                    type="file"
                    accept="video/*,.mp4,.webm,.mov,.mkv,.avi,.m4v"
                    hidden
                    onChange={onVideoFileChange}
                  />
                  {videoFileName && (
                    <span className="rp-thumb-ok" title={videoUrl}>
                      {videoFileName}
                      {videoUrl ? " · 已就绪" : ""}
                    </span>
                  )}
                </div>
                {uploadingVideo && (
                  <div className="rp-progress">
                    <div className="rp-progress-track">
                      <div className="rp-progress-bar" style={{ width: `${videoProgress}%` }} />
                    </div>
                    <span>{videoProgress}%</span>
                  </div>
                )}
                <p className="rp-hint">浏览器直传 R2；进度即上传到对象存储。</p>
              </div>
            ) : videoSource === "history" ? (
              <div className="rp-field">
                <span>从生成历史选择</span>
                <GenHistoryVideoPicker
                  selectedId={historySelectedId}
                  onSelect={onHistorySelect}
                  disabled={uploadingVideo}
                />
                {uploadingVideo && (
                  <p className="rp-hint">正在转存到公开地址，请稍候…</p>
                )}
                {videoUrl && !uploadingVideo && (
                  <span className="rp-thumb-ok" title={videoUrl}>
                    已就绪 · {videoFileName || "视频"}
                  </span>
                )}
                <p className="rp-hint">私有生成结果会自动转存到 R2，供公开审阅页匿名播放。</p>
              </div>
            ) : (
              <label className="rp-field">
                <span>视频 URL（公开 http/https）</span>
                <input
                  value={videoUrl}
                  onChange={(e) => {
                    setVideoUrl(e.target.value)
                    setVideoFileName("")
                    setHistorySelectedId(null)
                  }}
                  placeholder="https://…"
                />
              </label>
            )}

            <div className="rp-field">
              <span>封面图（可选）</span>
              <div className="rp-thumb-row">
                <button
                  type="button"
                  className="rp-btn"
                  disabled={uploadingThumb}
                  onClick={() => thumbInputRef.current?.click()}
                >
                  {uploadingThumb ? "上传中…" : "上传封面"}
                </button>
                <input ref={thumbInputRef} type="file" accept="image/*" hidden onChange={onThumbChange} />
                {thumbnailUrl && <span className="rp-thumb-ok">已选封面</span>}
              </div>
            </div>
            <div className="rp-modal-footer">
              <button type="button" className="rp-btn" disabled={busy} onClick={() => setFormOpen(false)}>
                取消
              </button>
              <button
                type="button"
                className="rp-btn rp-btn--primary"
                disabled={busy || uploadingVideo}
                onClick={handlePublish}
              >
                {saving ? "发布中…" : "发布"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
