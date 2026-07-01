import { formatNodeEditMeta } from "../../utils/canvas/nodeEditMeta"
import "./NodeLastEditedMeta.css"

export default function NodeLastEditedMeta({ meta, className = "" }) {
  const text = formatNodeEditMeta(meta)
  if (!text) return null
  return (
    <span className={`node-last-edited${className ? ` ${className}` : ""}`} title={text}>
      {text}
    </span>
  )
}
