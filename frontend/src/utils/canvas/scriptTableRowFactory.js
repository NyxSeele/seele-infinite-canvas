import { normalizeScriptRow } from "./scriptTableKeyframes"
import { applyQualityPresetToRow } from "./scriptQualityPresets"

function makeRowId() {
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function makeEmptyScriptRow(shotNumber = 1) {
  const duration = 8
  return normalizeScriptRow(
    applyQualityPresetToRow(
      {
        id: makeRowId(),
        shotNumber,
        duration,
        camera: "",
        movement: "",
        lighting: "",
        composition: "",
        colorGrade: "",
        lens: "",
        performance: "",
        soundDesign: "",
        soundNote: "",
        atmosphereNote: "",
        qualityPresetId: "",
        prompt: "",
        description: "",
        promptMentions: [],
        identityIds: [],
        keyframes: [],
        beatCardNodeId: null,
        directImageGenNodeId: null,
        directResultUrl: null,
        directStatus: "idle",
        directVideoGenNodeId: null,
        status: "idle",
        error: null,
      },
      "auto"
    )
  )
}
