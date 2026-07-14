import { useEffect, useState } from "react"
import api from "../services/api"

/**
 * 拉取模型 capabilities（GET /api/models/:id/capabilities）
 * @param {string|null|undefined} modelId
 * @returns {{ capabilities: object|null, loading: boolean, error: Error|null }}
 */
export default function useModelCapabilities(modelId) {
  const [capabilities, setCapabilities] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!modelId) {
      setCapabilities(null)
      setLoading(false)
      setError(null)
      return undefined
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setCapabilities(null)

    api
      .get(`/api/models/${encodeURIComponent(modelId)}/capabilities`)
      .then((res) => {
        if (cancelled) return
        setCapabilities(res.data && typeof res.data === "object" ? res.data : {})
      })
      .catch((err) => {
        if (cancelled) return
        setError(err)
        setCapabilities({})
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [modelId])

  return { capabilities, loading, error }
}
