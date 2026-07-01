import { useEffect, useRef, useState } from "react"
import { IconChevronDown } from "./AgentPanelIcons"

function unescapeStatus(raw) {
  return (raw || "")
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "\t")
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, "\\")
}

function extractStatusPreview(raw) {
  const text = (raw || "").trim()
  if (!text) return ""
  const userMatch = text.match(/"user_status"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)/)
  if (userMatch) return unescapeStatus(userMatch[1])
  const thoughtsMatch = text.match(/"thoughts"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)/)
  if (thoughtsMatch) return unescapeStatus(thoughtsMatch[1])
  if (text.startsWith("{")) return ""
  return text
}

function parseTimelineLines(text) {
  return (text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
}

function timelineItemClass(line) {
  if (/^✓/.test(line) || /^已完成/.test(line)) return "ap-timeline__item--done"
  if (/^→/.test(line) || /^正在/.test(line)) return "ap-timeline__item--active"
  return "ap-timeline__item--pending"
}

export default function AgentThoughtBlock({ text, live = false, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen ?? live)
  const bodyRef = useRef(null)
  const display = live ? extractStatusPreview(text) || text : text
  const lines = parseTimelineLines(display)

  useEffect(() => {
    if (live) setOpen(true)
  }, [live])

  useEffect(() => {
    if (!live) setOpen(defaultOpen ?? false)
  }, [live, defaultOpen])

  useEffect(() => {
    if (!open || !bodyRef.current) return
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [display, open])

  if (!display?.trim() && !live) return null

  const toggleOpen = () => {
    if (!live) setOpen((v) => !v)
  }

  return (
    <div
      className={`ap-thoughts${live ? " ap-thoughts--live" : ""}${
        open ? " ap-thoughts--open" : ""
      }`}
    >
      <button
        type="button"
        className="ap-thoughts__summary"
        onClick={toggleOpen}
        aria-expanded={open}
        disabled={live}
      >
        {!live && (
          <span className="ap-thoughts__arrow" aria-hidden>
            <IconChevronDown />
          </span>
        )}
        <span className="ap-thoughts__label">{live ? "思考中…" : "思考过程"}</span>
        {live ? (
          <span className="ap-thoughts__dots" aria-hidden>
            <span />
            <span />
            <span />
          </span>
        ) : null}
      </button>
      {open && (
        <div ref={bodyRef} className="ap-thoughts__body ap-thoughts__body--timeline">
          {lines.length > 0 ? (
            <ul className="ap-timeline">
              {lines.map((line, i) => (
                <li
                  key={`${i}-${line.slice(0, 24)}`}
                  className={`ap-timeline__item ${timelineItemClass(line)}`}
                >
                  {line}
                </li>
              ))}
            </ul>
          ) : (
            display || (live ? "正在分析…" : "")
          )}
          {live && !lines.length && (
            <span className="ap-thoughts__cursor" aria-hidden>
              |
            </span>
          )}
        </div>
      )}
    </div>
  )
}
