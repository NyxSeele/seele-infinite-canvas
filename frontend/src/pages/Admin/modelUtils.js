/** 将 GET /api/admin/models 响应统一为 { id, display_name, ... } */
export function normalizeAdminModel(raw) {
  if (!raw || typeof raw !== "object") return null
  const id = raw.id ?? raw.model_id
  if (!id) return null
  return {
    ...raw,
    id: String(id),
    display_name: raw.display_name ?? raw.name ?? String(id),
    category: raw.category ?? "text",
    type: raw.type ?? "api",
    provider: raw.provider ?? null,
    api_base: raw.api_base ?? null,
    model_string: raw.model_string ?? raw.api_model_name ?? null,
    api_model_name: raw.api_model_name ?? raw.model_string ?? null,
    comfyui_file: raw.comfyui_file ?? null,
    enabled: !!raw.enabled,
    available: !!raw.available,
    api_key_masked: raw.api_key_masked ?? null,
    is_default_text: !!raw.is_default_text,
    input_price_per_million:
      raw.input_price_per_million != null ? Number(raw.input_price_per_million) : null,
    usage_24h_tokens: Number(raw.usage_24h_tokens ?? 0),
  }
}
