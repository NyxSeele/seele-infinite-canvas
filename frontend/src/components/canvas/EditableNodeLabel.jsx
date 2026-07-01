import { useCallback, useEffect, useRef, useState } from "react"
import { useLocale } from "../../utils/locale"
import "./EditableNodeLabel.css"

const PencilIcon = () => (
  <svg width="11" height="11" viewBox="0 0 11 11" fill="none" aria-hidden>
    <path
      d="M7.2 1.8l1 1-5.4 5.4H1.8V7.2L7.2 1.8z"
      stroke="currentColor"
      strokeWidth="1.1"
      strokeLinejoin="round"
    />
    <path d="M6.5 2.5l1 1" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
  </svg>
)

/**
 * 可编辑节点标题，名称存于 data.label，通过 data.onUpdate 同步。
 */
export default function EditableNodeLabel({ nodeId, data, defaultLabel, className = "" }) {
  const { t } = useLocale()
  const resolvedLabel = (data.label && String(data.label).trim()) || defaultLabel
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(resolvedLabel)
  const savedRef = useRef(resolvedLabel)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!editing) {
      const next = (data.label && String(data.label).trim()) || defaultLabel
      setDraft(next)
      savedRef.current = next
    }
  }, [data.label, defaultLabel, editing])

  useEffect(() => {
    if (!editing || !inputRef.current) return
    inputRef.current.focus()
    inputRef.current.select()
  }, [editing])

  const startEdit = useCallback((e) => {
    e?.stopPropagation?.()
    setDraft(savedRef.current)
    setEditing(true)
  }, [])

  const cancelEdit = useCallback(() => {
    setDraft(savedRef.current)
    setEditing(false)
  }, [])

  const commitEdit = useCallback(() => {
    const trimmed = draft.trim()
    if (!trimmed) {
      cancelEdit()
      return
    }
    if (trimmed !== savedRef.current) {
      data.onUpdate?.(nodeId, { label: trimmed })
      savedRef.current = trimmed
    }
    setEditing(false)
  }, [draft, cancelEdit, data, nodeId])

  const handleKeyDown = useCallback((e) => {
    e.stopPropagation()
    if (e.key === "Enter") {
      e.preventDefault()
      commitEdit()
    } else if (e.key === "Escape") {
      e.preventDefault()
      cancelEdit()
    }
  }, [commitEdit, cancelEdit])

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        className={`node-label-input nodrag nopan ${className}`.trim()}
        value={draft}
        size={Math.max(draft.length, 2)}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commitEdit}
        onKeyDown={handleKeyDown}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      />
    )
  }

  return (
    <span className={`node-label-editable ${className}`.trim()}>
      <span
        className="node-label-editable-text"
        onDoubleClick={startEdit}
      >
        {resolvedLabel}
      </span>
      <button
        type="button"
        className="node-label-edit-btn nodrag nopan"
        aria-label={t("canvas.image.editName")}
        onClick={startEdit}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <PencilIcon />
      </button>
    </span>
  )
}
