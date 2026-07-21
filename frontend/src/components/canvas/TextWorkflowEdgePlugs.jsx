import { useState } from "react"
import { Handle, Position } from "reactflow"
import { useCanvasActions } from "./CanvasActionsContext"
import "./CanvasShared.css"

const TGT_CLASS = "gn2-edge-handle gn2-edge-handle--target"

/** 文本工作流节点左右加号 + 拖线锚点（与 GenerationCardNode 一致） */
export default function TextWorkflowEdgePlugs({ nodeId, nodeType, disabled = false, selected = false }) {
  const canvasActions = useCanvasActions()
  const [leftVisible, setLeftVisible] = useState(false)
  const [rightVisible, setRightVisible] = useState(false)
  const plusPinned = selected

  if (disabled) return null

  return (
    <>
      <Handle type="target" position={Position.Left} id="tgt" className={TGT_CLASS} />
      <Handle
        type="source"
        position={Position.Left}
        id="src-left"
        className="gn2-edge-handle gn2-edge-handle--left"
        onMouseEnter={() => setLeftVisible(true)}
        onMouseLeave={() => { if (!plusPinned) setLeftVisible(false) }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="src-right"
        className="gn2-edge-handle gn2-edge-handle--right"
        onMouseEnter={() => setRightVisible(true)}
        onMouseLeave={() => { if (!plusPinned) setRightVisible(false) }}
      />

      <div
        className={`gn2-plus-left-zone${leftVisible || plusPinned ? " gn2-plus-zone--visible" : ""}`}
        onMouseEnter={() => setLeftVisible(true)}
        onMouseLeave={() => { if (!plusPinned) setLeftVisible(false) }}
      >
        <div
          className="gn2-plus-btn-visual nodrag nopan"
          onClick={(e) => {
            e.stopPropagation()
            canvasActions?.openPickerAt(e.clientX - 20, e.clientY, {
              toLeft: true,
              targetNodeId: nodeId,
            })
          }}
        >
          +
        </div>
      </div>

      <div
        className={`gn2-plus-right-zone${rightVisible || plusPinned ? " gn2-plus-zone--visible" : ""}`}
        onMouseEnter={() => setRightVisible(true)}
        onMouseLeave={() => { if (!plusPinned) setRightVisible(false) }}
      >
        <div
          className="gn2-plus-btn-visual nodrag nopan"
          onClick={(e) => {
            e.stopPropagation()
            canvasActions?.openPickerAt(e.clientX + 20, e.clientY, {
              fromEdge: true,
              sourceNodeId: nodeId,
              sourceNodeType: nodeType,
            })
          }}
        >
          +
        </div>
      </div>
    </>
  )
}
