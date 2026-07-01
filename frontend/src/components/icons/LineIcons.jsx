/** 全系统统一的线条图标（无填充色块） */

export function LineIcon({ name, size = 18, className = "" }) {
  const props = {
    width: size,
    height: size,
    viewBox: "0 0 18 18",
    fill: "none",
    className,
    "aria-hidden": true,
  }

  switch (name) {
    case "image":
      return (
        <svg {...props}>
          <rect x="2.5" y="3.5" width="13" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
          <circle cx="6.5" cy="7.5" r="1.2" stroke="currentColor" strokeWidth="1.1" />
          <path d="M3.5 13l3.5-3 2.5 2 2-1.5 3 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case "video":
      return (
        <svg {...props}>
          <rect x="2.5" y="4.5" width="13" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M8 7.5l3.5 2L8 11.5V7.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
      )
    case "text":
      return (
        <svg {...props}>
          <path d="M4 5h10M4 9h8M4 13h5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "script":
      return (
        <svg {...props}>
          <rect x="3.5" y="2.5" width="11" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M6 6h6M6 9h6M6 12h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      )
    case "character":
      return (
        <svg {...props}>
          <circle cx="9" cy="6" r="3" stroke="currentColor" strokeWidth="1.3" />
          <path d="M3.5 15.5c0-3 2.5-5 5.5-5s5.5 2 5.5 5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "scene":
      return (
        <svg {...props}>
          <path d="M3 14V6l6-3 6 3v8H3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          <path d="M7 14V9h4v5" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      )
    case "audio":
      return (
        <svg {...props}>
          <path d="M6 8.5v5M6 8.5c0-1.5 1.2-2.5 3-2.5s3 1 3 2.5v5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <path d="M4.5 11.5v1.5a4.5 4.5 0 0 0 9 0v-1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "sparkle":
      return (
        <svg {...props}>
          <path d="M9 2l1.2 4.3L14.5 7.5l-4.3 1.2L9 13l-1.2-4.3L3.5 7.5l4.3-1.2L9 2z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
      )
    case "chain":
      return (
        <svg {...props}>
          <path d="M6.5 9a2.5 2.5 0 0 1 0-5h2a2.5 2.5 0 0 1 2.45 2M11.5 9a2.5 2.5 0 0 1 0 5h-2a2.5 2.5 0 0 1-2.45-2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "upload":
      return (
        <svg {...props}>
          <path d="M9 3v8M6 6l3-3 3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M3.5 14.5h11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "plus":
      return (
        <svg {...props}>
          <path d="M9 3.5v11M4 9h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      )
    case "folder":
      return (
        <svg {...props}>
          <path d="M2.5 6.5V14a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5V7.5a1.5 1.5 0 0 0-1.5-1.5H9L7.5 4.5H4a1.5 1.5 0 0 0-1.5 1.5v.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
      )
    case "style":
      return (
        <svg {...props}>
          <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.3" />
          <path d="M9 5.5v7M5.5 9h7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      )
    case "info":
      return (
        <svg {...props}>
          <circle cx="9" cy="9" r="6.5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M9 8.2V12.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          <circle cx="9" cy="5.8" r="0.7" fill="currentColor" />
        </svg>
      )
    case "user":
      return (
        <svg {...props}>
          <circle cx="9" cy="6.5" r="2.8" stroke="currentColor" strokeWidth="1.3" />
          <path d="M3.5 15c0-3 2.5-4.5 5.5-4.5s5.5 1.5 5.5 4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "settings":
      return (
        <svg {...props}>
          <path
            d="M7.4 2.5h3.2l.4 1.8a4.8 4.8 0 0 1 1.6.9l1.7-.7 2.3 2.3-.7 1.7c.4.5.7 1 .9 1.6l1.8.4v3.2l-1.8.4c-.2.6-.5 1.1-.9 1.6l.7 1.7-2.3 2.3-1.7-.7a4.8 4.8 0 0 1-1.6.9l-.4 1.8H7.4l-.4-1.8a4.8 4.8 0 0 1-1.6-.9l-1.7.7-2.3-2.3.7-1.7a4.8 4.8 0 0 1-.9-1.6l-1.8-.4V7.4l1.8-.4c.2-.6.5-1.1.9-1.6l-.7-1.7 2.3-2.3 1.7.7c.5-.4 1-.7 1.6-.9l.4-1.8z"
            stroke="currentColor"
            strokeWidth="1.05"
            strokeLinejoin="round"
          />
          <circle cx="9" cy="9" r="2.2" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      )
    case "bell":
      return (
        <svg {...props}>
          <path d="M9 2.5a4.5 4.5 0 0 0-4.5 4.5v3.2l-1.2 2.2h11.4l-1.2-2.2V7a4.5 4.5 0 0 0-4.5-4.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          <path d="M7.5 14a1.5 1.5 0 0 0 3 0" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "agent":
      return (
        <svg {...props}>
          <path d="M3.5 5.5V13a1.5 1.5 0 0 0 1.5 1.5H9" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          <path d="M6.5 4.5H11l2 2.5V13a1.5 1.5 0 0 1-1.5 1.5H11" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          <circle cx="12.5" cy="12.5" r="1.2" stroke="currentColor" strokeWidth="1.1" />
          <path d="M12.5 11.3V9.8M11.7 12.5H10.2" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
        </svg>
      )
    case "sprout":
      return (
        <svg {...props}>
          <path d="M9 15.5V8.5M9 8.5C9 5.5 12 3.5 14.5 3.5C14.5 6.5 12.5 8.5 9 8.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M9 8.5C9 5.5 6 3.5 3.5 3.5C3.5 6.5 5.5 8.5 9 8.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case "help":
      return (
        <svg {...props}>
          <circle cx="9" cy="9" r="6.5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M7 7a2 2 0 1 1 3.2 1.6c-.8.6-1.2 1-1.2 2.1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <circle cx="9" cy="13" r="0.8" fill="currentColor" />
        </svg>
      )
    case "logout":
      return (
        <svg {...props}>
          <path d="M7 3.5H4.5a1.5 1.5 0 0 0-1.5 1.5v8a1.5 1.5 0 0 0 1.5 1.5H7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <path d="M11.5 12.5 15 9l-3.5-3.5M15 9H7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case "feedback":
      return (
        <svg {...props}>
          <path d="M3.5 4.5h11v7.5H7.5L4.5 14.5v-2.5H3.5V4.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
      )
    case "doc":
      return (
        <svg {...props}>
          <path d="M5 2.5h5.5L13.5 5.5V15a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          <path d="M10 2.5V6h3.5" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
      )
    case "book":
      return (
        <svg {...props}>
          <path d="M3.5 3.5h4.5v11H4a1 1 0 0 1-1-1V3.5zm7 0H15a1 1 0 0 1 1 1v10h-5.5V3.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
      )
    case "thumb":
      return (
        <svg {...props}>
          <rect x="3.5" y="3.5" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.3" />
        </svg>
      )
    case "undo":
      return (
        <svg {...props}>
          <path d="M5.5 6.5H12a3 3 0 1 1 0 6H10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <path d="M7.5 4.5 5.5 6.5 7.5 8.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case "redo":
      return (
        <svg {...props}>
          <path d="M12.5 6.5H6a3 3 0 1 0 0 6H8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <path d="M10.5 4.5 12.5 6.5 10.5 8.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case "clipboard":
      return (
        <svg {...props}>
          <rect x="5.5" y="4.5" width="8" height="10" rx="1.2" stroke="currentColor" strokeWidth="1.3" />
          <path d="M7 4.5V4a1.5 1.5 0 0 1 1.5-1.5h1A1.5 1.5 0 0 1 11 4v.5" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      )
    case "sun":
      return (
        <svg {...props}>
          <circle cx="9" cy="9" r="3.2" stroke="currentColor" strokeWidth="1.3" />
          <path d="M9 2v1.5M9 14.5V16M2 9h1.5M14.5 9H16M4.1 4.1l1 1M12.9 12.9l1 1M13.9 4.1l-1 1M5.1 12.9l-1 1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      )
    case "moon":
      return (
        <svg {...props}>
          <path
            d="M8.5 2.7a5.3 5.3 0 1 0 0 10.4 4.6 4.6 0 0 1 0-10.4z"
            fill="currentColor"
          />
        </svg>
      )
    case "trash":
      return (
        <svg {...props}>
          <path d="M4 5.5h10M6.5 5.5V4.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1M7 8v4M11 8v4M5.5 5.5l.5 8a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1l.5-8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    default:
      return (
        <svg {...props}>
          <circle cx="9" cy="9" r="6.5" stroke="currentColor" strokeWidth="1.3" />
        </svg>
      )
  }
}

export const NODE_TYPE_ICON = {
  "image-gen": "sparkle",
  "video-gen": "video",
  "text-note": "text",
  "script-table": "script",
  "image-upload": "upload",
}
