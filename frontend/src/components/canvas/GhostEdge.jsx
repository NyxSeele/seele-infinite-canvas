import { useState } from "react"
import { Position, useStore } from "reactflow"
import "./GhostEdge.css"

function buildPath(sourceX, sourceY, targetX, targetY, sourcePosition) {
  const dx = targetX - sourceX
  const offset = Math.max(dx * 0.45, 80)
  const fromLeft = sourcePosition === Position.Left
  const cp1x = fromLeft ? sourceX - offset : sourceX + offset
  const cp2x = fromLeft ? targetX + offset : targetX - offset
  return `M ${sourceX} ${sourceY} C ${cp1x} ${sourceY}, ${cp2x} ${targetY}, ${targetX} ${targetY}`
}

export default function GhostEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  source,
  target,
  style = {},
}) {
  const [hovered, setHovered] = useState(false)
  const edgePath = buildPath(sourceX, sourceY, targetX, targetY, sourcePosition)
  const nodeSelected = useStore((s) => {
    const src = s.nodeInternals.get(source)
    const tgt = s.nodeInternals.get(target)
    return !!(src?.selected || tgt?.selected)
  })

  return (
    <g
      className={`ghost-edge-group${nodeSelected ? ' ghost-edge-node-selected' : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Wide transparent stroke — hover hit area */}
      <path
        d={edgePath}
        stroke="transparent"
        strokeWidth={16}
        fill="none"
        style={{ pointerEvents: "stroke", cursor: "default" }}
      />
      {/* Glow bloom layer */}
      <path d={edgePath} className="ghost-edge-glow" />
      {/* Main visible line */}
      <path
        d={edgePath}
        className="ghost-edge-line"
        fill="none"
        style={style}
      />
    </g>
  )
}
