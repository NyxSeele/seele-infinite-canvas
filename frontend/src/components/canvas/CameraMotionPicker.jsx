import "./CameraMotionPicker.css"

export const CAMERA_MOVE_OPTIONS = [
  { id: "auto", label: "自动", hint: "" },
  { id: "push_in", label: "推镜", hint: "→" },
  { id: "pull_out", label: "拉镜", hint: "←" },
  { id: "pan", label: "摇镜", hint: "↔" },
  { id: "track", label: "跟镜", hint: "↗" },
  { id: "static", label: "固定", hint: "·" },
]

export const SHOT_SCALE_OPTIONS = [
  { id: "auto", label: "自动" },
  { id: "close", label: "近景" },
  { id: "medium", label: "中景" },
  { id: "wide", label: "远景" },
  { id: "full", label: "全景" },
]

const sp = (e) => e.stopPropagation()

function ChipRow({ label, options, value, onSelect, disabled }) {
  return (
    <div className="cmp-row nodrag nopan">
      <span className="cmp-row-label">{label}</span>
      <div className="cmp-chips" role="group" aria-label={label}>
        {options.map((opt) => {
          const active = value === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              className={`cmp-chip nodrag nopan${active ? " cmp-chip--active" : ""}`}
              disabled={disabled}
              aria-pressed={active}
              title={opt.hint ? `${opt.label} ${opt.hint}` : opt.label}
              onClick={(e) => {
                sp(e)
                if (!disabled && !active) onSelect(opt.id)
              }}
              onPointerDown={sp}
            >
              {opt.hint ? <span className="cmp-chip-hint" aria-hidden>{opt.hint}</span> : null}
              <span>{opt.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/**
 * G33: 视频卡运镜 / 景别 pill 选择器（与画风 VideoStylePicker 分离）。
 */
export default function CameraMotionPicker({
  cameraMove = "auto",
  shotScale = "auto",
  onChange,
  disabled = false,
  readOnly = false,
}) {
  const locked = disabled || readOnly
  const move = CAMERA_MOVE_OPTIONS.some((o) => o.id === cameraMove) ? cameraMove : "auto"
  const scale = SHOT_SCALE_OPTIONS.some((o) => o.id === shotScale) ? shotScale : "auto"

  const emit = (next) => {
    if (locked || typeof onChange !== "function") return
    const cameraMoveNext = next.cameraMove ?? move
    const shotScaleNext = next.shotScale ?? scale
    const samplingProfile = cameraMoveNext !== "auto" ? "quality" : "fast"
    onChange({
      cameraMove: cameraMoveNext,
      shotScale: shotScaleNext,
      samplingProfile,
    })
  }

  return (
    <div className="cmp-wrap nodrag nopan" onPointerDown={sp}>
      <ChipRow
        label="运镜"
        options={CAMERA_MOVE_OPTIONS}
        value={move}
        disabled={locked}
        onSelect={(id) => emit({ cameraMove: id })}
      />
      <ChipRow
        label="景别"
        options={SHOT_SCALE_OPTIONS}
        value={scale}
        disabled={locked}
        onSelect={(id) => emit({ shotScale: id })}
      />
    </div>
  )
}
