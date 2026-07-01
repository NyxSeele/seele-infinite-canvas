import { useCallback, useEffect, useState } from "react"
import { message, Switch } from "antd"
import api from "../../services/api"
import "./UserModelPermissions.css"

function typeLabel(type) {
  if (type === "video") return "视频"
  if (type === "text") return "文本"
  return "图像"
}

export default function UserModelPermissions({ userId }) {
  const [catalog, setCatalog] = useState([])
  const [permissions, setPermissions] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    if (!userId) return
    setLoading(true)
    try {
      const [modelsRes, permRes] = await Promise.all([
        api.get("/api/admin/catalog-models"),
        api.get(`/api/admin/users/${userId}/models`),
      ])
      const catalogMap = new Map(
        (modelsRes.data.models || []).map((m) => [m.model_id, m])
      )
      const merged = (permRes.data.permissions || []).map((p) => ({
        ...p,
        name: catalogMap.get(p.model_id)?.name || p.model_id,
        type: catalogMap.get(p.model_id)?.type || "image",
      }))
      setCatalog(modelsRes.data.models || [])
      setPermissions(merged)
    } catch (err) {
      const detail = err.response?.data?.detail
      message.error(typeof detail === "string" ? detail : "加载模型权限失败")
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    load()
  }, [load])

  const savePermissions = async (nextPermissions) => {
    setSaving(true)
    try {
      const res = await api.put(`/api/admin/users/${userId}/models`, {
        permissions: nextPermissions.map((p) => ({
          model_id: p.model_id,
          enabled: p.enabled,
        })),
      })
      const catalogMap = new Map(catalog.map((m) => [m.model_id, m]))
      const merged = (res.data.permissions || []).map((p) => ({
        ...p,
        name: catalogMap.get(p.model_id)?.name || p.model_id,
        type: catalogMap.get(p.model_id)?.type || "image",
      }))
      setPermissions(merged)
      message.success("权限已更新")
    } catch (err) {
      const detail = err.response?.data?.detail
      message.error(typeof detail === "string" ? detail : "更新权限失败")
      await load()
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = (modelId, enabled) => {
    const next = permissions.map((p) =>
      p.model_id === modelId ? { ...p, enabled } : p
    )
    setPermissions(next)
    savePermissions(next)
  }

  if (!userId) {
    return <p className="admin-empty-hint">请从左侧选择用户</p>
  }

  if (loading) {
    return <p className="admin-empty-hint">加载模型权限…</p>
  }

  if (permissions.length === 0) {
    return <p className="admin-empty-hint">暂无可用模型，请确认 ComfyUI 已配置 checkpoint</p>
  }

  return (
    <div className={`user-model-permissions${saving ? " is-saving" : ""}`}>
      {saving && <p className="admin-saving-hint">正在保存…</p>}
      <ul className="model-perm-list">
        {permissions.map((item) => (
          <li key={item.model_id} className="model-perm-row">
            <div className="model-perm-info">
              <span className="model-perm-name" title={item.model_id}>
                {item.name || item.model_id}
              </span>
              <span className={`model-perm-type type-${item.type}`}>
                {typeLabel(item.type)}
              </span>
            </div>
            <Switch
              checked={item.enabled}
              disabled={saving}
              onChange={(checked) => handleToggle(item.model_id, checked)}
            />
          </li>
        ))}
      </ul>
    </div>
  )
}
