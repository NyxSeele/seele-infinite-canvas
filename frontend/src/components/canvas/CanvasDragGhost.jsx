import { ensureMediaUrl } from "../../utils/mediaTicket"
import { useLocale } from "../../utils/locale"

export default function CanvasDragGhost({ session }) {
  const { t } = useLocale()

  if (!session?.active) return null

  const preview = ensureMediaUrl(session.previewUrl || session.mediaUrl)

  return (
    <div
      className="canvas-drag-ghost"
      style={{
        left: session.x,
        top: session.y,
      }}
      aria-hidden
    >
      {session.kind === "video" ? (
        <video src={preview} className="canvas-drag-ghost__media" muted playsInline />
      ) : (
        <img src={preview} alt="" className="canvas-drag-ghost__media" draggable={false} />
      )}
      <span className="canvas-drag-ghost__hint">{t("canvas.drag.dropHint")}</span>
    </div>
  )
}
