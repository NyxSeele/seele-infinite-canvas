/** Agent 侧栏黑白 SVG 图标（禁止 emoji） */

const ICON = 20

export function IconChat() {
  return (
    <svg width={ICON} height={ICON} viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M3 3.5h10a1 1 0 0 1 1 1v5.5a1 1 0 0 1-1 1H8l-2.5 2v-2H3a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path d="M5.5 6.5h5M5.5 8.5h3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

export function IconMic({ active }) {
  return (
    <svg width={ICON} height={ICON} viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="6" y="2.5" width="4" height="7" rx="2" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="M4 7.5a4 4 0 0 0 8 0M8 11.5v2.5M6 14h4"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      {active && <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1" opacity="0.35" />}
    </svg>
  )
}

export function IconSend({ size = 34.5 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none" aria-hidden className="ap-send-icon">
      <circle cx="18" cy="18" r="18" className="ap-send-icon__bg" />
      <path
        d="M18 25V11M18 11l-5 5M18 11l5 5"
        className="ap-send-icon__arrow"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function IconHistoryEmpty() {
  return (
    <svg width="48" height="48" viewBox="0 0 40 40" fill="none" aria-hidden>
      <circle cx="20" cy="20" r="14" stroke="currentColor" strokeWidth="1.4" opacity="0.45" />
      <path
        d="M20 11v9l5 3"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.45"
      />
    </svg>
  )
}

export function IconAnalyze() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="7" cy="7" r="2" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  )
}

export function IconPipeline() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <rect x="1.5" y="2" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.1" />
      <rect x="8.5" y="2" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.1" />
      <rect x="5" y="8" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.1" />
      <path d="M5.5 4h3M7 6v2" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  )
}

export function IconOrganize() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <rect x="1.5" y="1.5" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.1" />
      <rect x="8" y="1.5" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.1" />
      <rect x="1.5" y="8" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.1" />
      <rect x="8" y="8" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  )
}

/** 手动确认：鼠标放在画布上 */
export function IconManualMode() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <rect x="1" y="1.5" width="12" height="9" rx="1.2" stroke="currentColor" strokeWidth="1.1" />
      <path d="M1 4.5h12" stroke="currentColor" strokeWidth="0.9" opacity="0.45" />
      <path
        d="M7.5 6.2l2.8 2.4-.6.7-1.6-.4-.4 1.6-.7-.6 1.1-3.7Z"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="0.4"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function IconAutoMode() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path
        d="M7 2.5v2M7 9.5v2M2.5 7h2M9.5 7h2"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <path
        d="M4.2 4.2l1.4 1.4M8.4 8.4l1.4 1.4M9.8 4.2 8.4 5.6M5.6 8.4 4.2 9.8"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function IconCanvasAdd() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <rect x="1.5" y="1.5" width="11" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.1" />
      <path d="M4.5 7h5M7 4.5v5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  )
}

export function IconUpload() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M7 9V3M7 3L4.5 5.5M7 3l2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2.5 10.5h9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

export function IconBrainstorm() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M7 1.5v1.2M7 11.3v1.2M1.5 7h1.2M11.3 7h1.2" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
      <circle cx="7" cy="7" r="3.2" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  )
}

export function IconSkills() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M2.5 9.5 6 2.5l1.5 3 3.5 1-3.5 1-1.5 3-1.5-3-3.5-1 3.5-1 1.5-3Z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
    </svg>
  )
}

export function IconThinking() {
  return (
    <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M7 2l1 2.2 2.4.4-1.7 1.7.4 2.4L7 7.5 5.3 9.7l.4-2.4L4 4.6 6.4 4.2 7 2Z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
    </svg>
  )
}

export function IconCheck() {
  return (
    <svg width="14" height="14" viewBox="0 0 12 12" fill="none" aria-hidden>
      <path d="M2.5 6l2.2 2.2 4.8-4.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 10 10" fill="none" aria-hidden>
      <path d="M2 3.5 5 6.5 8 3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconChevronRight() {
  return (
    <svg width="12" height="12" viewBox="0 0 10 10" fill="none" aria-hidden>
      <path d="M3.5 2 6.5 5 3.5 8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconStop() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
      <rect x="5" y="5" width="10" height="10" rx="2" fill="currentColor" />
    </svg>
  )
}

export function IconContinue() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden>
      <path
        d="M2 3.5 6 6.5 2 9.5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M7 3.5l4 3-4 3"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function IconAcceptOnly() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden>
      <path d="M2.5 6.5 5.2 9.2 10.5 3.8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconUndo() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden>
      <path d="M3 4.5H8a3 3 0 1 1 0 6H6.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 2.5 3 4.5l2 2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconArrowUpRight() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden>
      <path d="M3.5 8.5 8.5 3.5M5 3.5h3.5V7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
