import { useCallback, useEffect, useMemo, useState } from "react"
import { message } from "antd"
import api from "../../services/api"
import ModelDrawer from "./ModelDrawer.jsx"
import { formatApiError } from "./formatApiError.js"
import { normalizeAdminModel } from "./modelUtils.js"

const CATEGORY_LABEL = { text: "文本", image: "图像", video: "视频" }
const TYPE_LABEL = { local: "本地", api: "API" }
const ROUTING_MODES = [
  { id: "fixed", label: "固定默认" },
  { id: "cheapest", label: "低价优先" },
  { id: "balanced", label: "均衡分流" },
]

export default function ModelManagement() {
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [toggling, setToggling] = useState("")
  const [err, setErr] = useState("")
  const [tab, setTab] = useState("all")
  const [drawerMode, setDrawerMode] = useState("create")
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingModel, setEditingModel] = useState(null)
  const [keyTesting, setKeyTesting] = useState("")
  const [testResults, setTestResults] = useState({})
  const [routingMode, setRoutingMode] = useState("fixed")
  const [routingLoading, setRoutingLoading] = useState(false)
  const [settingDefault, setSettingDefault] = useState("")

  const loadModels = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const res = await api.get("/api/admin/models")
      console.log("GET /api/admin/models response:", res.data)
      const list = (res.data?.models || [])
        .map(normalizeAdminModel)
        .filter(Boolean)
      setModels(list)
    } catch (e) {
      setErr(formatApiError(e.response?.data?.detail, "加载模型失败"))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadRouting = useCallback(async () => {
    setRoutingLoading(true)
    try {
      const res = await api.get("/api/admin/models/llm-routing")
      setRoutingMode(res.data?.mode || "fixed")
    } catch {
      /* 旧后端或未迁移时忽略 */
    } finally {
      setRoutingLoading(false)
    }
  }, [])

  useEffect(() => {
    loadModels()
    loadRouting()
  }, [loadModels, loadRouting])

  const handleRoutingModeChange = async (mode) => {
    const prev = routingMode
    setRoutingMode(mode)
    try {
      await api.put("/api/admin/models/llm-routing", { mode })
      message.success("分流策略已更新")
      await loadModels()
    } catch (e) {
      setRoutingMode(prev)
      await loadRouting()
      message.error(formatApiError(e.response?.data?.detail, "更新分流策略失败"))
    }
  }

  const handleSetDefault = async (modelId) => {
    if (!modelId) return
    setSettingDefault(modelId)
    try {
      await api.post(`/api/admin/models/${modelId}/set-default-text`)
      message.success("已设为默认 Agent LLM")
      await loadModels()
      await loadRouting()
    } catch (e) {
      message.error(formatApiError(e.response?.data?.detail, "设置默认失败"))
    } finally {
      setSettingDefault("")
    }
  }

  const handleToggle = async (modelId, currentEnabled) => {
    if (!modelId) {
      message.error("模型 ID 无效，请刷新页面后重试")
      return
    }
    const newEnabled = !currentEnabled
    setModels((prev) =>
      prev.map((m) => (m.id === modelId ? { ...m, enabled: newEnabled } : m))
    )
    setToggling(modelId)
    try {
      await api.put(`/api/admin/models/${modelId}`, { enabled: newEnabled })
    } catch (e) {
      setModels((prev) =>
        prev.map((m) => (m.id === modelId ? { ...m, enabled: currentEnabled } : m))
      )
      message.error(formatApiError(e.response?.data?.detail, "更新开关失败"))
      setErr(formatApiError(e.response?.data?.detail, "操作失败"))
    } finally {
      setToggling("")
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    setErr("")
    try {
      const res = await api.post("/api/admin/models/refresh-check")
      await loadModels()
      const n = res.data?.inserted ?? 0
      message.success(
        n > 0 ? `已同步 ${n} 个新本地模型` : "检测缓存已刷新，已同步 ComfyUI 本地模型"
      )
    } catch (e) {
      setErr(formatApiError(e.response?.data?.detail, "刷新失败"))
    } finally {
      setRefreshing(false)
    }
  }

  const handleDelete = async (modelId) => {
    if (!modelId) return
    if (!window.confirm("确定删除该模型？")) return
    try {
      await api.delete(`/api/admin/models/${modelId}`)
      message.success("模型已删除")
      await loadModels()
    } catch (e) {
      message.error(formatApiError(e.response?.data?.detail, "删除失败"))
    }
  }

  const handleTest = async (modelId) => {
    if (!modelId) return
    setKeyTesting(modelId)
    setTestResults((prev) => ({ ...prev, [modelId]: null }))
    try {
      const res = await api.post(`/api/admin/models/${modelId}/test-connection`)
      setTestResults((prev) => ({ ...prev, [modelId]: res.data }))
      const timeout = res.data?.ok ? 3000 : 5000
      setTimeout(() => {
        setTestResults((prev) => ({ ...prev, [modelId]: null }))
      }, timeout)
    } catch (e) {
      setTestResults((prev) => ({
        ...prev,
        [modelId]: { ok: false, error: formatApiError(e.response?.data?.detail, "测试失败") },
      }))
      setTimeout(() => {
        setTestResults((prev) => ({ ...prev, [modelId]: null }))
      }, 5000)
    } finally {
      setKeyTesting("")
    }
  }

  const filteredModels = useMemo(() => {
    if (tab === "all") return models
    return models.filter((m) => m.category === tab)
  }, [models, tab])

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 20,
          gap: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {[
            { id: "all", label: "全部" },
            { id: "text", label: "文本" },
            { id: "image", label: "图像" },
            { id: "video", label: "视频" },
          ].map((item) => (
            <button
              key={item.id}
              type="button"
              className={`adm-btn${tab === item.id ? " adm-btn--primary" : ""}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            className="adm-btn adm-btn--primary"
            onClick={() => {
              setDrawerMode("create")
              setEditingModel(null)
              setDrawerOpen(true)
            }}
          >
            + 添加 API 模型
          </button>
          <button
            className="adm-btn"
            onClick={handleRefresh}
            disabled={refreshing || loading}
          >
            {refreshing ? "检测中…" : "刷新检测"}
          </button>
        </div>
      </div>

      {tab === "all" && (
        <div className="adm-llm-routing-panel">
          <div className="adm-llm-routing-head">
            <strong>Agent / 文本 LLM 分流</strong>
            <span className="adm-llm-routing-hint">
              控制智能划分、画布 Agent、剧本生成等后台文本任务；图/视频仍由用户在画布选择模型
            </span>
          </div>
          <div className="adm-llm-routing-modes">
            {ROUTING_MODES.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`adm-btn${routingMode === item.id ? " adm-btn--primary" : ""}`}
                disabled={routingLoading}
                onClick={() => handleRoutingModeChange(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <p className="adm-llm-routing-desc">
            {routingMode === "fixed" &&
              "始终使用「默认」文本模型；未设置默认时使用第一个已启用模型。"}
            {routingMode === "cheapest" &&
              "在已启用文本模型中选择输入单价最低的模型（需填写单价）。"}
            {routingMode === "balanced" &&
              "按 score = 近24h tokens × (单价/最低单价) 选最低者，兼顾成本与负载。"}
          </p>
        </div>
      )}

      {err && (
        <div
          style={{
            color: "var(--adm-danger)",
            background: "rgba(239,68,68,0.1)",
            padding: "10px 14px",
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
          }}
        >
          {err}
        </div>
      )}

      {loading ? (
        <div className="adm-loading">加载模型列表…</div>
      ) : filteredModels.length === 0 ? (
        <div className="adm-empty">当前分类暂无模型</div>
      ) : (
        <div className="adm-model-grid">
          {filteredModels.map((m) => (
            <ModelCard
              key={m.id}
              model={m}
              toggling={toggling}
              testing={keyTesting === m.id}
              testResult={testResults[m.id]}
              settingDefault={settingDefault === m.id}
              onToggle={handleToggle}
              onEdit={() => {
                setDrawerMode("edit")
                setEditingModel(m)
                setDrawerOpen(true)
              }}
              onDelete={() => handleDelete(m.id)}
              onTest={() => handleTest(m.id)}
              onSetDefault={() => handleSetDefault(m.id)}
            />
          ))}
        </div>
      )}

      <ModelDrawer
        open={drawerOpen}
        mode={drawerMode}
        model={editingModel}
        onClose={() => setDrawerOpen(false)}
        onSaved={async () => {
          setDrawerOpen(false)
          await loadModels()
        }}
      />
    </div>
  )
}

function ModelCard({
  model: m,
  toggling,
  testing,
  testResult,
  settingDefault,
  onToggle,
  onEdit,
  onDelete,
  onTest,
  onSetDefault,
}) {
  const isLocal = m.type === "local"
  const isTextApi = m.category === "text" && m.type === "api"

  return (
    <article className={`adm-model-card${isLocal ? " adm-model-card--local" : ""}`}>
      <div className="adm-model-card-top">
        <div>
          <h4>{m.display_name}</h4>
          <span className="adm-badge adm-badge--user">{CATEGORY_LABEL[m.category]}</span>
          {m.is_default_text && (
            <span className="adm-badge adm-badge--default" style={{ marginLeft: 6 }}>
              默认 Agent
            </span>
          )}
          {isLocal && (
            <span className="adm-badge" style={{ marginLeft: 6 }}>自动识别</span>
          )}
        </div>
        <span className={m.available ? "adm-dot ok" : "adm-dot fail"}>
          {m.available ? "● 可用" : "● 不可用"}
        </span>
      </div>
      {!isLocal && (
        <p className="adm-model-meta">
          {m.provider || "—"} · {TYPE_LABEL[m.type] || m.type}
          {m.api_model_name && m.api_model_name !== m.id && (
            <> · 调用名 {m.api_model_name}</>
          )}
        </p>
      )}
      <p className="adm-model-sub">
        {isLocal
          ? (m.comfyui_file || "未匹配到 ComfyUI 文件")
          : (m.api_key_masked || "未配置 API Key")}
      </p>
      {isTextApi && (
        <p className="adm-model-meta">
          近 24h：{(m.usage_24h_tokens ?? 0).toLocaleString()} tokens
          {m.input_price_per_million != null && (
            <> · 单价 ¥{m.input_price_per_million}/百万 tokens</>
          )}
        </p>
      )}

      <div className="adm-model-toggle">
        <button
          className={`adm-toggle${m.enabled ? " adm-toggle--on" : ""}`}
          onClick={() => onToggle(m.id, m.enabled)}
          disabled={toggling === m.id}
          title={m.enabled ? "点击关闭" : "点击开启"}
        >
          <span className="adm-toggle-thumb" />
        </button>
      </div>

      {!isLocal && (
        <div className="adm-model-actions">
          {isTextApi && m.enabled && !m.is_default_text && (
            <button
              className="adm-btn"
              type="button"
              onClick={onSetDefault}
              disabled={settingDefault}
            >
              {settingDefault ? "设置中…" : "设为默认"}
            </button>
          )}
          <button className="adm-btn" type="button" onClick={onEdit}>编辑</button>
          <button className="adm-btn" type="button" onClick={onTest} disabled={testing}>
            {testing ? "测试中…" : "测试连接"}
          </button>
          <button className="adm-btn adm-btn--danger" type="button" onClick={onDelete}>删除</button>
        </div>
      )}
      {isLocal && (
        <div className="adm-model-actions">
          <button className="adm-btn" type="button" onClick={onEdit}>启用设置</button>
        </div>
      )}
      {!isLocal && testResult && (
        <p
          style={{
            marginTop: 8,
            fontSize: 12,
            color: testResult.ok ? "var(--adm-success)" : "var(--adm-danger)",
          }}
        >
          {testResult.ok ? `✓ ${testResult.latency_ms}ms` : `✗ ${testResult.error || "连接失败"}`}
        </p>
      )}
    </article>
  )
}
