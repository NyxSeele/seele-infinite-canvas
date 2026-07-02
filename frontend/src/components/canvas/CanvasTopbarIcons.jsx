function IconCollabScreen() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <circle cx="4.8" cy="4.2" r="1.8" stroke="currentColor" strokeWidth="1.1" />
      <path
        d="M1.8 12c0-2 1.4-3.2 3-3.2s3 1.2 3 3.2"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
      <circle cx="10.2" cy="4.8" r="1.8" stroke="currentColor" strokeWidth="1.1" />
      <path
        d="M7.2 12c0-2 1.4-3.2 3-3.2s3 1.2 3 3.2"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
    </svg>
  )
}

function IconAgent() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <path
        d="M7.5 2L8.3 6.2L12.5 7L8.3 7.8L7.5 12L6.7 7.8L2.5 7L6.7 6.2L7.5 2Z"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  )
}

function IconShare() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <circle cx="11.2" cy="3.2" r="1.5" stroke="currentColor" strokeWidth="1.1" />
      <circle cx="3.8" cy="7.5" r="1.5" stroke="currentColor" strokeWidth="1.1" />
      <circle cx="11.2" cy="11.8" r="1.5" stroke="currentColor" strokeWidth="1.1" />
      <path d="M5.1 6.7l4.8-2.4M5.1 8.3l4.8 2.4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  )
}

function IconStyleRef() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <rect x="2" y="3.5" width="11" height="8" rx="1.2" stroke="currentColor" strokeWidth="1.1" />
      <path
        d="M2 6.2h11M5.2 9.2h2.4M9 9.2h1.6"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
      <circle cx="4.2" cy="5.1" r="0.7" fill="currentColor" />
    </svg>
  )
}

function IconZoom() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <circle cx="6.5" cy="6.5" r="3.6" stroke="currentColor" strokeWidth="1.1" />
      <path d="M9.2 9.2L12.5 12.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  )
}

function IconCredit() {
  return (
    <span className="canvas-credit-icon" aria-hidden>
      ✦
    </span>
  )
}

function IconEnhance() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <path
        d="M7.5 2.2l.9 2.8 2.8.9-2.8.9-.9 2.8-.9-2.8-2.8-.9 2.8-.9.9-2.8z"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
      <path d="M11.8 2.4v1.6M12.6 3.2h-1.6" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
      <path d="M3 11.2h2.2M4.1 10.1v2.2" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  )
}

export { IconCollabScreen, IconAgent, IconShare, IconStyleRef, IconZoom, IconEnhance, IconCredit }
