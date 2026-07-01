import { useEffect, useMemo, useState } from "react"
import { message } from "antd"
import api from "../../services/api"
import { formatApiError } from "./formatApiError.js"

const MODEL_ID_RE = /^[A-Za-z0-9-]+$/
const MODEL_ID_INVALID_MSG =
  "模型ID仅作为内部标识，请填写字母数字和连字符；官方模型名请填写在模型调用名字段。"
const OFFICIAL_MODEL_NAME_RE = /[.:_]/

function inferApiModelName({ id, displayName, apiModelName }) {
  const modelId = (id || "").trim()
  const display = (displayName || "").trim()
  const explicit = (apiModelName || "").trim()
  if (explicit && explicit !== modelId) return explicit
  if (display && display !== modelId && OFFICIAL_MODEL_NAME_RE.test(display)) return display
  return explicit || modelId
}

function slugifyModelId(raw) {
  return (raw || "")
    .trim()
    .replace(/[.:_]+/g, "-")
    .replace(/[^A-Za-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
}

function normalizeApiBase(url) {
  const trimmed = (url || "").trim().replace(/\/+$/, "")
  if (!trimmed) return trimmed
  const lower = trimmed.toLowerCase()
  if (!lower.includes("dashscope.aliyuncs.com") && !lower.includes("maas.aliyuncs.com")) {
    return trimmed
  }
  if (trimmed.endsWith("/api/v1")) {
    return `${trimmed.slice(0, -"/api/v1".length)}/compatible-mode/v1`
  }
  if (trimmed.endsWith("/api")) {
    return `${trimmed}/compatible-mode/v1`
  }
  if (!lower.includes("compatible-mode") && !lower.endsWith("/v1")) {
    return `${trimmed}/compatible-mode/v1`
  }
  return trimmed
}

function resolveCreateFields(form) {
  let modelId = form.id.trim()
  let displayName = form.display_name.trim()
  let apiModelName = form.api_model_name.trim()
  let officialFromId = null

  if (modelId && !MODEL_ID_RE.test(modelId)) {
    officialFromId = modelId
    modelId = slugifyModelId(modelId)
    if (!apiModelName) apiModelName = officialFromId
    if (!displayName) displayName = officialFromId
  }

  const resolvedApiName = inferApiModelName({
    id: modelId,
    displayName,
    apiModelName,
  })

  return {
    modelId,
    displayName,
    apiModelName: resolvedApiName,
    apiBase: normalizeApiBase(form.api_base),
  }
}

function suggestApiModelNameFromDisplay(displayName, modelId, currentApiName) {
  const display = (displayName || "").trim()
  const id = (modelId || "").trim()
  const current = (currentApiName || "").trim()
  if (!display || display === id || !OFFICIAL_MODEL_NAME_RE.test(display)) return current
  if (!current || current === id) return display
  return current
}

const EMPTY_FORM = {
  id: "",
  display_name: "",
  category: "text",
  type: "api",
  provider: "",
  api_base: "",
  api_key: "",
  api_model_name: "",
  enabled: false,
  input_price_per_million: "",
}

export default function ModelDrawer({
  open,
  mode,
  model,
  onClose,
  onSaved,
}) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState(null)

  const isEdit = mode === "edit"
  const isLocal = isEdit && model?.type === "local"

  useEffect(() => {
    if (!open) return
    if (isEdit && model) {
      const modelId = model.id || ""
      const displayName = model.display_name || ""
      const storedApiName = model.api_model_name || model.model_string || ""
      setForm({
        id: modelId,
        display_name: displayName,
        category: model.category || "text",
        type: model.type || "api",
        provider: model.provider || "",
        api_base: model.api_base || "",
        api_key: "",
        api_model_name: inferApiModelName({
          id: modelId,
          displayName,
          apiModelName: storedApiName,
        }),
        enabled: !!model.enabled,
        input_price_per_million:
          model.input_price_per_million != null ? String(model.input_price_per_million) : "",
      })
    } else {
      setForm(EMPTY_FORM)
    }
    setTestResult(null)
  }, [open, isEdit, model])

  const drawerTitle = isLocal
    ? "本地模型（自动识别）"
    : isEdit
      ? "编辑 API 模型"
      : "添加 API 模型"

  const idWillAutoSplit = useMemo(() => {
    const id = form.id.trim()
    return !isEdit && id.length > 0 && !MODEL_ID_RE.test(id)
  }, [form.id, isEdit])

  const previewModelId = useMemo(() => {
    if (!idWillAutoSplit) return form.id.trim()
    return slugifyModelId(form.id)
  }, [form.id, idWillAutoSplit])

  const canSubmit = useMemo(() => {
    if (isLocal) return true
    if (!form.id.trim()) return false
    if (!form.display_name.trim() && !idWillAutoSplit) return false
    if (!isEdit && !previewModelId) return false
    if (!form.api_base.trim()) return false
    return true
  }, [form, isLocal, previewModelId, isEdit, idWillAutoSplit])

  const updateField = (key, value) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value }
      if (key === "display_name") {
        next.api_model_name = suggestApiModelNameFromDisplay(
          value,
          next.id,
          next.api_model_name
        )
      }
      return next
    })
  }

  const resolvedApiModelName = useMemo(
    () =>
      inferApiModelName({
        id: form.id,
        displayName: form.display_name,
        apiModelName: form.api_model_name,
      }),
    [form.id, form.display_name, form.api_model_name]
  )

  const apiNameLooksWrong = useMemo(() => {
    const id = form.id.trim()
    const explicit = form.api_model_name.trim()
    const display = form.display_name.trim()
    return (
      !!id &&
      !!display &&
      OFFICIAL_MODEL_NAME_RE.test(display) &&
      display !== id &&
      (!explicit || explicit === id)
    )
  }, [form.id, form.display_name, form.api_model_name])

  const submit = async () => {
    if (!canSubmit || saving) return
    const resolved = resolveCreateFields(form)
    if (!isEdit && (!resolved.modelId || !MODEL_ID_RE.test(resolved.modelId))) {
      message.error(MODEL_ID_INVALID_MSG)
      return
    }
    setSaving(true)
    setTestResult(null)
    try {
      if (isLocal) {
        await api.put(`/api/admin/models/${form.id}`, { enabled: !!form.enabled })
        message.success("已更新启用状态")
        onSaved?.()
        return
      }

      const payload = {
        display_name: resolved.displayName,
        category: form.category,
        type: "api",
        provider: form.provider.trim() || null,
        api_base: resolved.apiBase,
        api_model_name: resolved.apiModelName,
        enabled: !!form.enabled,
      }
      if (form.category === "text") {
        const priceRaw = String(form.input_price_per_million ?? "").trim()
        payload.input_price_per_million = priceRaw ? Number(priceRaw) : null
      }
      if (form.api_key.trim()) {
        payload.api_key = form.api_key.trim()
      }

      const res = isEdit
        ? await api.put(`/api/admin/models/${form.id}`, payload)
        : await api.post("/api/admin/models", { ...payload, id: resolved.modelId })

      if (!isEdit && payload.api_key) {
        const t = await api.post(`/api/admin/models/${resolved.modelId}/test-connection`)
        setTestResult(t.data)
      }
      message.success(isEdit ? "模型已更新" : "模型已创建")
      onSaved?.(res.data)
    } catch (err) {
      message.error(formatApiError(err.response?.data?.detail, "保存失败"))
    } finally {
      setSaving(false)
    }
  }

  if (!open) return null

  return (
    <div className="adm-drawer-mask" onClick={onClose}>
      <aside className="adm-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="adm-drawer-head">
          <h3>{drawerTitle}</h3>
          <button type="button" className="adm-btn" onClick={onClose}>关闭</button>
        </div>

        <form
          id="adm-model-drawer-form"
          className="adm-drawer-body"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          {isLocal ? (
            <>
              <p className="adm-field-hint" style={{ marginBottom: 16 }}>
                该模型由 ComfyUI 自动扫描识别，仅可调整启用状态。文件名：
                <strong> {model?.comfyui_file || "—"}</strong>
              </p>
              <div className="adm-field">
                <label>启用</label>
                <button
                  type="button"
                  className={`adm-toggle${form.enabled ? " adm-toggle--on" : ""}`}
                  onClick={() => updateField("enabled", !form.enabled)}
                >
                  <span className="adm-toggle-thumb" />
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="adm-field">
                <label>生成类别（必填）</label>
                <div className="adm-radio-group">
                  {["text", "image", "video"].map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      className={`adm-radio-btn${form.category === cat ? " active" : ""}`}
                      onClick={() => updateField("category", cat)}
                    >
                      {cat === "text" ? "文本" : cat === "image" ? "图像" : "视频"}
                    </button>
                  ))}
                </div>
              </div>

              <div className="adm-field">
                <label>模型 ID（必填）</label>
                <input
                  placeholder="可填 qwen3-6-plus，或直接粘贴官方名 qwen3.6-plus"
                  value={form.id}
                  onChange={(e) => updateField("id", e.target.value)}
                  disabled={isEdit}
                />
                <p className="adm-field-hint">
                  系统内部标识；可直接粘贴官方模型名，保存时自动生成连字符版 ID
                </p>
                {idWillAutoSplit && previewModelId && (
                  <p className="adm-field-hint" style={{ color: "var(--adm-warning, #f59e0b)" }}>
                    将保存为内部 ID：<strong>{previewModelId}</strong>，调用名：
                    <strong> {form.id.trim()}</strong>
                  </p>
                )}
              </div>

              <div className="adm-field">
                <label>显示名称（必填）</label>
                <input
                  placeholder="千问 Turbo"
                  value={form.display_name}
                  onChange={(e) => updateField("display_name", e.target.value)}
                />
              </div>

              <div className="adm-field">
                <label>供应商（选填）</label>
                <input
                  placeholder="qwen / openai / anthropic"
                  value={form.provider}
                  onChange={(e) => updateField("provider", e.target.value)}
                />
              </div>

              <div className="adm-field">
                <label>API Base URL（必填）</label>
                <input
                  placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
                  value={form.api_base}
                  onChange={(e) => updateField("api_base", e.target.value)}
                />
                <p className="adm-field-hint">
                  OpenAI 兼容地址；百炼控制台若给 /api/v1，保存时会自动改为 /compatible-mode/v1
                </p>
                {form.api_base.trim() &&
                  normalizeApiBase(form.api_base) !== form.api_base.trim().replace(/\/+$/, "") && (
                    <p className="adm-field-hint">
                      将使用：<strong>{normalizeApiBase(form.api_base)}</strong>
                    </p>
                  )}
              </div>

              <div className="adm-field">
                <label>API Key（选填）</label>
                <input
                  type="password"
                  placeholder="sk-..."
                  value={form.api_key}
                  onChange={(e) => updateField("api_key", e.target.value)}
                />
                <p className="adm-field-hint">可以先留空，创建后再录入</p>
              </div>

              <div className="adm-field">
                <label>模型调用名（选填）</label>
                <input
                  placeholder="qwen3.6-plus-2026-04-02"
                  value={form.api_model_name}
                  onChange={(e) => updateField("api_model_name", e.target.value)}
                />
                <p className="adm-field-hint">
                  官方模型名（可含 . _ : 等），实际传给 API；不填则尝试用显示名称，否则与模型 ID 相同
                </p>
                {apiNameLooksWrong && (
                  <p className="adm-field-hint" style={{ color: "var(--adm-warning, #f59e0b)" }}>
                    显示名称像官方模型名，但调用名仍是内部 ID。保存时将自动使用：
                    <strong> {resolvedApiModelName}</strong>
                  </p>
                )}
                {!apiNameLooksWrong && resolvedApiModelName && form.id.trim() && (
                  <p className="adm-field-hint">
                    实际请求调用名：<strong>{resolvedApiModelName}</strong>
                  </p>
                )}
              </div>

              {form.category === "text" && (
                <div className="adm-field">
                  <label>输入单价（元 / 百万 tokens，选填）</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="例如 2.5"
                    value={form.input_price_per_million}
                    onChange={(e) => updateField("input_price_per_million", e.target.value)}
                  />
                  <p className="adm-field-hint">
                    用于 Admin 分流策略（低价优先 / 均衡分流）；不填则仅「固定默认」模式可靠
                  </p>
                </div>
              )}

              <div className="adm-field">
                <label>立即启用</label>
                <button
                  type="button"
                  className={`adm-toggle${form.enabled ? " adm-toggle--on" : ""}`}
                  onClick={() => updateField("enabled", !form.enabled)}
                >
                  <span className="adm-toggle-thumb" />
                </button>
              </div>
            </>
          )}

          {testResult && (
            <p
              style={{
                color: testResult.ok ? "var(--adm-success)" : "var(--adm-danger)",
                fontSize: 13,
              }}
            >
              {testResult.ok
                ? `✓ 连接正常 (${testResult.latency_ms}ms)`
                : `✗ ${testResult.error || "连接失败"}`}
            </p>
          )}
        </form>

        <div className="adm-drawer-foot">
          <button type="button" className="adm-btn" onClick={onClose}>取消</button>
          <button
            type="submit"
            form="adm-model-drawer-form"
            className="adm-btn adm-btn--primary"
            disabled={!canSubmit || saving}
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </aside>
    </div>
  )
}
