import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react"
import { createPortal } from "react-dom"
import {
  getMentionQueryAtSelection,
  insertMentionAtCaret,
  renderMentionContent,
  serializeMentionEditor,
} from "./promptMentions"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import "./MentionTextarea.css"

const MentionTextarea = forwardRef(function MentionTextarea(
  {
    className = "",
    placeholder = "",
    value = "",
    mentions = [],
    expanded = false,
    getMentionImage,
    onChange,
    onMentionQuery,
    onPointerDown,
    onMouseDown,
    onFocus,
    onBlur,
    onClick,
    onKeyDown,
    disabled = false,
  },
  ref
) {
  const editorRef = useRef(null)
  const syncingRef = useRef(false)
  const selectedMentionRef = useRef(null)
  const [hoverPreview, setHoverPreview] = useState(null)

  const emitChange = useCallback(() => {
    const root = editorRef.current
    if (!root || syncingRef.current) return
    const { text, mentions: nextMentions } = serializeMentionEditor(root)
    onChange?.({ text, mentions: nextMentions })
  }, [onChange])

  const updateMentionQuery = useCallback(() => {
    const root = editorRef.current
    const q = getMentionQueryAtSelection(root)
    onMentionQuery?.(q ? { active: true, query: q.query } : { active: false, query: "" })
  }, [onMentionQuery])

  useImperativeHandle(ref, () => ({
    insertMention(candidate) {
      insertMentionAtCaret(editorRef.current, candidate)
      selectedMentionRef.current = null
      emitChange()
      updateMentionQuery()
    },
    focus() {
      editorRef.current?.focus()
    },
  }))

  useEffect(() => {
    const root = editorRef.current
    if (!root) return
    const { text } = serializeMentionEditor(root)
    if (text === (value || "") && mentions?.length >= 0) {
      const current = serializeMentionEditor(root).mentions
      if (
        JSON.stringify(current) === JSON.stringify(mentions || [])
      ) {
        return
      }
    }
    syncingRef.current = true
    renderMentionContent(root, value || "", mentions || [])
    syncingRef.current = false
  }, [value, mentions])

  const clearMentionSelection = useCallback(() => {
    if (selectedMentionRef.current) {
      selectedMentionRef.current.classList.remove("mention-token--selected")
      selectedMentionRef.current = null
    }
  }, [])

  const handleInput = useCallback(() => {
    emitChange()
    updateMentionQuery()
  }, [emitChange, updateMentionQuery])

  const handleMentionHover = useCallback(
    (e) => {
      const token = e.target.closest?.(".mention-token")
      if (!token || !editorRef.current?.contains(token)) {
        setHoverPreview(null)
        return
      }
      const id = token.dataset.id
      const name = token.dataset.name
      const imageUrl =
        token.dataset.imageUrl
        || getMentionImage?.(id, name)
        || null
      if (!imageUrl) {
        setHoverPreview(null)
        return
      }
      const rect = token.getBoundingClientRect()
      setHoverPreview({
        imageUrl,
        name: name || "",
        left: rect.left + rect.width / 2,
        top: rect.top,
      })
    },
    [getMentionImage]
  )

  const handleMentionLeave = useCallback((e) => {
    const related = e.relatedTarget
    if (related?.closest?.(".mention-hover-preview")) return
    setHoverPreview(null)
  }, [])

  const handleKeyDown = useCallback(
    (e) => {
      const root = editorRef.current
      const isDeleteKey = e.key === "Backspace" || e.key === "Delete"
      if (isDeleteKey && root) {
        const sel = window.getSelection()
        if (!sel?.rangeCount) {
          onKeyDown?.(e)
          return
        }
        const range = sel.getRangeAt(0)
        if (!range.collapsed) {
          clearMentionSelection()
          onKeyDown?.(e)
          return
        }

        let mentionEl = null
        const node = range.startContainer
        if (node.nodeType === Node.ELEMENT_NODE && node.classList?.contains("mention-token")) {
          mentionEl = node
        } else if (node.nodeType === Node.TEXT_NODE && range.startOffset === 0) {
          const prev = node.previousSibling
          if (prev?.classList?.contains("mention-token")) mentionEl = prev
        } else if (node.nodeType === Node.TEXT_NODE && e.key === "Delete") {
          const next = node.nextSibling
          if (next?.classList?.contains("mention-token")) mentionEl = next
        } else if (node.nodeType === Node.TEXT_NODE) {
          const parent = node.parentElement
          if (parent?.classList?.contains("mention-token")) mentionEl = parent
        }

        if (mentionEl) {
          e.preventDefault()
          if (selectedMentionRef.current === mentionEl) {
            mentionEl.remove()
            selectedMentionRef.current = null
            emitChange()
            updateMentionQuery()
          } else {
            clearMentionSelection()
            selectedMentionRef.current = mentionEl
            mentionEl.classList.add("mention-token--selected")
          }
          return
        }
        clearMentionSelection()
      } else {
        clearMentionSelection()
      }
      onKeyDown?.(e)
    },
    [clearMentionSelection, emitChange, updateMentionQuery, onKeyDown]
  )

  const handlePaste = useCallback(
    (e) => {
      e.preventDefault()
      const text = e.clipboardData?.getData("text/plain") || ""
      if (!text) return
      const sel = window.getSelection()
      if (!sel?.rangeCount) return
      sel.deleteFromDocument()
      const range = sel.getRangeAt(0)
      range.collapse(true)
      const node = document.createTextNode(text)
      range.insertNode(node)
      range.setStartAfter(node)
      range.collapse(true)
      sel.removeAllRanges()
      sel.addRange(range)
      emitChange()
      updateMentionQuery()
    },
    [emitChange, updateMentionQuery]
  )

  return (
    <>
      <div
        ref={editorRef}
        className={`mention-editor nodrag nowheel${expanded ? " mention-editor--expanded" : ""}${disabled ? " mention-editor--disabled" : ""}${className ? ` ${className}` : ""}`}
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        data-placeholder={placeholder}
        onInput={handleInput}
        onKeyUp={updateMentionQuery}
        onPointerDown={(e) => {
          clearMentionSelection()
          onPointerDown?.(e)
        }}
        onMouseDown={(e) => {
          clearMentionSelection()
          onMouseDown?.(e)
        }}
        onMouseOver={handleMentionHover}
        onMouseMove={handleMentionHover}
        onMouseLeave={handleMentionLeave}
        onFocus={onFocus}
        onBlur={(e) => {
          setHoverPreview(null)
          onBlur?.(e)
        }}
        onClick={onClick}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
      />
      {hoverPreview &&
        createPortal(
          <div
            className="mention-hover-preview nodrag nopan"
            style={{
              position: "fixed",
              left: hoverPreview.left,
              top: hoverPreview.top - 8,
              transform: "translate(-50%, -100%)",
              zIndex: 13000,
            }}
            onMouseLeave={() => setHoverPreview(null)}
          >
            <img src={ensureMediaUrl(hoverPreview.imageUrl)} alt="" draggable={false} />
            {hoverPreview.name && (
              <span className="mention-hover-preview-label">{hoverPreview.name}</span>
            )}
          </div>,
          document.body
        )}
    </>
  )
})

export default MentionTextarea
