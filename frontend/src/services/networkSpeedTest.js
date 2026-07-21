const TEST_SIZE_BYTES = 100 * 1024 * 1024
const PING_COUNT = 10
const MB = 1024 * 1024

const NO_CACHE_HEADERS = {
  "Cache-Control": "no-cache",
}

function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || "").trim().replace(/\/+$/, "")
}

function fetchErrorMessage(err, baseUrl) {
  const raw = err?.message || String(err)
  if (raw === "Failed to fetch" || err?.name === "TypeError") {
    return `请求失败（多为 CORS 跨域）：页面域名与 ${baseUrl} 不同源时，后端 CORS_ORIGINS 必须同时包含两者。也可能是证书/网络中断。`
  }
  return raw
}

async function fetchNoCache(url, options = {}) {
  try {
    return await fetch(url, {
      cache: "no-store",
      headers: NO_CACHE_HEADERS,
      ...options,
      headers: {
        ...NO_CACHE_HEADERS,
        ...(options.headers || {}),
      },
    })
  } catch (err) {
    throw new Error(fetchErrorMessage(err, new URL(url).origin))
  }
}

function cacheBustUrl(url) {
  const sep = url.includes("?") ? "&" : "?"
  return `${url}${sep}_t=${Date.now()}`
}

function percentile95(values) {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const index = Math.ceil(0.95 * (sorted.length - 1))
  return sorted[index]
}

function statsFromSamples(samples) {
  if (!samples.length) {
    return { min: 0, max: 0, avg: 0, p95: 0 }
  }
  const sum = samples.reduce((acc, v) => acc + v, 0)
  return {
    min: Math.min(...samples),
    max: Math.max(...samples),
    avg: sum / samples.length,
    p95: percentile95(samples),
  }
}

function formatBytesShort(bytes) {
  if (!Number.isFinite(bytes)) return "—"
  if (bytes < MB) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / MB).toFixed(1)} MB`
}

function bytesToMbps(bytes, seconds) {
  if (!seconds || seconds <= 0) return 0
  return bytes / MB / seconds
}

function xhrErrorMessage(xhr, baseUrl) {
  if (xhr.status > 0) {
    return `上传测试失败: HTTP ${xhr.status}`
  }
  return `上传请求失败（可能是 Cloudflare Tunnel 100s 超时或网络中断）: ${baseUrl}`
}

function uploadWithProgress(url, blob, onProgress, timeoutMs = 600000) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const start = performance.now()
    let loaded = 0
    let lastProgressAt = start

    const tickTimer = window.setInterval(() => {
      const now = performance.now()
      const elapsedSec = (now - start) / 1000
      const stalledMs = now - lastProgressAt
      const message =
        loaded > 0
          ? `上传中 ${formatBytesShort(loaded)} / ${formatBytesShort(blob.size)}`
          : `上传中，等待数据发送… ${Math.round(elapsedSec)}s`
      onProgress?.({
        loaded,
        total: blob.size,
        percent: blob.size > 0 ? (loaded / blob.size) * 100 : 0,
        speedMbps: bytesToMbps(loaded, elapsedSec),
        elapsedSec,
        stalled: loaded > 0 && stalledMs > 5000,
        message,
      })
    }, 500)

    xhr.open("POST", url)
    xhr.timeout = timeoutMs
    xhr.setRequestHeader("Cache-Control", "no-cache")
    xhr.setRequestHeader("Content-Type", "application/octet-stream")

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      loaded = event.loaded
      lastProgressAt = performance.now()
      const elapsedSec = (performance.now() - start) / 1000
      onProgress?.({
        loaded: event.loaded,
        total: event.total,
        percent: (event.loaded / event.total) * 100,
        speedMbps: bytesToMbps(event.loaded, elapsedSec),
        elapsedSec,
        message: `上传中 ${formatBytesShort(event.loaded)} / ${formatBytesShort(event.total)}`,
      })
    }

    xhr.onload = () => {
      window.clearInterval(tickTimer)
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve({
          body: xhr.responseText,
          totalSec: (performance.now() - start) / 1000,
        })
        return
      }
      reject(new Error(xhrErrorMessage(xhr, new URL(url).origin)))
    }

    xhr.onerror = () => {
      window.clearInterval(tickTimer)
      reject(new Error(xhrErrorMessage(xhr, new URL(url).origin)))
    }

    xhr.ontimeout = () => {
      window.clearInterval(tickTimer)
      reject(new Error(`上传超时（>${Math.round(timeoutMs / 1000)}s），Cloudflare 免费 Tunnel 约 100s 限制，可改用 AutoDL 直连对比上传速度`))
    }

    xhr.send(blob)
  })
}

async function consumeDownloadStream(response, onProgress) {
  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error("响应不支持流式下载")
  }

  let received = 0
  let firstByteMs = null
  const start = performance.now()
  let lastReceived = 0
  let lastTick = start

  const tickTimer = window.setInterval(() => {
    const now = performance.now()
    const elapsedSec = (now - start) / 1000
    const message =
      received >= TEST_SIZE_BYTES
        ? "下载完成，校验中…"
        : received > 0
          ? `下载中 ${formatBytesShort(received)} / ${formatBytesShort(TEST_SIZE_BYTES)}`
          : `下载中，等待首包… ${Math.round(elapsedSec)}s`
    onProgress?.({
      received,
      total: TEST_SIZE_BYTES,
      elapsedSec,
      speedMbps: bytesToMbps(received, elapsedSec),
      message,
      stalled: received > 0 && received === lastReceived && now - lastTick > 5000,
    })
    if (received !== lastReceived) {
      lastReceived = received
      lastTick = now
    }
  }, 500)

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (value?.byteLength) {
        if (firstByteMs == null) {
          firstByteMs = performance.now() - start
        }
        received += value.byteLength
        const elapsedSec = (performance.now() - start) / 1000
        onProgress?.({
          received,
          total: TEST_SIZE_BYTES,
          elapsedSec,
          speedMbps: bytesToMbps(received, elapsedSec),
          message: `下载中 ${formatBytesShort(received)} / ${formatBytesShort(TEST_SIZE_BYTES)}`,
        })
      }
    }
  } finally {
    window.clearInterval(tickTimer)
  }

  const totalSec = (performance.now() - start) / 1000
  return {
    ttfbMs: firstByteMs ?? totalSec * 1000,
    received,
    seconds: totalSec,
    mbps: bytesToMbps(received, totalSec),
  }
}

export async function runPingTest(baseUrl) {
  const base = normalizeBaseUrl(baseUrl)
  if (!base) throw new Error("Base URL 不能为空")

  const samples = []
  for (let i = 0; i < PING_COUNT; i += 1) {
    const url = cacheBustUrl(`${base}/api/health`)
    const start = performance.now()
    const response = await fetchNoCache(url, { method: "GET" })
    if (!response.ok) {
      throw new Error(`Ping 失败: HTTP ${response.status}`)
    }
    await response.text()
    samples.push(performance.now() - start)
  }

  return statsFromSamples(samples)
}

export async function runDownloadTest(baseUrl, onProgress) {
  const base = normalizeBaseUrl(baseUrl)
  if (!base) throw new Error("Base URL 不能为空")

  const url = cacheBustUrl(`${base}/api/network/test-download`)
  const start = performance.now()
  const response = await fetchNoCache(url, { method: "GET" })
  if (!response.ok) {
    throw new Error(`下载测试失败: HTTP ${response.status}`)
  }

  const result = await consumeDownloadStream(response, onProgress)
  return {
    ttfbMs: result.ttfbMs,
    seconds: result.seconds,
    mbps: result.mbps,
    received: result.received,
    totalMs: performance.now() - start,
  }
}

export async function runUploadTest(baseUrl, onProgress) {
  const base = normalizeBaseUrl(baseUrl)
  if (!base) throw new Error("Base URL 不能为空")

  onProgress?.({
    phase: "preparing",
    percent: 0,
    message: "生成 100MB 测试数据…",
  })
  const blob = new Blob([new Uint8Array(TEST_SIZE_BYTES)])

  const url = cacheBustUrl(`${base}/api/network/test-upload`)
  onProgress?.({
    phase: "uploading",
    percent: 0,
    message: "开始上传…",
  })

  const { body, totalSec } = await uploadWithProgress(url, blob, (progress) => {
    onProgress?.({
      phase: "uploading",
      ...progress,
    })
  })

  let payload = {}
  try {
    payload = JSON.parse(body)
  } catch {
    payload = {}
  }
  if (payload?.success !== true) {
    throw new Error("上传测试返回异常")
  }

  onProgress?.({
    phase: "done",
    percent: 100,
    speedMbps: bytesToMbps(TEST_SIZE_BYTES, totalSec),
    elapsedSec: totalSec,
    message: "上传完成",
  })

  return {
    seconds: totalSec,
    mbps: bytesToMbps(TEST_SIZE_BYTES, totalSec),
    totalMs: totalSec * 1000,
  }
}

export async function runFullNetworkTest(baseUrl, onProgress) {
  const emit = (phase, detail = {}) => onProgress?.({ phase, ...detail })

  emit("ping", { message: "Ping 测试中…" })
  const ping = await runPingTest(baseUrl)

  emit("download", { message: "下载测试中…", speedMbps: 0 })
  const download = await runDownloadTest(baseUrl, (progress) => {
    emit("download", {
      message: progress.message || "下载测试中…",
      speedMbps: progress.speedMbps,
      received: progress.received,
      elapsedSec: progress.elapsedSec,
      stalled: progress.stalled,
    })
  })

  emit("upload", { message: "准备上传…", speedMbps: 0 })
  const upload = await runUploadTest(baseUrl, (progress) => {
    emit("upload", {
      phase: progress.phase || "uploading",
      message: progress.message || "上传测试中…",
      speedMbps: progress.speedMbps ?? 0,
      percent: progress.percent ?? 0,
      elapsedSec: progress.elapsedSec ?? 0,
      stalled: progress.stalled,
    })
  })

  return {
    baseUrl: normalizeBaseUrl(baseUrl),
    ping,
    ttfbMs: download.ttfbMs,
    download: {
      seconds: download.seconds,
      mbps: download.mbps,
    },
    upload: {
      seconds: upload.seconds,
      mbps: upload.mbps,
    },
    finishedAt: new Date().toISOString(),
  }
}

export function compareNetworkResults(cloudflare, autodl) {
  const rows = [
    {
      key: "pingAvg",
      label: "Ping Avg",
      cf: cloudflare?.ping?.avg,
      ad: autodl?.ping?.avg,
      unit: "ms",
      lowerIsBetter: true,
    },
    {
      key: "pingP95",
      label: "Ping P95",
      cf: cloudflare?.ping?.p95,
      ad: autodl?.ping?.p95,
      unit: "ms",
      lowerIsBetter: true,
    },
    {
      key: "ttfb",
      label: "TTFB",
      cf: cloudflare?.ttfbMs,
      ad: autodl?.ttfbMs,
      unit: "ms",
      lowerIsBetter: true,
    },
    {
      key: "download",
      label: "Download MB/s",
      cf: cloudflare?.download?.mbps,
      ad: autodl?.download?.mbps,
      unit: "MB/s",
      lowerIsBetter: false,
    },
    {
      key: "upload",
      label: "Upload MB/s",
      cf: cloudflare?.upload?.mbps,
      ad: autodl?.upload?.mbps,
      unit: "MB/s",
      lowerIsBetter: false,
    },
  ]

  return rows.map((row) => {
    const cf = Number(row.cf)
    const ad = Number(row.ad)
    const cfValid = Number.isFinite(cf)
    const adValid = Number.isFinite(ad)

    let winner = null
    let cfNote = ""
    let adNote = ""

    if (cfValid && adValid) {
      if (row.lowerIsBetter) {
        if (cf < ad) {
          winner = "cloudflare"
          adNote = `+${Math.round(ad - cf)}ms`
        } else if (ad < cf) {
          winner = "autodl"
          cfNote = `+${Math.round(cf - ad)}ms`
        }
      } else if (cf > ad) {
        winner = "cloudflare"
        adNote = `+${Math.round(((cf - ad) / ad) * 100)}%`
      } else if (ad > cf) {
        winner = "autodl"
        cfNote = `+${Math.round(((ad - cf) / cf) * 100)}%`
      }
    }

    return {
      ...row,
      cfValid,
      adValid,
      winner,
      cfNote,
      adNote,
    }
  })
}

export const HISTORY_STORAGE_KEY = "velora-network-test-history"
export const HISTORY_MAX = 20

export function loadNetworkTestHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveNetworkTestHistory(entry) {
  const prev = loadNetworkTestHistory()
  const next = [entry, ...prev].slice(0, HISTORY_MAX)
  localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next))
  return next
}

export function formatMs(value) {
  if (!Number.isFinite(value)) return "—"
  return `${Math.round(value)} ms`
}

export function formatMbps(value) {
  if (!Number.isFinite(value)) return "—"
  return `${value.toFixed(2)} MB/s`
}

export function formatSeconds(value) {
  if (!Number.isFinite(value)) return "—"
  return `${value.toFixed(2)} s`
}
