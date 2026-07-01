import { useCallback, useEffect, useMemo, useState } from "react"
import { message } from "antd"
import api from "../services/api"
import "./ModelManager.css"

const CATEGORY_LABELS = {
  checkpoints: "Checkpoints",
  loras: "LoRA",
  vae: "VAE",
  text_encoders: "文本编码器",
}

function fileExt(name) {
  const i = name.lastIndexOf(".")
  return i >= 0 ? name.slice(i + 1).toUpperCase() : "—"
}

function truncateName(name, max = 36) {
  if (!name || name.length <= max) return name
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : ""
  const base = name.slice(0, name.length - ext.length)
  const keep = max - ext.length - 3
  return `${base.slice(0, Math.max(keep, 8))}...${ext}`
}

function CurrentModelCard({ label, modelName, tag }) {
  const ext = fileExt(modelName)
  return (
    <div className="model-current-card">
      <div className="model-current-head">
        <span className="model-type-tag">{tag}</span>
        <span className="model-active-badge">使用中</span>
      </div>
      <p className="model-current-label">{label}</p>
      <p className="model-name-full" title={modelName}>
        {truncateName(modelName, 42)}
      </p>
      <p className="model-meta">格式：{ext}</p>
    </div>
  )
}

function LibraryModelCard({
  name,
  category,
  currentImage,
  currentVideo,
  switching,
  generating,
  onSelect,
}) {
  const isImage = currentImage === name
  const isVideo = currentVideo === name
  const canAssign = category === "checkpoints"
  const disabled = generating || !!switching
  const disabledTitle = generating
    ? "生成中不可切换"
    : !canAssign
      ? "仅 Checkpoints 可用于图像/视频生成"
      : ""

  return (
    <div className={`model-lib-card${isImage || isVideo ? " in-use" : ""}`}>
      <p className="model-lib-name" title={name}>
        {truncateName(name)}
      </p>
      <p className="model-meta">.{fileExt(name).toLowerCase()}</p>
      {(isImage || isVideo) && (
        <div className="model-lib-badges">
          {isImage && <span className="mini-badge image">图像</span>}
          {isVideo && <span className="mini-badge video">视频</span>}
        </div>
      )}
      <div className="model-lib-actions">
        <button
          type="button"
          className="model-select-btn"
          disabled={disabled || !canAssign}
          title={disabledTitle}
          onClick={() => onSelect("image", name)}
        >
          {switching === `image:${name}` ? "切换中…" : "用于图像"}
        </button>
        <button
          type="button"
          className="model-select-btn secondary"
          disabled={disabled || !canAssign}
          title={disabledTitle}
          onClick={() => onSelect("video", name)}
        >
          {switching === `video:${name}` ? "切换中…" : "用于视频"}
        </button>
      </div>
    </div>
  )
}

export default function ModelManager() {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [switching, setSwitching] = useState(null)
  const [generating, setGenerating] = useState(false)

  const fetchModels = useCallback(async () => {
    try {
      const res = await api.get("/api/models")
      setData(res.data)
    } catch (e) {
      console.error("获取模型列表失败", e)
      message.error("获取模型列表失败")
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchTaskStatus = useCallback(async () => {
    try {
      const res = await api.get("/api/tasks")
      const tasks = res.data.tasks || []
      const busy = tasks.some(
        (t) => t.status === "running" || t.status === "pending"
      )
      setGenerating(busy)
    } catch {
      setGenerating(false)
    }
  }, [])

  useEffect(() => {
    fetchModels()
    fetchTaskStatus()
    const timer = setInterval(fetchTaskStatus, 5000)
    return () => clearInterval(timer)
  }, [fetchModels, fetchTaskStatus])

  const handleSelect = async (type, model) => {
    if (generating) {
      message.warning("生成中不可切换模型")
      return
    }
    setSwitching(`${type}:${model}`)
    try {
      await api.post("/api/models/select", { type, model })
      message.success(
        type === "image"
          ? `已切换图像模型为 ${truncateName(model, 28)}`
          : `已切换视频模型为 ${truncateName(model, 28)}`
      )
      await fetchModels()
    } catch (e) {
      const detail = e.response?.data?.detail || e.message || "切换失败"
      message.error(typeof detail === "string" ? detail : "切换失败")
    } finally {
      setSwitching(null)
    }
  }

  const current = data?.current || {}
  const categories = useMemo(
    () => Object.keys(CATEGORY_LABELS),
    []
  )

  return (
    <div className="model-manager-page">
      <section className="model-section">
        <h2 className="model-section-title">当前使用的模型</h2>
        {loading ? (
          <p className="model-loading">加载中…</p>
        ) : (
          <div className="model-current-grid">
            <CurrentModelCard
              label="图像生成"
              tag="图像"
              modelName={current.image_model || "—"}
            />
            <CurrentModelCard
              label="视频生成"
              tag="视频"
              modelName={current.video_model || "—"}
            />
          </div>
        )}
        {generating && (
          <p className="model-generating-hint">⚠️ 有任务正在生成，暂不可切换模型</p>
        )}
      </section>

      <section className="model-section">
        <h2 className="model-section-title">本地模型库</h2>
        <p className="model-section-desc">
          扫描目录：D:\ComfyUI\ComfyUI\models\（.safetensors / .ckpt）
        </p>
        {loading ? (
          <p className="model-loading">加载模型库…</p>
        ) : (
          categories.map((key) => {
            const list = data?.[key] || []
            return (
              <div key={key} className="model-category-block">
                <h3 className="model-category-title">
                  {CATEGORY_LABELS[key]}
                  <span className="model-count">{list.length}</span>
                </h3>
                {list.length === 0 ? (
                  <p className="model-empty">暂无模型文件</p>
                ) : (
                  <div className="model-lib-grid">
                    {list.map((name) => (
                      <LibraryModelCard
                        key={`${key}-${name}`}
                        name={name}
                        category={key}
                        currentImage={current.image_model}
                        currentVideo={current.video_model}
                        switching={switching}
                        generating={generating}
                        onSelect={handleSelect}
                      />
                    ))}
                  </div>
                )}
              </div>
            )
          })
        )}
      </section>
    </div>
  )
}
