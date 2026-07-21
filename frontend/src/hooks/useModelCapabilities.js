import { useEffect, useState } from "react"
import api from "../services/api"

/** 跨组件共享：同 modelId 只打一次 capabilities */
const capsCache = new Map()
const capsInflight = new Map()

function fetchCapabilities(modelId) {
  if (capsCache.has(modelId)) {
    return Promise.resolve(capsCache.get(modelId))
  }
  if (capsInflight.has(modelId)) {
    return capsInflight.get(modelId)
  }
  const pending = api
    .get(`/api/models/${encodeURIComponent(modelId)}/capabilities`)
    .then((res) => {
      const data = res.data && typeof res.data === "object" ? res.data : {}
      capsCache.set(modelId, data)
      return data
    })
    .finally(() => {
      capsInflight.delete(modelId)
    })
  capsInflight.set(modelId, pending)
  return pending
}

/**
 * 拉取模型 capabilities（GET /api/models/:id/capabilities）
 * @param {string|null|undefined} modelId
 * @returns {{ capabilities: object|null, loading: boolean, error: Error|null }}
 */
export default function useModelCapabilities(modelId) {
  const [capabilities, setCapabilities] = useState(() =>
    modelId && capsCache.has(modelId) ? capsCache.get(modelId) : null
  )
  const [loading, setLoading] = useState(() => Boolean(modelId) && !capsCache.has(modelId))
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!modelId) {
      setCapabilities(null)
      setLoading(false)
      setError(null)
      return undefined
    }

    if (capsCache.has(modelId)) {
      setCapabilities(capsCache.get(modelId))
      setLoading(false)
      setError(null)
      return undefined
    }

    let cancelled = false
    setLoading(true)
    setError(null)

    fetchCapabilities(modelId)
      .then((data) => {
        if (cancelled) return
        setCapabilities(data)
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
