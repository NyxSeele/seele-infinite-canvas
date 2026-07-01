import { useLocale } from "../../utils/locale"

/** 生成中「停止」按钮，用于图像/视频/文本卡片 */
export default function GenerationStopButton({ onStop, className = "" }) {
  const { t } = useLocale()
  if (!onStop) return null
  return (
    <button
      type="button"
      className={`gn2-stop-btn nodrag nopan ${className}`.trim()}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation()
        onStop()
      }}
    >
      {t("canvas.gen.stop")}
    </button>
  )
}
