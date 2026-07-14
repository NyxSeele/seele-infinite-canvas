import { useCallback, useEffect, useState } from "react"

export const REVIEWER_NAME_KEY = "aistudio_review_reviewer_name"

export function useReviewerName() {
  const [name, setNameState] = useState(() => {
    try {
      return localStorage.getItem(REVIEWER_NAME_KEY) || ""
    } catch {
      return ""
    }
  })
  const [forceAsk, setForceAsk] = useState(false)
  const ready = Boolean(name.trim()) && !forceAsk

  const setName = useCallback((n, reopen = false) => {
    if (reopen) {
      setForceAsk(true)
      return
    }
    const trimmed = (n || "").trim()
    setNameState(trimmed)
    setForceAsk(false)
  }, [])

  return { name, setName, ready, askName: forceAsk }
}

export function ReviewerNameGate({ open, initialName, onConfirm }) {
  const [value, setValue] = useState(initialName || "")

  useEffect(() => {
    if (open) setValue(initialName || "")
  }, [open, initialName])

  if (!open) return null

  return (
    <div className="rs-gate-overlay">
      <div className="rs-gate-modal">
        <h2>输入用户名</h2>
        <p>审阅页无需登录，但提交评价前需要一个显示名。</p>
        <input
          className="rs-gate-input"
          value={value}
          maxLength={64}
          placeholder="你的名字"
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && value.trim()) onConfirm(value.trim())
          }}
        />
        <button
          type="button"
          className="rs-submit"
          disabled={!value.trim()}
          onClick={() => onConfirm(value.trim())}
        >
          进入
        </button>
      </div>
    </div>
  )
}
