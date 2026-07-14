import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { message } from "antd"
import api, { API_BASE } from "../../services/api"
import {
  downloadAdminFile,
  getAdminFileStats,
  listAdminFiles,
} from "../../services/adminFilesApi"
import { appendMediaTicket, refreshMediaTicket, stripMediaTicket } from "../../utils/mediaTicket"
import "./UserFiles.css"

const PAGE_SIZE = 48

const SOURCE_OPTIONS = [
  { value: "", label: "全部来源" },
  { value: "generation", label: "AI 生成" },
  { value: "upload", label: "本地上传" },
  { value: "r2", label: "团队文件" },
  { value: "asset", label: "资产库" },
  { value: "export", label: "剧本导出" },
]

const CATEGORY_OPTIONS = [
  { value: "all", label: "全部类型" },
  { value: "image", label: "图片" },
  { value: "video", label: "视频" },
  { value: "audio", label: "音频" },
  { value: "document", label: "文档" },
  { value: "other", label: "其他" },
]

const SOURCE_LABEL = {
  upload: "本地上传",
  r2: "团队文件",
  generation: "AI 生成",
  asset: "资产库",
  export: "剧本导出",
}

const CATEGORY_LABEL = {
  image: "图片",
  video: "视频",
  audio: "音频",
  document: "文档",
  other: "其他",
}

function formatDate(iso) {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleString("zh-CN")
  } catch {
    return iso
  }
}

function formatBytes(n) {
  const v = Number(n) || 0
  if (!v) return "—"
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`
  if (v < 1024 * 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(1)} MB`
  return `${(v / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function mediaUrl(raw) {
  if (!raw) return ""
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    if (!raw.includes("/api/view") && !raw.includes("/api/uploads") && !raw.includes("/api/admin/")) {
      return raw
    }
  }
  const stripped = stripMediaTicket(raw)
  const relative = stripped.startsWith("/") ? stripped : `/${stripped}`
  const base = API_BASE || ""
  const target = base ? `${base}${relative}` : relative
  if (
    target.includes("/api/view") ||
    target.includes("/api/uploads") ||
    target.includes("/api/admin/files/")
  ) {
    return appendMediaTicket(target)
  }
  return target
}

function previewUrl(file) {
  return mediaUrl(file?.preview_url || file?.url)
}

function thumbnailUrl(file) {
  if ((file?.category || "") === "video") {
    return mediaUrl(file?.thumbnail_url || file?.preview_url || file?.url)
  }
  return previewUrl(file)
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename || "download"
  a.click()
  URL.revokeObjectURL(url)
}

function FilePreview({ file }) {
  const [broken, setBroken] = useState(false)
  const cat = file.category || "other"
  const url = cat === "video" ? thumbnailUrl(file) : previewUrl(file)

  if (!broken && url && cat === "image") {
    return (
      <img
        className="user-files-card__media"
        src={url}
        alt=""
        loading="lazy"
        onError={() => setBroken(true)}
      />
    )
  }

  if (!broken && url && cat === "video") {
    return (
      <div className="user-files-card__video-thumb">
        <img
          className="user-files-card__media"
          src={url}
          alt=""
          loading="lazy"
          onError={() => setBroken(true)}
        />
        <span className="user-files-card__play" aria-hidden>
          ▶
        </span>
      </div>
    )
  }

  if (cat === "video") {
    return (
      <div className="user-files-card__fallback user-files-card__fallback--video">
        <span className="user-files-card__play user-files-card__play--lg" aria-hidden>
          ▶
        </span>
        <span>{CATEGORY_LABEL.video}</span>
      </div>
    )
  }

  return (
    <div className="user-files-card__fallback">
      <span>{CATEGORY_LABEL[cat] || "文件"}</span>
      <span>{SOURCE_LABEL[file.source] || file.source}</span>
    </div>
  )
}

function PreviewModal({
  file,
  previewSrc,
  onClose,
  onDownload,
  downloading,
  loading,
  onMediaReady,
  onMediaError,
}) {
  if (!file) return null
  const cat = file.category || "other"

  return (
    <div className="user-files-preview-modal" onClick={onClose} role="presentation">
      <div
        className="user-files-preview-modal__inner"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="user-files-preview-modal__header">
          <div className="user-files-preview-modal__title" title={file.filename}>
            {file.filename}
          </div>
          <div className="user-files-preview-modal__actions">
            <button
              type="button"
              className="adm-btn"
              disabled={downloading}
              onClick={() => onDownload(file)}
            >
              {downloading ? "下载中…" : "下载"}
            </button>
            <button type="button" className="adm-btn" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
        <div className="user-files-preview-modal__content">
          {loading && (
            <div className="user-files-preview-modal__loading">正在缓冲视频…</div>
          )}
          {cat === "image" && previewSrc ? (
            <img
              className="user-files-preview-modal__media"
              src={previewSrc}
              alt={file.filename}
              onLoad={onMediaReady}
              onError={onMediaError}
            />
          ) : cat === "video" && previewSrc ? (
            <video
              className="user-files-preview-modal__media"
              src={previewSrc}
              controls
              playsInline
              autoPlay
              preload="auto"
              onCanPlay={onMediaReady}
              onError={onMediaError}
            />
          ) : cat === "audio" && previewSrc ? (
            <audio
              className="user-files-preview-modal__media"
              src={previewSrc}
              controls
              autoPlay
              preload="auto"
              onCanPlay={onMediaReady}
              onError={onMediaError}
            />
          ) : !loading ? (
            <div className="user-files-card__fallback">
              <p>{file.description || "无法内嵌预览此文件类型"}</p>
              <button
                type="button"
                className="adm-btn"
                disabled={downloading}
                onClick={() => onDownload(file)}
              >
                下载文件
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default function UserFiles() {
  const [stats, setStats] = useState(null)
  const [files, setFiles] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [sourceFilter, setSourceFilter] = useState("")
  const [categoryFilter, setCategoryFilter] = useState("all")
  const [searchInput, setSearchInput] = useState("")
  const [search, setSearch] = useState("")
  const [previewFile, setPreviewFile] = useState(null)
  const [previewSrc, setPreviewSrc] = useState("")
  const [previewLoading, setPreviewLoading] = useState(false)
  const [downloadingId, setDownloadingId] = useState("")
  const listRequestRef = useRef(0)
  const previewFileIdRef = useRef("")

  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [searchInput])

  const loadStats = useCallback(async () => {
    try {
      const data = await getAdminFileStats()
      setStats(data)
    } catch (e) {
      console.error("加载文件统计失败", e)
    }
  }, [])

  const loadFiles = useCallback(async () => {
    const requestId = ++listRequestRef.current
    setLoading(true)
    try {
      await refreshMediaTicket(api).catch(() => {})
      const data = await listAdminFiles({
        page,
        page_size: PAGE_SIZE,
        source: sourceFilter || undefined,
        category: categoryFilter === "all" ? undefined : categoryFilter,
        q: search || undefined,
      })
      if (requestId !== listRequestRef.current) return
      setFiles(data.items || [])
      setTotal(data.total || 0)
    } catch (e) {
      if (requestId !== listRequestRef.current) return
      console.error("加载文件列表失败", e)
      message.error(e.response?.data?.detail || "加载文件列表失败")
      setFiles([])
      setTotal(0)
    } finally {
      if (requestId === listRequestRef.current) {
        setLoading(false)
      }
    }
  }, [page, sourceFilter, categoryFilter, search])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  useEffect(() => {
    loadFiles()
  }, [loadFiles])

  const handleSourceFilterChange = (value) => {
    setSourceFilter(value)
    setPage(1)
  }

  const handleCategoryFilterChange = (value) => {
    setCategoryFilter(value)
    setPage(1)
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const statCards = useMemo(() => {
    if (!stats) return []
    const by = stats.by_source || {}
    return [
      { label: "全部文件", value: stats.total, sub: null },
      { label: "AI 生成", value: by.generation || 0, sub: null },
      { label: "本地上传", value: by.upload || 0, sub: formatBytes(stats.storage_bytes?.upload) },
      { label: "团队文件", value: by.r2 || 0, sub: formatBytes(stats.storage_bytes?.r2) },
      { label: "资产库", value: by.asset || 0, sub: null },
      { label: "剧本导出", value: by.export || 0, sub: null },
    ]
  }, [stats])

  const handleDownload = async (file) => {
    if (!file?.id || downloadingId) return
    setDownloadingId(file.id)
    try {
      const blob = await downloadAdminFile(file)
      triggerBlobDownload(blob, file.filename || "download")
      message.success("开始下载")
    } catch (e) {
      console.error("下载失败", e)
      message.error(e.response?.data?.detail || e.message || "下载失败")
    } finally {
      setDownloadingId("")
    }
  }

  const openFile = (file) => {
    const cat = file.category || "other"
    if (cat !== "image" && cat !== "video" && cat !== "audio") {
      handleDownload(file)
      return
    }

    const url = previewUrl(file)
    if (!url) {
      message.error("无法生成预览地址")
      return
    }

    previewFileIdRef.current = file.id
    setPreviewFile(file)
    setPreviewSrc(url)
    setPreviewLoading(cat === "video" || cat === "audio")

    refreshMediaTicket(api)
      .then(() => {
        if (previewFileIdRef.current === file.id) {
          setPreviewSrc(previewUrl(file))
        }
      })
      .catch(() => {})
  }

  const handlePreviewMediaReady = () => {
    setPreviewLoading(false)
  }

  const handlePreviewMediaError = async () => {
    try {
      await refreshMediaTicket(api)
      if (previewFile) {
        setPreviewSrc(previewUrl(previewFile))
      }
    } catch {
      setPreviewLoading(false)
      message.error("预览加载失败，请尝试下载")
    }
  }

  const closePreview = () => {
    previewFileIdRef.current = ""
    setPreviewFile(null)
    setPreviewSrc("")
    setPreviewLoading(false)
  }

  return (
    <div>
      <div className="adm-page-header feedback-page__header">
        <h2 className="adm-page-title" style={{ marginBottom: 0 }}>
          用户文件
        </h2>
        <button type="button" className="adm-btn" onClick={() => { loadStats(); loadFiles() }}>
          刷新
        </button>
      </div>

      {statCards.length > 0 && (
        <div className="user-files-stats">
          {statCards.map((card) => (
            <div key={card.label} className="user-files-stat">
              <div className="user-files-stat__label">{card.label}</div>
              <div className="user-files-stat__value">{card.value}</div>
              {card.sub && card.sub !== "—" && (
                <div className="user-files-stat__sub">{card.sub}</div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="user-files-filter-bar">
        <select value={sourceFilter} onChange={(e) => handleSourceFilterChange(e.target.value)}>
          {SOURCE_OPTIONS.map((opt) => (
            <option key={opt.value || "all"} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select value={categoryFilter} onChange={(e) => handleCategoryFilterChange(e.target.value)}>
          {CATEGORY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <input
          type="search"
          placeholder="搜索文件名或提示词…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          style={{ minWidth: 200, flex: 1 }}
        />
      </div>

      {loading ? (
        <div className="adm-empty">加载中…</div>
      ) : files.length === 0 ? (
        <div className="adm-empty">暂无文件</div>
      ) : (
        <div className="user-files-grid">
          {files.map((file) => (
            <article key={file.id} className="user-files-card">
              <button
                type="button"
                className="user-files-card__preview"
                onClick={() => openFile(file)}
                style={{ border: "none", padding: 0, cursor: "pointer", width: "100%" }}
              >
                <FilePreview file={file} />
              </button>
              <div className="user-files-card__body">
                <div className="user-files-card__name" title={file.filename}>
                  {file.filename}
                </div>
                <div className="user-files-card__meta">
                  <span className="user-files-source-badge">
                    {SOURCE_LABEL[file.source] || file.source}
                  </span>
                  <span>{file.username || "—"}</span>
                  <span>{formatDate(file.created_at)}</span>
                </div>
                {file.description && (
                  <div
                    className="user-files-card__meta"
                    title={file.description}
                    style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  >
                    {file.description}
                  </div>
                )}
                <div className="user-files-card__actions">
                  <button type="button" className="adm-btn adm-btn--sm" onClick={() => openFile(file)}>
                    预览
                  </button>
                  <button
                    type="button"
                    className="adm-btn adm-btn--sm"
                    disabled={downloadingId === file.id}
                    onClick={() => handleDownload(file)}
                  >
                    {downloadingId === file.id ? "下载中…" : "下载"}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="user-files-pagination">
          <button
            type="button"
            className="adm-btn"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            上一页
          </button>
          <span>
            第 {page} / {totalPages} 页，共 {total} 条
          </span>
          <button
            type="button"
            className="adm-btn"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </button>
        </div>
      )}

      <PreviewModal
        file={previewFile}
        previewSrc={previewSrc}
        onClose={closePreview}
        onDownload={handleDownload}
        downloading={!!previewFile && downloadingId === previewFile.id}
        loading={previewLoading}
        onMediaReady={handlePreviewMediaReady}
        onMediaError={handlePreviewMediaError}
      />
    </div>
  )
}
