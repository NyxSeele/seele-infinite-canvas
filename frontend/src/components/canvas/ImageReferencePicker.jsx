import { useEffect } from "react"
import { useCanvasStore } from "../../stores"
import { useLocale } from "../../utils/locale"
import "./ImageReferencePicker.css"

const sp = (e) => e.stopPropagation()

export default function ImageReferencePicker({
  open,
  images = [],
  selectedRef,
  hoverRef,
  onHover,
  onSelect,
  onConfirm,
  onCancel,
  onReset,
}) {
  const { t } = useLocale()
  const theme = useCanvasStore((s) => s.theme)

  useEffect(() => {
    if (!open) return undefined
    onReset?.()
    return () => onReset?.()
  }, [open, onReset])

  if (!open) return null

  return (
    <div
      className={`img-ref-picker rf-page rf-page--${theme} nodrag nopan`}
      onPointerDown={sp}
      onClick={sp}
      onMouseLeave={() => onHover?.(null)}
    >
      <div className="img-ref-picker-header">
        <span className="img-ref-picker-title">{t("canvas.ref.pickTitle")}</span>
        <button type="button" className="img-ref-picker-cancel nodrag" onClick={onCancel}>
          {t("canvas.common.cancel")}
        </button>
      </div>

      {images.length === 0 ? (
        <div className="img-ref-picker-empty">{t("canvas.ref.noImages")}</div>
      ) : (
        <div className="img-ref-picker-grid">
          {images.map((img) => {
            const isSelected = selectedRef?.imageId === img.imageId
            const isHover = !isSelected && hoverRef?.imageId === img.imageId
            return (
              <button
                key={img.imageId}
                type="button"
                className={`img-ref-picker-cell nodrag${isSelected ? " img-ref-picker-cell--selected" : ""}${isHover ? " img-ref-picker-cell--hover" : ""}`}
                onMouseEnter={() => onHover?.(img)}
                onMouseLeave={() => onHover?.(null)}
                onClick={(e) => {
                  e.stopPropagation()
                  onSelect?.(img)
                }}
              >
                <img
                  src={img.imageUrl}
                  alt=""
                  draggable={false}
                  onDragStart={(e) => e.preventDefault()}
                  style={{ pointerEvents: "none" }}
                />
                <span className="img-ref-picker-cell-label">{img.label}</span>
              </button>
            )
          })}
        </div>
      )}

      <div className="img-ref-picker-footer">
        <button
          type="button"
          className="img-ref-picker-confirm nodrag"
          disabled={!selectedRef}
          onClick={() => selectedRef && onConfirm?.(selectedRef)}
        >
          {t("canvas.ref.confirmAdd")}
        </button>
      </div>
    </div>
  )
}
