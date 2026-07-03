import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { createPortal } from "react-dom"
import { getThemePortalRoot } from "./utils/themePortalRoot"
import api, { API_BASE } from "./services/api"
import { appendMediaTicket } from "./utils/mediaTicket"
import { wsManager } from "./services/ws"
import ModelSelectBanner from "./components/ModelSelectBanner.jsx"
import "./App.css"

const PAGE_TITLES = {
  submit: "图像生成",
  video: "视频生成",
  tasks: "任务管理",
}

const DEFAULT_STEPS = 20
const POLL_INTERVAL = 5000
const DEFAULT_UNWANTED = "模糊, 低质量, 水印, 文字"
const DEFAULT_VIDEO_UNWANTED =
  "worst quality, inconsistent motion, blurry, jittery, distorted"

const SIZE_OPTIONS = [
  { label: "方形 512×512", width: 512, height: 512 },
  { label: "竖屏 512×768（适合人像）", width: 512, height: 768 },
  { label: "横屏 768×512（适合风景）", width: 768, height: 512 },
]

const VIDEO_SIZE_OPTIONS = [
  { label: "480P 竖屏 (480×848)", width: 480, height: 848 },
  { label: "480P 横屏 (848×480)", width: 848, height: 480 },
  { label: "480P 方形 (480×480)", width: 480, height: 480 },
  { label: "720P 横屏 (1280×720)", width: 1280, height: 720, warnVram: true },
]

const STYLE_OPTIONS = [
  { value: "realistic", label: "写实风格" },
  { value: "anime", label: "动漫风格" },
  { value: "oil", label: "油画风格" },
]

function mediaFilename(file) {
  if (!file) return ""
  return typeof file === "string" ? file : file.filename || ""
}

function mediaUrl(file) {
  if (!file) return ""
  const filename = mediaFilename(file)
  const type = typeof file === "string" ? "output" : file.type || "output"
  const subfolder = typeof file === "string" ? "" : file.subfolder || ""
  const params = new URLSearchParams({ filename, type })
  if (subfolder) params.set("subfolder", subfolder)
  return appendMediaTicket(`${API_BASE}/api/view?${params}`)
}

function isVideoFilename(filename) {
  return /\.(mp4|webm|mov|mkv|avi)(\?|$)/i.test(filename || "")
}

function isVideoMediaUrl(url) {
  return isVideoFilename(url)
}

function taskIsPlayableVideo(task) {
  if (task?.result_media_type === "video") return true
  const videoName = mediaFilename(task?.videos?.[0])
  if (videoName && isVideoFilename(videoName)) return true
  if (task?.is_video && task?.videos?.length > 0) return true
  return task?.task_type === "video" && isVideoFilename(videoName)
}

function downloadFilename(task, cover) {
  const name = mediaFilename(cover)
  if (name) return name
  return taskIsPlayableVideo(task) ? "Velora_video.mp4" : "Velora_image.png"
}

function formatTimestamp(ts) {
  if (ts == null) return "—"
  const ms = ts < 1e12 ? ts * 1000 : ts
  return new Date(ms).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

function formatDuration(seconds) {
  if (seconds == null) return "—"
  if (seconds < 60) return `${seconds} 秒`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m} 分 ${s} 秒`
}

function isToday(ts) {
  if (ts == null) return false
  const ms = ts < 1e12 ? ts * 1000 : ts
  const d = new Date(ms)
  const now = new Date()
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  )
}

function sortTasks(list) {
  const order = { running: 0, pending: 1, done: 2 }
  return [...list].sort((a, b) => {
    const oa = order[a.status] ?? 9
    const ob = order[b.status] ?? 9
    if (oa !== ob) return oa - ob
    const ta = a.completed_at || a.started_at || a.timestamp || 0
    const tb = b.completed_at || b.started_at || b.timestamp || 0
    return tb - ta
  })
}

function mergeTasksList(newTasks, cachedTasks) {
  const cacheMap = new Map(cachedTasks.map((t) => [t.id, t]))
  return newTasks.map((t) => {
    const old = cacheMap.get(t.id)
    if (!old) return t
    const merged = { ...t }
    if ((!merged.images || merged.images.length === 0) && old.images?.length) {
      merged.images = old.images
    }
    if ((!merged.videos || merged.videos.length === 0) && old.videos?.length) {
      merged.videos = old.videos
    }
    if (merged.is_video == null && old.is_video != null) {
      merged.is_video = old.is_video
    }
    if (!merged.result_media_type && old.result_media_type) {
      merged.result_media_type = old.result_media_type
    }
    if (!merged.prompt_text && old.prompt_text) merged.prompt_text = old.prompt_text
    if (!merged.negative_text && old.negative_text) merged.negative_text = old.negative_text
    return merged
  })
}

function findSizeIndex(width, height, options = SIZE_OPTIONS) {
  const idx = options.findIndex((o) => o.width === width && o.height === height)
  return idx >= 0 ? idx : 0
}

function taskHasMedia(task) {
  if (taskIsPlayableVideo(task)) {
    return (task.videos?.length ?? 0) > 0
  }
  return (task.images?.length ?? 0) > 0
}

function taskCover(task) {
  if (taskIsPlayableVideo(task)) {
    return task.videos?.[0]
  }
  return task.images?.[0]
}

function progressFromWs(stage, current = 0, total = DEFAULT_STEPS) {
  if (stage === "sampling") return progressSampling(current, total)
  if (stage === "decoding") return progressDecoding()
  if (stage === "saving") return progressSaving()
  if (stage === "done") return progressDone()
  return progressSampling(current, total)
}

function downloadTaskMedia(task) {
  const cover = taskCover(task)
  if (!cover) return
  const a = document.createElement("a")
  a.href = mediaUrl(cover)
  a.download = downloadFilename(task, cover)
  a.rel = "noopener"
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function progressSampling(current, total) {
  const t = total > 0 ? total : DEFAULT_STEPS
  const c = current ?? 0
  return {
    phase: "sampling",
    current: c,
    total: t,
    percent: Math.min(85, Math.round((c / t) * 85)),
    label: `${c} / ${t} 步`,
  }
}

function progressDecoding() {
  return { phase: "decoding", percent: 88, label: "图像解码中..." }
}

function progressSaving() {
  return { phase: "saving", percent: 95, label: "保存图像..." }
}

function progressDone() {
  return { phase: "done", percent: 100, label: "完成" }
}

function MediaPreviewOverlay({ preview, onClose }) {
  useEffect(() => {
    if (!preview) return
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKeyDown)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = prevOverflow
    }
  }, [preview, onClose])

  if (!preview) return null

  return createPortal(
    <div className="media-preview-overlay" onClick={onClose} role="presentation">
      <button
        type="button"
        className="media-preview-close"
        onClick={(e) => {
          e.stopPropagation()
          onClose()
        }}
        aria-label="关闭"
      >
        ×
      </button>
      {preview.type === "video" ? (
        <video
          src={preview.url}
          controls
          autoPlay
          playsInline
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <img src={preview.url} alt="预览" onClick={(e) => e.stopPropagation()} />
      )}
    </div>,
    getThemePortalRoot()
  )
}

function PromptSceneField({
  label,
  required,
  placeholder,
  scene,
  onSceneChange,
  optimizeMode,
  onOptimized,
}) {
  const [optimizing, setOptimizing] = useState(false)
  const [optimizeHint, setOptimizeHint] = useState(null)
  const [optimizeError, setOptimizeError] = useState(null)

  const handleOptimize = async () => {
    if (!scene.trim()) {
      setOptimizeError("请先填写画面描述")
      setOptimizeHint(null)
      return
    }
    setOptimizing(true)
    setOptimizeError(null)
    setOptimizeHint(null)

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 15000)

    try {
      const res = await api.post(
        `/api/optimize-prompt`,
        { text: scene.trim(), mode: optimizeMode },
        { signal: controller.signal, timeout: 15000 }
      )
      clearTimeout(timeoutId)

      if (res.data.positive) {
        onOptimized(res.data.positive, res.data.negative || "")
      }
      if (res.data.error) {
        setOptimizeHint(res.data.error)
      }
    } catch (err) {
      clearTimeout(timeoutId)
      const isAbort =
        err.name === "AbortError" ||
        err.name === "CanceledError" ||
        err.code === "ECONNABORTED"
      if (isAbort) {
        setOptimizeError("优化超时，请重试")
      } else {
        const detail = err.response?.data?.detail
        setOptimizeError(
          typeof detail === "string" ? detail : "优化失败，请重试"
        )
      }
    } finally {
      setOptimizing(false)
    }
  }

  return (
    <div className="form-group">
      <label>
        {label}
        {required && <span className="required">*</span>}
      </label>
      <div className="scene-input-wrap">
        <textarea
          className="scene-textarea"
          value={scene}
          onChange={(e) => {
            onSceneChange(e.target.value)
            if (optimizeError) setOptimizeError(null)
            if (optimizeHint) setOptimizeHint(null)
          }}
          placeholder={placeholder}
          required={required}
        />
        <button
          type="button"
          className={`optimize-btn${optimizing ? " loading" : ""}`}
          onClick={handleOptimize}
          disabled={optimizing || !scene.trim()}
        >
          {optimizing ? (
            <>
              <span className="optimize-spinner" aria-hidden="true" />
              优化中...
            </>
          ) : (
            "✨ 智能优化"
          )}
        </button>
      </div>
      <p className="form-hint form-hint-sub">支持中文描述，AI 将自动优化为专业提示词</p>
      {optimizeHint && <p className="form-hint form-hint-warn">{optimizeHint}</p>}
      {optimizeError && <p className="form-hint form-hint-error">{optimizeError}</p>}
    </div>
  )
}

export default function App() {
  const [activeTab, setActiveTab] = useState("submit")
  const [tasks, setTasks] = useState([])
  const [initialLoading, setInitialLoading] = useState(true)
  const [preview, setPreview] = useState(null)
  const [progressMap, setProgressMap] = useState({})
  const [hiddenIds, setHiddenIds] = useState(() => new Set())
  const [selectedTask, setSelectedTask] = useState(null)
  const [contextMenu, setContextMenu] = useState(null)
  const [submitPrefill, setSubmitPrefill] = useState(null)
  const [videoPrefill, setVideoPrefill] = useState(null)

  const tasksCacheRef = useRef([])
  const hiddenIdsRef = useRef(hiddenIds)
  const activeTaskIdRef = useRef(null)
  const fetchTasksRef = useRef(null)

  hiddenIdsRef.current = hiddenIds

  const openPreview = useCallback((url, taskType) => {
    const type = taskType === "video" || isVideoMediaUrl(url) ? "video" : "image"
    setPreview({ url, type })
  }, [])

  const applyTasks = useCallback((list) => {
    const merged = mergeTasksList(list, tasksCacheRef.current)
    const sorted = sortTasks(merged)
    tasksCacheRef.current = sorted
    setTasks(sorted.filter((t) => !hiddenIdsRef.current.has(t.id)))

    setProgressMap((prev) => {
      const next = { ...prev }
      for (const t of sorted) {
        if (t.status === "done" && taskHasMedia(t) && prev[t.id]?.phase === "saving") {
          next[t.id] = progressDone()
          setTimeout(() => {
            setProgressMap((p) => {
              const n = { ...p }
              delete n[t.id]
              return n
            })
          }, 500)
        }
      }
      return next
    })
  }, [])

  const fetchTasks = useCallback(async () => {
    try {
      const res = await api.get("/api/tasks")
      applyTasks(res.data.tasks || [])
    } catch (e) {
      console.error("获取任务失败", e)
      if (tasksCacheRef.current.length > 0) {
        setTasks(tasksCacheRef.current.filter((t) => !hiddenIdsRef.current.has(t.id)))
      }
    } finally {
      setInitialLoading(false)
    }
  }, [applyTasks])

  fetchTasksRef.current = fetchTasks

  useEffect(() => {
    fetchTasks()
    const timer = setInterval(fetchTasks, POLL_INTERVAL)
    return () => clearInterval(timer)
  }, [fetchTasks])

  useEffect(() => {
    const handleClick = () => setContextMenu(null)
    const handleContextMenuGlobal = (e) => {
      if (!e.target.closest(".task-card")) {
        setContextMenu(null)
      }
    }
    document.addEventListener("click", handleClick)
    document.addEventListener("contextmenu", handleContextMenuGlobal)
    return () => {
      document.removeEventListener("click", handleClick)
      document.removeEventListener("contextmenu", handleContextMenuGlobal)
    }
  }, [])

  useEffect(() => {
    if (localStorage.getItem("access_token")) {
      wsManager.connect()
    }
    const removeListener = wsManager.addListener((msg) => {
      const { type, data } = msg

      if (type === "progress" && data) {
        const pid = data.prompt_id ?? activeTaskIdRef.current
        if (!pid) return
        activeTaskIdRef.current = pid
        const step = Number(data.value ?? 0)
        const total = Number(data.max ?? DEFAULT_STEPS) || DEFAULT_STEPS
        setProgressMap((prev) => ({
          ...prev,
          [pid]: progressFromWs("sampling", step, total),
        }))
      }

      if (type === "executing" && data?.prompt_id) {
        const pid = data.prompt_id
        if (data.node == null) {
          setProgressMap((prev) => ({
            ...prev,
            [pid]: progressFromWs("done", 1, 1),
          }))
          activeTaskIdRef.current = null
          fetchTasksRef.current?.()
          setTimeout(() => {
            setProgressMap((prev) => {
              const next = { ...prev }
              delete next[pid]
              return next
            })
          }, 500)
        } else {
          activeTaskIdRef.current = pid
          setProgressMap((prev) => ({
            ...prev,
            [pid]: progressFromWs("decoding"),
          }))
        }
      }
    })
    return removeListener
  }, [])

  const stats = useMemo(() => {
    const running = tasks.filter((t) => t.status === "running")
    const pending = tasks.filter((t) => t.status === "pending")
    const doneToday = tasks.filter(
      (t) => t.status === "done" && isToday(t.completed_at || t.timestamp)
    )
    return {
      todayTotal: doneToday.length + running.length + pending.length,
      completed: doneToday.length,
      generating: running.length,
    }
  }, [tasks])

  const hasGeneratingTasks = useMemo(
    () => tasks.some((t) => t.status === "running" || t.status === "pending"),
    [tasks]
  )

  useEffect(() => {
    document.title = `Velora - ${PAGE_TITLES[activeTab] || "工作台"}`
  }, [activeTab])

  const handleContextMenu = (e, taskId) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      taskId,
    })
  }

  const hideTask = useCallback((taskId) => {
    setHiddenIds((prev) => new Set([...prev, taskId]))
    if (selectedTask?.id === taskId) setSelectedTask(null)
    setTasks((prev) => prev.filter((t) => t.id !== taskId))
  }, [selectedTask])

  const handleCancel = useCallback(
    async (taskId) => {
      try {
        await api.post(`/api/task/${taskId}/cancel`)
        setProgressMap((prev) => {
          const next = { ...prev }
          delete next[taskId]
          return next
        })
        fetchTasks()
      } catch (e) {
        console.error("取消失败", e)
        alert("取消失败，请稍后重试")
      }
    },
    [fetchTasks]
  )

  const initTaskProgress = (taskId) => {
    if (!taskId) return
    activeTaskIdRef.current = taskId
    setProgressMap((prev) => ({
      ...prev,
      [taskId]: progressSampling(0, DEFAULT_STEPS),
    }))
  }

  const handleImageSubmitSuccess = (taskId) => {
    initTaskProgress(taskId)
    setActiveTab("tasks")
    fetchTasks()
  }

  const handleVideoSubmitSuccess = (taskId) => {
    initTaskProgress(taskId)
    setActiveTab("tasks")
    fetchTasks()
  }

  const handleRegenerate = (task) => {
    if (taskIsPlayableVideo(task) || task.task_type === "video") {
      setVideoPrefill({
        scene: task.prompt_text || "",
        unwanted: task.negative_text || DEFAULT_VIDEO_UNWANTED,
        sizeIndex: findSizeIndex(task.width, task.height, VIDEO_SIZE_OPTIONS),
        mode: "text2video",
      })
      setActiveTab("video")
    } else {
      setSubmitPrefill({
        scene: task.prompt_text || "",
        unwanted: task.negative_text || DEFAULT_UNWANTED,
        style: "realistic",
        sizeIndex: findSizeIndex(task.width, task.height),
      })
      setActiveTab("submit")
    }
    setSelectedTask(null)
  }

  return (
    <>
      <nav className="tab-bar studio-tabs">
        <button
          type="button"
          className={`tab-btn${activeTab === "submit" ? " active" : ""}`}
          onClick={() => setActiveTab("submit")}
        >
          图像生成
        </button>
        <button
          type="button"
          className={`tab-btn${activeTab === "video" ? " active" : ""}`}
          onClick={() => setActiveTab("video")}
        >
          视频生成
        </button>
        <button
          type="button"
          className={`tab-btn${activeTab === "tasks" ? " active" : ""}`}
          onClick={() => setActiveTab("tasks")}
        >
          任务管理
        </button>
      </nav>

      <main className="app-body">
        {activeTab === "submit" && (
          <SubmitForm
            clientId={wsManager.getClientId()}
            prefill={submitPrefill}
            onPrefillConsumed={() => setSubmitPrefill(null)}
            onSuccess={handleImageSubmitSuccess}
            generating={hasGeneratingTasks}
          />
        )}
        {activeTab === "video" && (
          <VideoSubmitForm
            clientId={wsManager.getClientId()}
            prefill={videoPrefill}
            onPrefillConsumed={() => setVideoPrefill(null)}
            onSuccess={handleVideoSubmitSuccess}
            generating={hasGeneratingTasks}
          />
        )}
        {activeTab === "tasks" && (
          <TaskManagement
            tasks={tasks}
            initialLoading={initialLoading}
            stats={stats}
            progressMap={progressMap}
            selectedTaskId={selectedTask?.id}
            onSelectTask={setSelectedTask}
            onContextMenu={handleContextMenu}
            onPreview={openPreview}
          />
        )}
      </main>

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          taskId={contextMenu.taskId}
          tasks={tasks}
          onClose={() => setContextMenu(null)}
          onCancel={handleCancel}
          onDownload={downloadTaskMedia}
          onHide={hideTask}
        />
      )}

      <TaskModal
        task={selectedTask}
        open={!!selectedTask}
        onClose={() => setSelectedTask(null)}
        onPreview={openPreview}
        onDownload={downloadTaskMedia}
        onRegenerate={handleRegenerate}
      />

      <MediaPreviewOverlay preview={preview} onClose={() => setPreview(null)} />
    </>
  )
}

function SubmitForm({ clientId, prefill, onPrefillConsumed, onSuccess, generating }) {
  const [scene, setScene] = useState("")
  const [unwanted, setUnwanted] = useState(DEFAULT_UNWANTED)
  const [style, setStyle] = useState("realistic")
  const [sizeIndex, setSizeIndex] = useState(0)
  const [autoOptimize, setAutoOptimize] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    if (!prefill) return
    setScene(prefill.scene || "")
    setUnwanted(prefill.unwanted || DEFAULT_UNWANTED)
    setStyle(prefill.style || "realistic")
    setSizeIndex(prefill.sizeIndex ?? 0)
    onPrefillConsumed?.()
  }, [prefill, onPrefillConsumed])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!scene.trim()) {
      setMessage({ type: "error", text: "请填写画面描述" })
      return
    }
    const size = SIZE_OPTIONS[sizeIndex]
    setSubmitting(true)
    setMessage(null)
    try {
      const res = await api.post(`/api/submit`, {
        prompt: scene.trim(),
        negative_prompt: unwanted.trim() || DEFAULT_UNWANTED,
        style,
        width: size.width,
        height: size.height,
        client_id: clientId,
        auto_optimize: autoOptimize,
      })
      setMessage({ type: "success", text: `已提交，任务 ID：${res.data.task_id.slice(0, 8)}…` })
      setScene("")
      setTimeout(() => onSuccess(res.data.task_id), 600)
    } catch (err) {
      const detail = err.response?.data?.detail
      setMessage({
        type: "error",
        text: typeof detail === "string" ? detail : "提交失败，请确认后端与 ComfyUI 已启动",
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="submit-card">
      <h2 className="submit-page-title">图像生成</h2>
      <ModelSelectBanner
        type="image"
        icon="🎨"
        label="图像模型"
        disabled={generating || submitting}
      />
      <form onSubmit={handleSubmit}>
        <PromptSceneField
          label="画面描述"
          required
          placeholder="描述你想生成的画面"
          scene={scene}
          onSceneChange={setScene}
          optimizeMode="image"
          onOptimized={(positive, negative) => {
            setScene(positive)
            setUnwanted(negative)
          }}
        />
        <div className="form-group">
          <label>不想要的元素</label>
          <textarea value={unwanted} onChange={(e) => setUnwanted(e.target.value)} rows={2} />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>输出尺寸</label>
            <select value={sizeIndex} onChange={(e) => setSizeIndex(Number(e.target.value))}>
              {SIZE_OPTIONS.map((opt, i) => (
                <option key={opt.label} value={i}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>风格</label>
            <select value={style} onChange={(e) => setStyle(e.target.value)}>
              {STYLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>
        <label className="auto-optimize-toggle">
          <input
            type="checkbox"
            checked={autoOptimize}
            onChange={(e) => setAutoOptimize(e.target.checked)}
          />
          <span>自动优化提示词</span>
          <span className="toggle-hint">（提交时由 AI 自动转为英文专业提示词）</span>
        </label>
        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? "提交中…" : "开始生成"}
        </button>
        {message && <div className={`submit-message ${message.type}`}>{message.text}</div>}
      </form>
    </div>
  )
}

function VideoSubmitForm({ clientId, prefill, onPrefillConsumed, onSuccess, generating }) {
  const [mode, setMode] = useState("text2video")
  const [scene, setScene] = useState("")
  const [unwanted, setUnwanted] = useState(DEFAULT_VIDEO_UNWANTED)
  const [duration, setDuration] = useState(5)
  const [sizeIndex, setSizeIndex] = useState(1)
  const [autoOptimize, setAutoOptimize] = useState(true)
  const [imagePreview, setImagePreview] = useState(null)
  const [imageB64, setImageB64] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState(null)
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    if (!prefill) return
    setScene(prefill.scene || "")
    setUnwanted(prefill.unwanted || DEFAULT_VIDEO_UNWANTED)
    setSizeIndex(prefill.sizeIndex ?? 1)
    setMode(prefill.mode || "text2video")
    onPrefillConsumed?.()
  }, [prefill, onPrefillConsumed])

  const readFile = (file) => {
    if (!file?.type?.startsWith("image/")) return
    const reader = new FileReader()
    reader.onload = () => {
      setImagePreview(reader.result)
      setImageB64(reader.result)
    }
    reader.readAsDataURL(file)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!scene.trim()) {
      setMessage({ type: "error", text: "请填写画面描述" })
      return
    }
    if (mode === "image2video" && !imageB64) {
      setMessage({ type: "error", text: "请上传参考图片" })
      return
    }
    const size = VIDEO_SIZE_OPTIONS[sizeIndex]
    setSubmitting(true)
    setMessage(null)
    try {
      const res = await api.post(`/api/submit/video`, {
        prompt: scene.trim(),
        negative_prompt: unwanted.trim(),
        duration,
        width: size.width,
        height: size.height,
        mode,
        image: mode === "image2video" ? imageB64 : undefined,
        client_id: clientId,
        auto_optimize: autoOptimize,
      })
      setMessage({ type: "success", text: `已提交，任务 ID：${res.data.task_id.slice(0, 8)}…` })
      setTimeout(() => onSuccess(res.data.task_id), 600)
    } catch (err) {
      const detail = err.response?.data?.detail
      setMessage({
        type: "error",
        text: typeof detail === "string" ? detail : "提交失败，请确认后端与 ComfyUI 已启动",
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="submit-card">
      <h2 className="submit-page-title">视频生成</h2>
      <ModelSelectBanner
        type="video"
        icon="🎬"
        label="视频模型"
        disabled={generating || submitting}
      />
      <form onSubmit={handleSubmit}>
        <div className="mode-cards">
          <button
            type="button"
            className={`mode-card${mode === "text2video" ? " active" : ""}`}
            onClick={() => setMode("text2video")}
          >
            <div className="icon">📝</div>
            <div className="title">文字生成视频</div>
          </button>
          <button
            type="button"
            className={`mode-card${mode === "image2video" ? " active" : ""}`}
            onClick={() => setMode("image2video")}
          >
            <div className="icon">🖼️</div>
            <div className="title">图片生成视频</div>
          </button>
        </div>

        <PromptSceneField
          label="画面描述"
          required
          placeholder="描述视频中的画面与动作"
          scene={scene}
          onSceneChange={setScene}
          optimizeMode="video"
          onOptimized={(positive, negative) => {
            setScene(positive)
            setUnwanted(negative)
          }}
        />

        <div className="form-group">
          <label>不想要的元素</label>
          <textarea value={unwanted} onChange={(e) => setUnwanted(e.target.value)} rows={2} />
        </div>

        {mode === "image2video" && (
          <div
            className={`upload-zone${dragOver ? " dragover" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              readFile(e.dataTransfer.files?.[0])
            }}
            onClick={() => document.getElementById("video-upload-input")?.click()}
          >
            <input
              id="video-upload-input"
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => readFile(e.target.files?.[0])}
            />
            {imagePreview ? (
              <img src={imagePreview} alt="预览" />
            ) : (
              <p>点击或拖拽上传参考图片</p>
            )}
          </div>
        )}

        <div className="video-params">
          <div className="form-group">
            <label>时长</label>
            <select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
              <option value={3}>3 秒</option>
              <option value={5}>5 秒</option>
            </select>
          </div>
          <div className="form-group">
            <label>尺寸</label>
            <select value={sizeIndex} onChange={(e) => setSizeIndex(Number(e.target.value))}>
              {VIDEO_SIZE_OPTIONS.map((opt, i) => (
                <option key={opt.label} value={i}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>

        {VIDEO_SIZE_OPTIONS[sizeIndex]?.warnVram && (
          <p className="form-hint form-hint-warn">
            720P 显存要求较高，8GB 显存可能生成较慢，建议使用 480P 选项。
          </p>
        )}

        <p className="form-hint">本地模型生成，宽高已按 32 倍数对齐。帧率固定 24fps。</p>

        <label className="auto-optimize-toggle">
          <input
            type="checkbox"
            checked={autoOptimize}
            onChange={(e) => setAutoOptimize(e.target.checked)}
          />
          <span>自动优化提示词</span>
          <span className="toggle-hint">（提交时由 AI 自动转为英文专业提示词）</span>
        </label>

        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? "提交中…" : "开始生成视频"}
        </button>
        {message && <div className={`submit-message ${message.type}`}>{message.text}</div>}
      </form>
    </div>
  )
}

function TaskManagement({ tasks, initialLoading, stats, progressMap, selectedTaskId, onSelectTask, onContextMenu, onPreview }) {
  const [storageInfo, setStorageInfo] = useState(null)
  const [storageOpen, setStorageOpen] = useState(false)
  const [storageLoading, setStorageLoading] = useState(false)

  const loadStorageInfo = async () => {
    setStorageLoading(true)
    try {
      const res = await api.get(`/api/storage/info`)
      setStorageInfo(res.data)
      setStorageOpen(true)
    } catch (e) {
      console.error("获取存储信息失败", e)
      alert("获取存储信息失败，请确认后端与 ComfyUI 已启动")
    } finally {
      setStorageLoading(false)
    }
  }

  return (
    <>
      <div className="stats-row">
        <StatCard icon="📋" label="今日任务" value={stats.todayTotal} variant="blue" />
        <StatCard icon="✅" label="已完成" value={stats.completed} variant="green" />
        <StatCard icon="⚡" label="生成中" value={stats.generating} variant="orange" />
        <button
          type="button"
          className="storage-info-btn"
          onClick={loadStorageInfo}
          disabled={storageLoading}
        >
          {storageLoading ? "加载中…" : "存储信息"}
        </button>
      </div>

      {storageOpen && storageInfo && (
        <div className="storage-popover" role="dialog">
          <div className="storage-popover-header">
            <strong>ComfyUI 输出目录</strong>
            <button type="button" className="storage-popover-close" onClick={() => setStorageOpen(false)}>
              ×
            </button>
          </div>
          <p className="storage-path">{storageInfo.comfyui_output}</p>
          <ul className="storage-stats-list">
            <li>图片文件：{storageInfo.images_count} 个</li>
            <li>视频文件：{storageInfo.videos_count} 个</li>
            <li>总占用：{storageInfo.total_size_mb} MB</li>
          </ul>
        </div>
      )}
      {initialLoading && tasks.length === 0 && (
        <div className="initial-loading">加载任务列表中…</div>
      )}
      {!initialLoading && tasks.length === 0 && (
        <div className="empty-state">
          <div className="icon">🎞️</div>
          <p>暂无任务，去提交一个生成任务吧</p>
        </div>
      )}
      <div className="tasks-grid">
        {tasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            progress={progressMap[task.id]}
            selected={task.id === selectedTaskId}
            onSelect={() => onSelectTask(task)}
            onContextMenu={(e) => onContextMenu(e, task.id)}
            onPreview={onPreview}
          />
        ))}
      </div>
    </>
  )
}

function StatCard({ icon, label, value, variant }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${variant}`}>{icon}</div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}

function TaskCard({ task, progress, selected, onSelect, onContextMenu, onPreview }) {
  const showVideo = taskIsPlayableVideo(task)
  const videoFile = task.videos?.[0]
  const imageFile = task.images?.[0]
  const videoSrc = showVideo && videoFile ? mediaUrl(videoFile) : null
  const imageSrc = !showVideo && imageFile ? mediaUrl(imageFile) : null
  const pct = progress?.percent ?? 0
  const showProgress = task.status !== "done" || (progress && progress.phase !== "done")

  return (
    <article
      className={`task-card${selected ? " selected" : ""}`}
      onContextMenu={onContextMenu}
    >
      <div className="task-card-media">
        {task.status === "done" && showVideo && videoSrc ? (
          <div
            className="task-card-video-wrap"
            onClick={(e) => {
              e.stopPropagation()
              onPreview(videoSrc, "video")
            }}
          >
            <video
              src={videoSrc}
              className="task-card-video"
              muted
              loop
              playsInline
              preload="metadata"
              onMouseEnter={(e) => e.currentTarget.play().catch(() => {})}
              onMouseLeave={(e) => {
                const v = e.currentTarget
                v.pause()
                v.currentTime = 0
              }}
            />
            <span className="task-type-badge">▶ 视频</span>
          </div>
        ) : task.status === "done" && imageSrc ? (
          <img
            src={imageSrc}
            alt={imageFile?.filename || "生成图"}
            loading="lazy"
            className="task-card-image"
            onClick={(e) => {
              e.stopPropagation()
              onPreview(imageSrc, "image")
            }}
          />
        ) : (
          <div className="task-card-placeholder">
            <span className="icon">{task.status === "running" ? "⏳" : task.status === "pending" ? "🕐" : showVideo || task.task_type === "video" ? "🎬" : "🖼️"}</span>
            <span>{task.status === "running" ? "生成中..." : task.status === "pending" ? "排队等待" : "暂无预览"}</span>
          </div>
        )}
      </div>
      <div className="task-card-body" onClick={onSelect}>
        <div className="task-card-top">
          <span className="task-id">{task.id.slice(0, 8)}…</span>
          <span className={`status-badge ${task.status}`}>{task.status_text}</span>
        </div>
        <div className="task-time">生成时间：{formatTimestamp(task.completed_at || task.timestamp)}</div>
        {showProgress && progress && (
          <div className="progress-block">
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            </div>
            <div className="progress-text">{progress.label}</div>
          </div>
        )}
        {task.status === "pending" && !progress && (
          <div className="pending-text">等待队列中</div>
        )}
      </div>
    </article>
  )
}

function ContextMenu({ x, y, taskId, tasks, onClose, onCancel, onDownload, onHide }) {
  const task = tasks.find((t) => t.id === taskId)
  if (!task) return null

  const canCancel = task.status === "running" || task.status === "pending"
  const canDownload = task.status === "done" && taskHasMedia(task)
  const saveLabel = taskIsPlayableVideo(task) ? "保存视频" : "保存图片"

  return (
    <div
      className="context-menu"
      style={{
        position: "fixed",
        left: x,
        top: y,
        zIndex: 9999,
        background: "#fff",
        borderRadius: 8,
        boxShadow: "0 4px 20px rgba(0, 0, 0, 0.15)",
        padding: "4px 0",
        minWidth: 150,
      }}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.preventDefault()}
    >
      {canCancel && (
        <button type="button" className="context-menu-item" onClick={() => { onCancel(task.id); onClose() }}>
          暂停 / 取消
        </button>
      )}
      {canDownload && (
        <button type="button" className="context-menu-item" onClick={() => { onDownload(task); onClose() }}>
          {saveLabel}
        </button>
      )}
      <button type="button" className="context-menu-item danger" onClick={() => { onHide(task.id); onClose() }}>
        删除记录
      </button>
    </div>
  )
}

function TaskModal({ task, open, onClose, onPreview, onDownload, onRegenerate }) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKeyDown)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = prevOverflow
    }
  }, [open, onClose])

  if (!open || !task) return null

  const cover = taskCover(task)
  const src = cover ? mediaUrl(cover) : null
  const showVideo = taskIsPlayableVideo(task)
  const sizeLabel = task.width && task.height ? `${task.width} × ${task.height}` : "—"
  const typeLabel = showVideo ? "视频" : "图像"

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text || "")
    } catch {
      alert("复制失败")
    }
  }

  return createPortal(
    <div className="task-modal-root" role="presentation">
      <div className="modal-backdrop" onClick={onClose} aria-hidden="true" />
      <div
        className="task-modal open"
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-titlebar">
          <div className="modal-titlebar-left">
            <span className={`status-badge ${task.status}`}>{task.status_text}</span>
            <span className="modal-titlebar-id" id="task-modal-title">
              任务 {task.id.slice(0, 8)}
            </span>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>

        <div className="modal-body">
          <div className="modal-preview">
            {src ? (
              showVideo ? (
                <video
                  src={src}
                  controls
                  playsInline
                  onClick={(e) => {
                    e.stopPropagation()
                    onPreview(src, "video")
                  }}
                />
              ) : (
                <img
                  src={src}
                  alt="预览"
                  onClick={(e) => {
                    e.stopPropagation()
                    onPreview(src, "image")
                  }}
                />
              )
            ) : (
              <div className="modal-preview-placeholder">暂无预览</div>
            )}
          </div>

          <div className="info-grid">
            <div className="info-grid-item">
              <label>生成时间</label>
              <p>{formatTimestamp(task.completed_at || task.timestamp)}</p>
            </div>
            <div className="info-grid-item">
              <label>耗时</label>
              <p>{formatDuration(task.duration)}</p>
            </div>
            <div className="info-grid-item">
              <label>图像尺寸</label>
              <p>{sizeLabel}</p>
            </div>
            <div className="info-grid-item">
              <label>生成类型</label>
              <p>{typeLabel}</p>
            </div>
          </div>

          <PromptBlock title="画面描述" text={task.prompt_text} onCopy={() => copyText(task.prompt_text)} />
          <PromptBlock title="排除元素" text={task.negative_text} onCopy={() => copyText(task.negative_text)} />
        </div>

        <div className="modal-footer">
          <button type="button" className="modal-btn" onClick={() => onRegenerate(task)}>
            用此提示词再次生成
          </button>
          <button
            type="button"
            className="modal-btn primary"
            disabled={!src}
            onClick={() => onDownload(task)}
          >
            保存文件
          </button>
        </div>
      </div>
    </div>,
    getThemePortalRoot()
  )
}

function PromptBlock({ title, text, onCopy }) {
  return (
    <div className="prompt-block">
      <div className="prompt-block-header">
        <label>{title}</label>
        <button type="button" className="copy-btn" onClick={onCopy}>复制</button>
      </div>
      <div className="prompt-box">{text || "—"}</div>
    </div>
  )
}
