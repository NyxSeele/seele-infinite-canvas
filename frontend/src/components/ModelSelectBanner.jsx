import { useCallback, useEffect, useState } from "react"
import { message } from "antd"
import api from "../services/api"
import { useAuth } from "../contexts/AuthContext.jsx"
import "./ModelSelectBanner.css"

function displayName(filename) {
  if (!filename) return ""
  const dot = filename.lastIndexOf(".")
  return dot > 0 ? filename.slice(0, dot) : filename
}

export default function ModelSelectBanner({
  type,
  icon,
  label,
  disabled = false,
}) {
  const { isAuthenticated } = useAuth()
  const [checkpoints, setCheckpoints] = useState([])
  const [current, setCurrent] = useState("")
  const [loading, setLoading] = useState(true)
  const [switching, setSwitching] = useState(false)

  const loadModels = useCallback(async () => {
    try {
      const currentRes = await api.get("/api/models/current")
      const cur = currentRes.data
      let selected = type === "image" ? cur.image_model : cur.video_model

      let filtered = []

      if (isAuthenticated) {
        const userRes = await api.get("/api/user/models")
        filtered = (userRes.data.models || [])
          .filter((m) => m.type === type && m.enabled)
          .map((m) => m.model_id)
      } else {
        const modelsRes = await api.get("/api/models", { params: { type } })
        const listKey =
          type === "image" ? "checkpoints_image" : "checkpoints_video"
        filtered =
          modelsRes.data[listKey] || modelsRes.data.checkpoints || []
      }

      if (selected && !filtered.includes(selected) && filtered.length > 0) {
        const fallback = filtered[0]
        try {
          await api.post("/api/models/select", { type, model: fallback })
        } catch {
          /* ignore silent switch failure */
        }
        selected = fallback
      }

      setCheckpoints(filtered)
      setCurrent(selected || filtered[0] || "")
    } catch (e) {
      console.error("加载模型列表失败", e)
      message.error("加载模型列表失败")
    } finally {
      setLoading(false)
    }
  }, [type, isAuthenticated])

  useEffect(() => {
    setLoading(true)
    loadModels()
  }, [loadModels])

  const handleChange = async (e) => {
    const model = e.target.value
    if (!model || model === current) return
    setSwitching(true)
    try {
      await api.post("/api/models/select", { type, model })
      setCurrent(model)
      const short = displayName(model)
      message.success(
        type === "image"
          ? `已切换图像模型为 ${short}`
          : `已切换视频模型为 ${short}`
      )
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || "切换失败"
      message.error(typeof detail === "string" ? detail : "切换失败")
      e.target.value = current
    } finally {
      setSwitching(false)
    }
  }

  const selectDisabled =
    disabled || loading || switching || checkpoints.length === 0
  const hint = disabled
    ? "生成中不可切换"
    : switching
      ? "切换中…"
      : loading
        ? "加载中…"
        : checkpoints.length === 0
          ? "无可用模型"
          : null

  return (
    <div className={`model-select-banner${selectDisabled ? " is-disabled" : ""}`}>
      <div className="model-select-banner-label">
        <span className="model-select-icon">{icon}</span>
        <span>{label}</span>
      </div>
      <div className="model-select-banner-control">
        <select
          className="model-select-dropdown"
          value={current}
          onChange={handleChange}
          disabled={selectDisabled}
          title={current || undefined}
        >
          {loading && <option value="">加载中…</option>}
          {!loading && checkpoints.length === 0 && (
            <option value="">无可用模型（请联系管理员）</option>
          )}
          {checkpoints.map((name) => (
            <option key={name} value={name} title={name}>
              {displayName(name)}
            </option>
          ))}
        </select>
        {hint && <span className="model-select-hint">{hint}</span>}
      </div>
    </div>
  )
}
