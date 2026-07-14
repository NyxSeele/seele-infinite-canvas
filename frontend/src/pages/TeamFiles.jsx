import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { message } from "antd"
import { useAuth } from "../contexts/AuthContext"
import { useCanvasStore, useTeamStore } from "../stores"
import WorkspaceTopbar from "../components/workspace/WorkspaceTopbar"
import {
  addTeamFileToAssets,
  deleteTeamFile,
  getTeamFileDownloadUrl,
  listTeamFiles,
  presignTeamFileUpload,
  registerTeamFile,
  uploadToPresignedUrl,
} from "../services/teamFilesApi"
import { goBackOr } from "../utils/navReturn"
import "./Workspace.css"
import "./TeamFiles.css"

const CATEGORY_TABS = [
  { id: "all", label: "全部" },
  { id: "image", label: "图片" },
  { id: "video", label: "视频" },
  { id: "audio", label: "音频" },
  { id: "document", label: "文档" },
  { id: "other", label: "其他" },
]

const CATEGORY_LABEL = {
  image: "图片",
  video: "视频",
  audio: "音频",
  document: "文档",
  other: "其他",
}

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

function FilePreview({ file }) {
  const [broken, setBroken] = useState(false)
  const cat = file.category || "other"
  const url = file.public_url

  if (!broken && url && cat === "image") {
    return (
      <img
        className="tf-preview-media"
        src={url}
        alt=""
        loading="lazy"
        onError={() => setBroken(true)}
      />
    )
  }

  if (!broken && url && cat === "video") {
    return (
      <video
        className="tf-preview-media"
        src={url}
        muted
        playsInline
        preload="metadata"
        onError={() => setBroken(true)}
      />
    )
  }

  return (
    <div className={`tf-preview-fallback tf-preview-fallback--${cat}`}>
      <span>{CATEGORY_LABEL[cat] || "文件"}</span>
    </div>
  )
}

export default function TeamFiles() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuth()
  const theme = useCanvasStore((s) => s.theme)
  const activeTeamId = useTeamStore((s) => s.activeTeamId)

  const hasAccess = user?.role === "admin" || user?.r2_access === true
  const isAdmin = user?.role === "admin"

  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchInput, setSearchInput] = useState("")
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("all")
  const [uploadOpen, setUploadOpen] = useState(false)
  const [pendingFile, setPendingFile] = useState(null)
  const [description, setDescription] = useState("")
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [assetTarget, setAssetTarget] = useState(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 300)
    return () => clearTimeout(t)
  }, [searchInput])

  const refresh = useCallback(async () => {
    if (!hasAccess) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await listTeamFiles({ q: search || undefined })
      setFiles(data.items || [])
    } catch (err) {
      console.error(err)
      message.error(err.response?.data?.detail || "加载文件列表失败")
      setFiles([])
    } finally {
      setLoading(false)
    }
  }, [hasAccess, search])

  useEffect(() => {
    refresh()
  }, [refresh])

  const filtered = useMemo(() => {
    if (category === "all") return files
    return files.filter((f) => (f.category || "other") === category)
  }, [files, category])

  const categoryCounts = useMemo(() => {
    const counts = { all: files.length }
    for (const tab of CATEGORY_TABS) {
      if (tab.id === "all") continue
      counts[tab.id] = files.filter((f) => (f.category || "other") === tab.id).length
    }
    return counts
  }, [files])

  const onPickFile = (e) => {
    const f = e.target.files?.[0]
    e.target.value = ""
    if (!f) return
    setPendingFile(f)
    setDescription("")
    setProgress(0)
    setUploadOpen(true)
  }

  const startUpload = async () => {
    if (!pendingFile || uploading) return
    setUploading(true)
    setProgress(0)
    try {
      const contentType = pendingFile.type || "application/octet-stream"
      const presign = await presignTeamFileUpload({
        filename: pendingFile.name,
        content_type: contentType,
        size_bytes: pendingFile.size,
        description: description.trim() || null,
      })
      await uploadToPresignedUrl(
        presign.upload_url,
        pendingFile,
        presign.content_type || contentType,
        setProgress,
      )
      await registerTeamFile({
        key: presign.key,
        filename: pendingFile.name,
        content_type: contentType,
        size_bytes: pendingFile.size,
        description: description.trim() || null,
      })
      message.success("上传成功")
      setUploadOpen(false)
      setPendingFile(null)
      await refresh()
    } catch (err) {
      console.error(err)
      message.error(err.response?.data?.detail || err.message || "上传失败")
    } finally {
      setUploading(false)
    }
  }

  const handleDownload = async (file) => {
    try {
      const data = await getTeamFileDownloadUrl(file.id)
      window.open(data.download_url, "_blank", "noopener,noreferrer")
    } catch (err) {
      message.error(err.response?.data?.detail || "获取下载链接失败")
    }
  }

  const handleDelete = async (file) => {
    if (!window.confirm(`确认删除「${file.filename}」？`)) return
    try {
      await deleteTeamFile(file.id)
      message.success("已删除")
      await refresh()
    } catch (err) {
      message.error(err.response?.data?.detail || "删除失败")
    }
  }

  const handleAddToAssets = async (file, target) => {
    try {
      const payload = { target }
      if (target === "team") {
        if (!activeTeamId) {
          message.warning("请先选择一个团队")
          return
        }
        payload.team_id = activeTeamId
      }
      await addTeamFileToAssets(file.id, payload)
      message.success(target === "team" ? "已添加到团队资产库" : "已添加到个人资产库")
      setAssetTarget(null)
    } catch (err) {
      message.error(err.response?.data?.detail || "添加到资产库失败")
    }
  }

  const emptyHint = useMemo(() => {
    if (loading) return "加载中…"
    if (!files.length) return search ? "无匹配文件" : "暂无文件，点击上方上传"
    if (!filtered.length) return "该分类下暂无文件"
    return null
  }, [loading, files.length, filtered.length, search])

  return (
    <div className={`ws-page ws-page--scroll rf-page--${theme}`}>
      <WorkspaceTopbar
        onBack={() => goBackOr(navigate, location, "/workspace")}
        title="团队文件空间"
      />

      <div className="tf-body">
        {!hasAccess ? (
          <div className="tf-denied">暂无访问权限，请联系管理员</div>
        ) : (
          <>
            <div className="tf-toolbar">
              <button
                type="button"
                className="tf-btn tf-btn--primary"
                onClick={() => fileInputRef.current?.click()}
              >
                上传文件
              </button>
              <input
                ref={fileInputRef}
                type="file"
                hidden
                onChange={onPickFile}
              />
              <input
                className="tf-search"
                type="search"
                placeholder="搜索文件名…"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </div>

            <div className="tf-tabs" role="tablist">
              {CATEGORY_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={category === tab.id}
                  className={`tf-tab${category === tab.id ? " tf-tab--active" : ""}`}
                  onClick={() => setCategory(tab.id)}
                >
                  {tab.label}
                  <span className="tf-tab-count">{categoryCounts[tab.id] || 0}</span>
                </button>
              ))}
            </div>

            {emptyHint ? (
              <div className="tf-empty">{emptyHint}</div>
            ) : (
              <div className="tf-grid">
                {filtered.map((f) => (
                  <article key={f.id} className="tf-card">
                    <div className="tf-preview">
                      <FilePreview file={f} />
                      <span className={`tf-badge tf-badge--${f.category || "other"}`}>
                        {CATEGORY_LABEL[f.category] || "其他"}
                      </span>
                    </div>
                    <div className="tf-card-body">
                      <div className="tf-card-name" title={f.description || f.filename}>
                        {f.filename}
                      </div>
                      <div className="tf-card-meta">
                        {f.uploader_name} · {formatBytes(f.size_bytes)}
                      </div>
                      <div className="tf-card-meta">{formatTime(f.uploaded_at)}</div>
                      <div className="tf-card-actions">
                        <button type="button" className="tf-link" onClick={() => handleDownload(f)}>
                          下载
                        </button>
                        <button
                          type="button"
                          className="tf-link"
                          onClick={() => setAssetTarget(f)}
                        >
                          加资产库
                        </button>
                        {isAdmin && (
                          <button
                            type="button"
                            className="tf-link tf-link--danger"
                            onClick={() => handleDelete(f)}
                          >
                            删除
                          </button>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {uploadOpen && pendingFile && (
        <div className="tf-modal-overlay" onClick={() => !uploading && setUploadOpen(false)}>
          <div className="tf-modal" onClick={(e) => e.stopPropagation()}>
            <h3>上传文件</h3>
            <p className="tf-modal-meta">{pendingFile.name}（{formatBytes(pendingFile.size)}）</p>
            <label className="tf-field">
              <span>描述（可选）</span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                disabled={uploading}
                placeholder="给团队成员的说明…"
              />
            </label>
            {uploading && (
              <div className="tf-progress">
                <div className="tf-progress-track">
                  <div className="tf-progress-bar" style={{ width: `${progress}%` }} />
                </div>
                <span>{progress}%</span>
              </div>
            )}
            <div className="tf-modal-footer">
              <button
                type="button"
                className="tf-btn"
                disabled={uploading}
                onClick={() => setUploadOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="tf-btn tf-btn--primary"
                disabled={uploading}
                onClick={startUpload}
              >
                {uploading ? "上传中…" : "开始上传"}
              </button>
            </div>
          </div>
        </div>
      )}

      {assetTarget && (
        <div className="tf-modal-overlay" onClick={() => setAssetTarget(null)}>
          <div className="tf-modal" onClick={(e) => e.stopPropagation()}>
            <h3>添加到资产库</h3>
            <p className="tf-modal-meta">{assetTarget.filename}</p>
            <p className="tf-hint">视频/大文件会以链接形式写入资产库，后续支持预览。</p>
            <div className="tf-modal-footer">
              <button type="button" className="tf-btn" onClick={() => setAssetTarget(null)}>
                取消
              </button>
              <button
                type="button"
                className="tf-btn tf-btn--primary"
                onClick={() => handleAddToAssets(assetTarget, "personal")}
              >
                个人资产库
              </button>
              <button
                type="button"
                className="tf-btn tf-btn--primary"
                onClick={() => handleAddToAssets(assetTarget, "team")}
              >
                团队资产库
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
