import { useState } from "react"
import { Handle, Position } from "reactflow"
import { useCanvasActions } from "./CanvasActionsContext"
import "./CanvasShared.css"

const TGT_STYLE = {
  position: "absolute",
  top: "50%",
  left: -1,
  width: 1,
  height: 1,
  minWidth: 1,
  minHeight: 1,
  background: "transparent",
  border: "none",
  opacity: 0,
  transform: "translateY(-50%)",
  zIndex: 25,
}

/** 文本工作流节点左右加号 + 拖线锚点（与 GenerationCardNode 一致） */
export default function TextWorkflowEdgePlugs({ nodeId, nodeType, disabled = false }) {
  const canvasActions = useCanvasActions()
  const [leftVisible, setLeftVisible] = useState(false)
  const [rightVisible, setRightVisible] = useState(false)

  if (disabled) return null

  return (
    <>
      <Handle type="target" position={Position.Left} id="tgt" style={TGT_STYLE} />
      <Handle
        type="source"
        position={Position.Left}
        id="src-left"
        className="gn2-edge-handle gn2-edge-handle--left"
        onMouseEnter={() => setLeftVisible(true)}
        onMouseLeave={() => setLeftVisible(false)}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="src-right"
        className="gn2-edge-handle gn2-edge-handle--right"
        onMouseEnter={() => setRightVisible(true)}
        onMouseLeave={() => setRightVisible(false)}
      />

      <div
        className={`gn2-plus-left-zone nodrag${leftVisible ? " gn2-plus-zone--visible" : ""}`}
        onMouseEnter={() => setLeftVisible(true)}
        onMouseLeave={() => setLeftVisible(false)}
        onClick={(e) => {
          e.stopPropagation()
          canvasActions?.openPickerAt(e.clientX - 20, e.clientY, {
            toLeft: true,
            targetNodeId: nodeId,
          })
        }}
      >
        <div className="gn2-plus-btn-visual">+</div>
      </div>

      <div
        className={`gn2-plus-right-zone nodrag${rightVisible ? " gn2-plus-zone--visible" : ""}`}
        onMouseEnter={() => setRightVisible(true)}
        onMouseLeave={() => setRightVisible(false)}
        onClick={(e) => {
          e.stopPropagation()
          canvasActions?.openPickerAt(e.clientX + 20, e.clientY, {
            fromEdge: true,
            sourceNodeId: nodeId,
            sourceNodeType: nodeType,
          })
        }}
      >
        <div className="gn2-plus-btn-visual">+</div>
      </div>
    </>
  )
}
