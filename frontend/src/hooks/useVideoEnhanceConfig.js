import { useEffect, useState } from "react"
import api from "../services/api"

const FALLBACK = {
  loaded: false,
  available: false,
  availableModelSizes: [],
  defaultModelSize: "7b",
}

let cached = null
let inflight = null

async function loadVideoEnhanceConfig() {
  if (cached?.loaded) return cached
  if (inflight) return inflight
  inflight = api
    .get("/api/tasks/video-enhance/config")
    .then(({ data }) => {
      cached = {
        loaded: true,
        available: !!data?.available,
        availableModelSizes: data?.available_model_sizes || [],
        defaultModelSize: data?.default_model_size || "7b",
      }
      return cached
    })
    .catch(() => {
      cached = { ...FALLBACK, loaded: true }
      return cached
    })
    .finally(() => {
      inflight = null
    })
  return inflight
}

/** 画质增强可用规模（5090 仅 3B 时自动降级） */
export function useVideoEnhanceConfig() {
  const [config, setConfig] = useState(cached || FALLBACK)

  useEffect(() => {
    let cancelled = false
    loadVideoEnhanceConfig().then((next) => {
      if (!cancelled) setConfig(next)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return config
}

export function resetVideoEnhanceConfigCache() {
  cached = null
}
