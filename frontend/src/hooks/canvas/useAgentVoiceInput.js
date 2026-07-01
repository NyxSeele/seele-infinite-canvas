import { useCallback, useRef, useState } from "react"

export function useAgentVoiceInput({ onTranscript, lang = "zh-CN" }) {
  const [listening, setListening] = useState(false)
  const [supported, setSupported] = useState(true)
  const recognitionRef = useRef(null)

  const toggleListening = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      setSupported(false)
      return false
    }

    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return true
    }

    const rec = new SR()
    rec.lang = lang
    rec.continuous = false
    rec.interimResults = false
    rec.onresult = (ev) => {
      const text = ev.results[0]?.[0]?.transcript || ""
      if (text) onTranscript?.(text)
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recognitionRef.current = rec
    rec.start()
    setListening(true)
    return true
  }, [lang, listening, onTranscript])

  return { listening, supported, toggleListening }
}
