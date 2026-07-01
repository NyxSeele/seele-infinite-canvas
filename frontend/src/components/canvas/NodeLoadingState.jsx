import { useLocale } from "../../utils/locale"
import "./NodeLoadingState.css"

export default function NodeLoadingState({ message }) {
  const { t } = useLocale()
  const text = message ?? t("canvas.gen.generating")
  return (
    <div className="node-loading-state" aria-live="polite">
      <div className="node-loading-spinner" aria-hidden />
      <span className="node-loading-text">{text}</span>
    </div>
  )
}
