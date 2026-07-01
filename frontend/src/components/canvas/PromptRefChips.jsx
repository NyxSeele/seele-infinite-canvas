import "./PromptRefChips.css"

const sp = (e) => e.stopPropagation()

/**
 * Prompt Bar 输入区上方：参考图 + @ 引用 chips（去重展示）
 */
export default function PromptRefChips({ items = [], onRemove }) {
  if (!items.length) return null

  return (
    <div className="prompt-ref-chips nodrag nopan" onPointerDown={sp}>
      {items.map((item) => (
        <div key={item.key} className="prompt-ref-chip" title={item.label}>
          {item.imageUrl ? (
            <img src={item.imageUrl} alt="" draggable={false} />
          ) : (
            <span className="prompt-ref-chip-fallback">{item.label?.slice(0, 1) || "?"}</span>
          )}
          <span className="prompt-ref-chip-label">{item.label}</span>
          {onRemove && item.removable !== false ? (
            <button
              type="button"
              className="prompt-ref-chip-remove nodrag"
              onPointerDown={sp}
              onClick={(e) => {
                sp(e)
                onRemove(item)
              }}
              aria-label="Remove"
            >
              ×
            </button>
          ) : null}
        </div>
      ))}
    </div>
  )
}
