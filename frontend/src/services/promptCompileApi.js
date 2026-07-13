import api from "./api"

/** Prompt Compiler：聚合 scene / character / style → model_target 专用 prompt */
export async function compilePrompt({
  scene_desc = "",
  character_refs = [],
  style_preset = "",
  model_target = "flux",
  trace_id = null,
  camera_move = "auto",
  shot_scale = "auto",
}) {
  const res = await api.post("/api/prompt/compile", {
    scene_desc,
    character_refs,
    style_preset,
    model_target,
    trace_id,
    camera_move: camera_move || "auto",
    shot_scale: shot_scale || "auto",
  })
  return res.data
}

export function modelTargetForVideo(modelId = "") {
  const id = String(modelId || "").toLowerCase()
  if (id.includes("i2v") || id === "wan-i2v") return "wan-i2v"
  if (id.includes("wan")) return "wan-t2v"
  return "wan-t2v"
}

export function modelTargetForImage(modelId = "") {
  const id = String(modelId || "").toLowerCase()
  if (id.includes("flux")) return "flux"
  return "flux"
}
