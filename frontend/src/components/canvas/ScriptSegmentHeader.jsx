import { useLocale } from "../../utils/locale"
import "./ScriptSegmentHeader.css"

const sp = (e) => e.stopPropagation()

export default function ScriptSegmentHeader({ segment }) {
  const { t } = useLocale()

  if (!segment) return null

  const label = segment.title?.trim() || t("canvas.script.segmentTitle")

  return (
    <header className="st-segment-divider nodrag" onPointerDown={sp} aria-label={label}>
      <span className="st-segment-divider-line" aria-hidden />
      <span className="st-segment-divider-label">{label}</span>
      <span className="st-segment-divider-line" aria-hidden />
    </header>
  )
}
