import { TEXT_MODES } from "./nodeHelpers"
import { beatCardHasBeatPrompts, beatCardStoryboardReady } from "./scriptBeatCard"
import {
  asKeyframeArray,
  keyframeText,
  rowDirectImageReady,
  rowDirectVideoReady,
  rowHasBeatPrompts,
  rowStoryboardReady,
  rowVideoReady,
} from "./scriptTableKeyframes"

const MAX_SNAPSHOT_NODES = 50
const MAX_CONTENT_LEN = 150
const MAX_ROW_PLOT_LEN = 400
const MAX_KF_PROMPT_LEN = 100

/** React Flow 类型 → Agent Prompt 约定类型 */
const FLOW_TO_AGENT_TYPE = {
  "text-response": "text_response",
  "text-note": "text_note",
  "image-gen": "image",
  "script-table": "script_table",
  outline: "outline",
  "video-gen": "video",
  "shot-script": "shot_script",
}

function toAgentNodeType(flowType) {
  return FLOW_TO_AGENT_TYPE[flowType] || flowType
}

function truncate(str) {
  if (!str) return ""
  return str.length > MAX_CONTENT_LEN ? str.slice(0, MAX_CONTENT_LEN) + "..." : str
}

function nodeContentPreview(data, nodeType) {
  if (!data) return ""
  if (data.status === "generating" || data.loading) return "[生成中]"
  if (nodeType === "outline" && data.error) return `[失败] ${data.error}`
  return (
    data.content
    || data.text
    || data.prompt
    || (Array.isArray(data.scenes) ? data.scenes.map((s) => s.content || s.title).join(" ") : "")
    || ""
  )
}

export function serializeCanvasForAgent(nodes, edges, selectedNodeIds = []) {
  const selectedSet = new Set(selectedNodeIds)
  const selectedNodes = nodes.filter((n) => selectedSet.has(n.id))

  let snapshotNodes
  if (nodes.length <= MAX_SNAPSHOT_NODES) {
    snapshotNodes = nodes
  } else {
    const unselectedNodes = nodes
      .filter((n) => !selectedSet.has(n.id))
      .slice(0, Math.max(0, MAX_SNAPSHOT_NODES - selectedNodes.length))
    snapshotNodes = [...selectedNodes, ...unselectedNodes]
  }

  const omitted = Math.max(0, nodes.length - snapshotNodes.length)

  return {
    nodes: snapshotNodes.map((n) => {
      const agentType = toAgentNodeType(n.type)
      const base = {
        id: n.id,
        type: agentType,
        position: {
          x: Math.round(n.position?.x ?? 0),
          y: Math.round(n.position?.y ?? 0),
        },
        content_preview: truncate(nodeContentPreview(n.data, n.type)),
        label: n.data?.label || n.type,
      }
      if (n.type === "text-note") {
        const mode = n.data?.textMode === TEXT_MODES.CHAT ? "chat" : "screenplay"
        base.text_mode = mode
        base.intent = mode
      }
      if (n.type === "text-response" && n.data?.status) {
        base.status = n.data.status
      }
      if (n.type === "outline") {
        if (n.data?.loading) base.loading = true
        if (n.data?.linkedScriptTableId) {
          base.linked_script_table_id = n.data.linkedScriptTableId
        }
        if (Array.isArray(n.data?.scenes)) {
          base.scene_count = n.data.scenes.length
          base.scenes_preview = n.data.scenes.slice(0, 8).map((s, i) => ({
            index: i + 1,
            title: truncate(s.title || "", 40),
            content: truncate(s.content || "", 200),
          }))
          const charSet = new Set()
          for (const s of n.data.scenes) {
            const chars = s.characters
            if (Array.isArray(chars)) {
              for (const c of chars) {
                const name = typeof c === "string" ? c : c?.name
                if (name && String(name).trim()) charSet.add(String(name).trim())
              }
            }
          }
          if (charSet.size > 0) {
            base.characters_preview = [...charSet]
          }
        }
      }
      if (n.type === "script-table") {
        const rows = n.data?.rows || []
        base.row_count = rows.length
        base.loading = Boolean(n.data?.loading || n.data?.generatingFromOutline)
        if (n.data?.sourceOutlineId) {
          base.source_outline_id = n.data.sourceOutlineId
        }
        base.rows_summary = rows.map((r) => {
          const beatCard = r.beatCardNodeId
            ? nodes.find((bn) => bn.id === r.beatCardNodeId)
            : null
          const beatKfs = beatCard
            ? asKeyframeArray(beatCard.data?.keyframes)
            : asKeyframeArray(r.keyframes)
          return {
          id: r.id,
          shot_number: r.shotNumber ?? 1,
          plot_preview: truncate(r.prompt || r.description || "", MAX_ROW_PLOT_LEN),
          duration_sec: r.duration ?? 8,
          camera: truncate(r.camera || "", 60),
          atmosphere: truncate(r.atmosphereNote || "", 80),
          movement: truncate(r.movement || "", 40),
          lighting: truncate(r.lighting || "", 40),
          composition: truncate(r.composition || "", 40),
          color_grade: truncate(r.colorGrade || "", 40),
          lens: truncate(r.lens || "", 40),
          performance: truncate(r.performance || "", 60),
          sound_design: truncate(r.soundDesign || "", 60),
          sound_note: truncate(r.soundNote || "", 60),
          location_id: r.locationId || r.location_id || null,
          beat_card_node_id: r.beatCardNodeId || null,
          direct_image_ready: rowDirectImageReady(r),
          keyframe_count: beatKfs.length,
          beat_prompt_count: beatKfs.filter((kf) => keyframeText(kf)).length,
          has_beats: Boolean(r.beatCardNodeId) && beatCardHasBeatPrompts(beatCard?.data),
          beats_split_at: beatCard?.data?.beatsSplitAt || r.beatsSplitAt || null,
          storyboard_ready: rowDirectImageReady(r) || beatCardStoryboardReady(beatCard?.data),
          has_video: rowDirectVideoReady(r, nodes) || rowVideoReady(r, nodes),
          video_generating: Boolean(
            (r.directVideoGenNodeId || r.videoGenNodeId)
            && !rowDirectVideoReady(r, nodes)
            && !rowVideoReady(r, nodes)
            && nodes.some(
              (vn) =>
                (vn.id === r.directVideoGenNodeId || vn.id === r.videoGenNodeId)
                && vn.type === "video-gen"
                && (vn.data?.status === "generating" || vn.data?.status === "pending")
            )
          ),
          keyframes_summary: beatKfs.map((kf, ki) => ({
            index: ki + 1,
            label: kf.label || `格${ki + 1}`,
            status: kf.status || "idle",
            prompt: truncate(keyframeText(kf), MAX_KF_PROMPT_LEN),
            prompt_en: truncate(kf.promptEn || kf.prompt_en || "", 80),
            action_note: truncate(kf.actionNote || "", 40),
            has_image: Boolean(kf.resultUrl),
          })),
          status: r.directStatus || r.status || "idle",
        }})
        if (rows.length > 0 && !base.loading) {
          const beatDone = rows.filter((r) => r.beatCardNodeId).length
          base.content_preview = `分镜表 ${rows.length} 镜${beatDone ? `，${beatDone} 镜已拆节拍` : ""}`
        }
        const castLib = n.data?.castLibrary
        if (Array.isArray(castLib) && castLib.length > 0) {
          base.cast_library = castLib
            .filter((c) => c.type !== "scene")
            .map((c) => ({
            id: c.id,
            name: c.name,
            type: "character",
            has_image: Boolean(c.imageUrl),
            image_url: c.imageUrl || null,
            description: truncate(c.description || "", 120) || null,
            pending_image: !c.imageUrl,
          }))
        }
        const sceneLib = n.data?.sceneLibrary
        if (Array.isArray(sceneLib) && sceneLib.length > 0) {
          base.scene_library = sceneLib.map((s) => ({
            id: s.id,
            name: s.name,
            type: "scene",
            has_image: Boolean(s.imageUrl),
            image_url: s.imageUrl || null,
            description: truncate(s.description || "", 120) || null,
            pending_image: !s.imageUrl,
          }))
        }
      }
      return base
    }),
    edges: edges.map((e) => ({ source: e.source, target: e.target })),
    selected_node_ids: selectedNodeIds,
    total_node_count: nodes.length,
    snapshot_truncated: omitted > 0,
    omitted_node_count: omitted,
  }
}
