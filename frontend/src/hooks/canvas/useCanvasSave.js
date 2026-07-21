import { useCallback, useEffect, useRef } from "react"
import api from "../../services/api"
import { loadCanvasProject, loadCanvasShare, saveCanvasProject } from "../../services/canvasApi"
import { useCanvasStore } from "../../stores"
import { getActiveTeamId } from "../../utils/teamContext"
import { hydrateNodeMediaFields, refreshMediaTicket, getMediaTicket } from "../../utils/mediaTicket"
import { fetchR2PublicBase } from "../../utils/r2MediaUrl"
import {
  sanitizeNodeDataForPersist,
  resetStaleGenerationState,
  isBlobUrl,
} from "../../components/canvas/videoReferenceHelpers"
import { pickOutlineNodeFields } from "../../utils/canvas/nodeCompose"
import {
  normalizeCanvasNode,
  normalizeOutlineNode,
  normalizeTextResponseNode,
} from "../../utils/canvas/nodeNormalize"
import { migrateCanvasBeatCards } from "../../utils/canvas/scriptBeatCard"
import { migrateGenNodePositions } from "../../utils/canvas/migrateGenNodePositions"
import { syncNodeIdSeq } from "../../utils/canvas/nodeHelpers"
import { readDisplayName } from "../../utils/canvas/commentUserDisplay"
import { parseServerTimestamp } from "../../utils/datetime"

const LAST_MOD_KEY = "canvas-last-modified"

const VOLATILE_SNAPSHOT_DATA_KEYS = new Set([
  "progress",
  "enhanceStatus",
  "lutStatus",
])

function stripVolatileNodeData(data) {
  if (!data || typeof data !== "object") return data
  const next = { ...data }
  for (const key of VOLATILE_SNAPSHOT_DATA_KEYS) {
    delete next[key]
  }
  return next
}

function lastModKey(projectId) {
  return projectId ? `${LAST_MOD_KEY}-${projectId}` : LAST_MOD_KEY
}

function draftKey(projectId) {
  return projectId ? `canvas-local-draft-${projectId}` : "canvas-local-draft"
}

function readDraft(projectId) {
  try {
    const raw = localStorage.getItem(draftKey(projectId))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed?.nodes && Array.isArray(parsed.nodes)) {
      return { savedAt: 0, payload: parsed }
    }
    if (parsed?.payload?.nodes) {
      return {
        savedAt: Number(parsed.savedAt) || 0,
        payload: parsed.payload,
      }
    }
    return null
  } catch {
    return null
  }
}

function writeDraft(projectId, payload) {
  try {
    const incomingNodes = payload?.nodes
    // 禁止用空草稿覆盖已有非空草稿（加载失败/误清空时保住最后一份）
    if (Array.isArray(incomingNodes) && incomingNodes.length === 0) {
      const existing = readDraft(projectId)
      if ((existing?.payload?.nodes?.length || 0) > 0) {
        return
      }
    }
    localStorage.setItem(
      draftKey(projectId),
      JSON.stringify({ savedAt: Date.now(), payload })
    )
  } catch {
    /* ignore */
  }
}

function clearDraft(projectId) {
  try {
    localStorage.removeItem(draftKey(projectId))
  } catch {
    /* ignore */
  }
}

function shouldApplyDraft(projectId, draft, serverUpdatedAt) {
  const apiTs = parseServerTimestamp(serverUpdatedAt)
  const draftTs = draft.savedAt || 0
  if (draftTs <= 0) return false
  if (apiTs != null && draftTs <= apiTs) {
    clearDraft(projectId)
    return false
  }
  return true
}

function readLastModified(projectId) {
  try {
    const v = localStorage.getItem(lastModKey(projectId))
    return v ? Number(v) : null
  } catch {
    return null
  }
}

function writeLastModified(projectId, ts) {
  try {
    localStorage.setItem(lastModKey(projectId), String(ts))
  } catch {
    /* ignore */
  }
}

function normalizeViewport(vp) {
  if (!vp || typeof vp !== "object") return null
  const x = Number(vp.x)
  const y = Number(vp.y)
  const zoom = Number(vp.zoom)
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(zoom) || zoom <= 0) {
    return null
  }
  return { x, y, zoom }
}

function localViewportKey(projectId) {
  return projectId ? `canvas-viewport-${projectId}` : null
}

function readLocalViewport(projectId) {
  const key = localViewportKey(projectId)
  if (!key) return null
  try {
    return normalizeViewport(JSON.parse(localStorage.getItem(key) || "null"))
  } catch {
    return null
  }
}

function writeLocalViewport(projectId, vp) {
  const key = localViewportKey(projectId)
  const normalized = normalizeViewport(vp)
  if (!key || !normalized) return
  try {
    localStorage.setItem(key, JSON.stringify(normalized))
  } catch {
    /* ignore */
  }
}

export { normalizeViewport, readLocalViewport, writeLocalViewport }

export function useCanvasSave({
  projectId = null,
  nodes,
  edges,
  setNodes,
  setEdges,
  buildData,
  buildOutlineData,
  zIndexCounterRef,
  textRetryRef,
  shareToken = null,
  readOnly = false,
  getSessionId = null,
  onShareLoaded,
  onProjectLoaded,
  onVersionConflict,
  savePauseRef = null,
  viewportSnapshot = null,
  onViewportRestore = null,
}) {
  const saveTimeoutRef = useRef(null)
  const draftTimeoutRef = useRef(null)
  const shareLoadedRef = useRef(false)
  const loadedProjectRef = useRef(null)
  const setSaveStatus = useCanvasStore((s) => s.setSaveStatus)
  const setLastModifiedAt = useCanvasStore((s) => s.setLastModifiedAt)
  const setLastModifiedBy = useCanvasStore((s) => s.setLastModifiedBy)
  const setProjectName = useCanvasStore((s) => s.setProjectName)
  const setProjectVersion = useCanvasStore((s) => s.setProjectVersion)
  const setProjectTeamId = useCanvasStore((s) => s.setProjectTeamId)
  const prevSnapshotRef = useRef(null)
  const prevDraftSnapshotRef = useRef(null)
  const viewportRef = useRef(null)
  const saveInFlightRef = useRef(false)
  const saveQueuedRef = useRef(false)
  const canvasLoadedRef = useRef(false)
  /** 最近一次成功加载时服务端节点数；>0 时禁止自动保存空画布 */
  const serverNodeCountRef = useRef(0)
  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)

  useEffect(() => {
    nodesRef.current = nodes
  }, [nodes])

  useEffect(() => {
    edgesRef.current = edges
  }, [edges])

  useEffect(() => {
    const vp = normalizeViewport(viewportSnapshot)
    if (vp) viewportRef.current = vp
  }, [viewportSnapshot])

  useEffect(() => {
    viewportRef.current = null
  }, [projectId, shareToken])

  const buildPersistPayload = useCallback((nodeList, edgeList) => {
    const serializableNodes = nodeList.map((n) => {
      const { onUpdate, onDelete, ...restData } = n.data
      return normalizeTextResponseNode({
        ...n,
        // draft/save 均去掉 progress 等瞬时字段，避免生成中每 2s 全量写 localStorage
        data: sanitizeNodeDataForPersist(stripVolatileNodeData(restData)),
      })
    })
    const payload = { nodes: serializableNodes, edges: edgeList }
    const vp = normalizeViewport(viewportRef.current) || normalizeViewport(viewportSnapshot)
    if (vp) payload.viewport = vp
    return payload
  }, [viewportSnapshot])

  const buildSnapshotComparePayload = useCallback((nodeList, edgeList) => {
    const serializableNodes = nodeList.map((n) => {
      const { onUpdate, onDelete, ...restData } = n.data
      return normalizeTextResponseNode({
        ...n,
        data: sanitizeNodeDataForPersist(stripVolatileNodeData(restData)),
      })
    })
    const payload = { nodes: serializableNodes, edges: edgeList }
    const vp = normalizeViewport(viewportRef.current) || normalizeViewport(viewportSnapshot)
    if (vp) payload.viewport = vp
    return payload
  }, [viewportSnapshot])

  const snapshotKey = useCallback(
    (nodeList, edgeList) => JSON.stringify(buildSnapshotComparePayload(nodeList, edgeList)),
    [buildSnapshotComparePayload]
  )

  const applyCanvasData = useCallback(
    (canvasData, meta = {}) => {
      const savedNodes = canvasData?.nodes || []
      const savedEdges = canvasData?.edges || []
      const migrated = migrateCanvasBeatCards(savedNodes, savedEdges)
      const { nodes: positionMigrated, migratedCount } = migrateGenNodePositions(migrated.nodes)
      if (migratedCount > 0) {
        console.info(`[canvas] migrated ${migratedCount} gen node X position(s) to new script-table layout`)
      }
      const nodesToRestore = positionMigrated
      const edgesToRestore = migrated.edges
      const restoredNodes = nodesToRestore.map((n) => {
        const base = normalizeCanvasNode(n)
        const cleanData = hydrateNodeMediaFields(
          resetStaleGenerationState(
            sanitizeNodeDataForPersist(base.data),
            base.type
          )
        )
        if (base.type === "outline") {
          const outlineFields = pickOutlineNodeFields(cleanData)
          return {
            ...normalizeOutlineNode(base),
            data: {
              ...outlineFields,
              ...buildOutlineData(outlineFields),
            },
          }
        }
        if (base.type === "image-gen") {
          const urls = [
            cleanData?.uploadedImage,
            cleanData?.imageUrl,
            ...(Array.isArray(cleanData?.results) ? cleanData.results : []),
          ].filter(Boolean)
          if (urls.some(isBlobUrl)) {
            console.warn("[canvas] 仍含 blob URL，已尝试清除:", base.id)
          }
        }
        return {
          ...base,
          data: {
            ...cleanData,
            ...buildData(cleanData),
            ...(base.type === "text-response"
              ? { onRetry: (id) => textRetryRef.current(id) }
              : {}),
          },
        }
      })
      const maxZ = restoredNodes.reduce(
        (max, n) => Math.max(max, n.zIndex ?? n.data?.zIndex ?? n.style?.zIndex ?? 0),
        0
      )
      zIndexCounterRef.current = maxZ
      syncNodeIdSeq(restoredNodes)
      setNodes(restoredNodes)
      setEdges(edgesToRestore)
      if (meta.name) setProjectName(meta.name)
      if (meta.version != null) setProjectVersion(meta.version)
      if (meta.team_id) {
        setProjectTeamId(meta.team_id)
      } else if (!getActiveTeamId()) {
        setProjectTeamId(null)
      }
      if (meta.updated_at) {
        const ts = parseServerTimestamp(meta.updated_at)
        if (ts != null) {
          writeLastModified(projectId, ts)
          setLastModifiedAt(ts)
        }
      } else {
        setLastModifiedAt(Date.now())
      }
      if (meta.last_modified_by) {
        setLastModifiedBy(meta.last_modified_by)
      }
      // Resolve viewport before snapshot so subsequent saves never omit a known viewport
      const restoredViewport =
        normalizeViewport(canvasData?.viewport)
        || readLocalViewport(projectId)
      if (restoredViewport) {
        viewportRef.current = restoredViewport
        writeLocalViewport(projectId, restoredViewport)
      }
      prevSnapshotRef.current = snapshotKey(restoredNodes, edgesToRestore)
      onViewportRestore?.(restoredViewport)
    },
    [
      buildData,
      buildOutlineData,
      projectId,
      setEdges,
      setLastModifiedAt,
      setLastModifiedBy,
      setNodes,
      setProjectName,
      setProjectTeamId,
      setProjectVersion,
      snapshotKey,
      textRetryRef,
      zIndexCounterRef,
      onViewportRestore,
    ]
  )

  const reloadFromServerRef = useRef(async () => {})

  const reloadFromServer = useCallback(async () => {
    await reloadFromServerRef.current()
  }, [])

  useEffect(() => {
    shareLoadedRef.current = false
    loadedProjectRef.current = null
    prevSnapshotRef.current = null
    prevDraftSnapshotRef.current = null
    canvasLoadedRef.current = false
    serverNodeCountRef.current = 0
  }, [projectId, shareToken])

  const markLoaded = useCallback((res, appliedPayload) => {
    const fromServer = Array.isArray(res?.canvas_data?.nodes)
      ? res.canvas_data.nodes.length
      : Number(res?.node_count) || 0
    const fromApplied = Array.isArray(appliedPayload?.nodes)
      ? appliedPayload.nodes.length
      : fromServer
    serverNodeCountRef.current = Math.max(fromServer, fromApplied)
    canvasLoadedRef.current = true
  }, [])

  useEffect(() => {
    reloadFromServerRef.current = async () => {
      if (!projectId || shareToken) return null
      try {
        await refreshMediaTicket(api)
        await fetchR2PublicBase(api)
      } catch {
        /* ignore */
      }
      const res = await loadCanvasProject(projectId)
      loadedProjectRef.current = projectId
      const draft = readDraft(projectId)
      if (draft && shouldApplyDraft(projectId, draft, res.updated_at)) {
        applyCanvasData(draft.payload, res)
        onProjectLoaded?.(res)
        markLoaded(res, draft.payload)
        setSaveStatus("idle")
        return res
      }
      const payload = res.canvas_data || { nodes: [], edges: [] }
      applyCanvasData(payload, res)
      onProjectLoaded?.(res)
      markLoaded(res, payload)
      setSaveStatus("idle")
      return res
    }

    const loadCanvas = async () => {
      try {
        if (shareToken) {
          if (shareLoadedRef.current) return
          const shared = await loadCanvasShare(shareToken)
          shareLoadedRef.current = true
          const payload = shared.canvas_data || { nodes: [], edges: [] }
          applyCanvasData(payload, {
            name: shared.project_name,
          })
          onShareLoaded?.(shared.project_name)
          markLoaded({ canvas_data: payload }, payload)
          setSaveStatus("idle")
          return
        }

        if (!projectId) return
        if (loadedProjectRef.current === projectId) return

        // ticket/R2 与项目加载并行；已有有效 ticket 则跳过刷新
        const prep = []
        if (!getMediaTicket()) {
          prep.push(refreshMediaTicket(api).catch(() => {}))
        }
        prep.push(fetchR2PublicBase(api).catch(() => {}))
        const projectPromise = loadCanvasProject(projectId)
        await Promise.all(prep)
        const res = await projectPromise
        loadedProjectRef.current = projectId
        const draft = readDraft(projectId)
        if (draft && shouldApplyDraft(projectId, draft, res.updated_at)) {
          applyCanvasData(draft.payload, res)
          onProjectLoaded?.(res)
          markLoaded(res, draft.payload)
          setSaveStatus("idle")
          return
        }
        const payload = res.canvas_data || { nodes: [], edges: [] }
        applyCanvasData(payload, res)
        onProjectLoaded?.(res)
        markLoaded(res, payload)
        const stored = readLastModified(projectId)
        const apiTs = parseServerTimestamp(res.updated_at)
        if (apiTs != null) {
          writeLastModified(projectId, apiTs)
          setLastModifiedAt(apiTs)
        } else if (stored) setLastModifiedAt(stored)
        if (res.last_modified_by) setLastModifiedBy(res.last_modified_by)
        setSaveStatus("idle")
      } catch (e) {
        console.error("画布加载失败，已禁止自动保存以免写空", e)
        canvasLoadedRef.current = false
        setSaveStatus("error")
      }
    }
    loadCanvas()
  }, [shareToken, projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const runSave = useCallback(async () => {
    if (savePauseRef?.current) return
    if (!canvasLoadedRef.current) return
    if (saveInFlightRef.current) {
      saveQueuedRef.current = true
      return
    }

    const payload = buildPersistPayload(nodesRef.current, edgesRef.current)
    const incomingCount = Array.isArray(payload.nodes) ? payload.nodes.length : 0
    // 硬闸：服务端曾有内容时，禁止把空 nodes 自动写回（上次事故根因）
    if (incomingCount === 0 && serverNodeCountRef.current > 0) {
      console.warn(
        "[canvas] skip empty overwrite save; serverNodeCount=",
        serverNodeCountRef.current
      )
      setSaveStatus("idle")
      return
    }

    const compareKey = JSON.stringify(
      buildSnapshotComparePayload(nodesRef.current, edgesRef.current)
    )
    if (compareKey === prevSnapshotRef.current) {
      return
    }
    const projectName = useCanvasStore.getState().projectName

    const token = localStorage.getItem("access_token")
    if (!token) {
      writeDraft(projectId, payload)
      const draftVp = normalizeViewport(payload.viewport)
      if (draftVp) writeLocalViewport(projectId, draftVp)
      setSaveStatus("idle")
      return
    }

    saveInFlightRef.current = true
    setSaveStatus("saving")
    const version = useCanvasStore.getState().projectVersion
    const sessionId = typeof getSessionId === "function" ? getSessionId() : null
    try {
      const res = await saveCanvasProject(projectId, {
        canvas_data: payload,
        name: projectName,
        version,
        session_id: sessionId,
        display_name: readDisplayName(),
      })
      if (res.version != null) setProjectVersion(res.version)
      const now = parseServerTimestamp(res.updated_at) ?? Date.now()
      writeLastModified(projectId, now)
      setLastModifiedAt(now)
      if (res.last_modified_by) {
        setLastModifiedBy(res.last_modified_by)
      } else {
        setLastModifiedBy(readDisplayName())
      }
      prevSnapshotRef.current = compareKey
      if (incomingCount > 0) {
        serverNodeCountRef.current = incomingCount
        clearDraft(projectId)
      }
      const savedVp = normalizeViewport(payload.viewport)
      if (savedVp) writeLocalViewport(projectId, savedVp)
      window.dispatchEvent(
        new CustomEvent("canvas-project-saved", {
          detail: {
            projectId,
            updated_at: res.updated_at ?? null,
            preview_url: res.preview_url ?? null,
            cover_media_type: res.cover_media_type ?? null,
            recent_collaborators: res.recent_collaborators ?? [],
            collaborator_extra_count: res.collaborator_extra_count ?? 0,
          },
        })
      )
      setSaveStatus("saved")
      setTimeout(() => {
        if (useCanvasStore.getState().saveStatus === "saved") {
          useCanvasStore.getState().setSaveStatus("idle")
        }
      }, 2500)
    } catch (err) {
      const status = err?.response?.status
      const detail = err?.response?.data?.detail
      if (status === 401) {
        writeDraft(projectId, payload)
        setSaveStatus("idle")
        return
      }
      if (status === 409) {
        // 空覆盖被拒：用服务端数据恢复，勿清草稿
        if (detail?.code === "empty_overwrite_blocked" && detail?.canvas_data) {
          applyCanvasData(detail.canvas_data, {
            version: detail.version,
            name: detail.name,
          })
          serverNodeCountRef.current =
            Array.isArray(detail.canvas_data?.nodes)
              ? detail.canvas_data.nodes.length
              : Number(detail.node_count) || serverNodeCountRef.current
          setSaveStatus("idle")
          onVersionConflict?.({ ...detail, merged: true })
          return
        }
        if (detail?.canvas_data) {
          applyCanvasData(detail.canvas_data, {
            version: detail.version,
            name: detail.name,
          })
          setSaveStatus("idle")
          onVersionConflict?.({ ...detail, merged: true })
          return
        }
        if (detail?.version != null) setProjectVersion(detail.version)
        onVersionConflict?.(detail)
        setSaveStatus("error")
        return
      }
      if (status === 423) {
        setSaveStatus("error")
        return
      }
      setSaveStatus("error")
    } finally {
      saveInFlightRef.current = false
      if (saveQueuedRef.current) {
        saveQueuedRef.current = false
        void runSave()
      }
    }
  }, [
    projectId,
    buildPersistPayload,
    buildSnapshotComparePayload,
    setSaveStatus,
    setLastModifiedAt,
    setLastModifiedBy,
    setProjectVersion,
    getSessionId,
    onVersionConflict,
    savePauseRef,
    applyCanvasData,
  ])

  useEffect(() => {
    if (readOnly || shareToken || !projectId) return undefined
    clearTimeout(saveTimeoutRef.current)
    saveTimeoutRef.current = setTimeout(() => {
      void runSave()
    }, 2000)
    return () => clearTimeout(saveTimeoutRef.current)
  }, [
    nodes,
    edges,
    projectId,
    readOnly,
    shareToken,
    runSave,
  ])

  useEffect(() => {
    if (readOnly || shareToken || !projectId) return undefined
    clearTimeout(draftTimeoutRef.current)
    draftTimeoutRef.current = setTimeout(() => {
      if (!canvasLoadedRef.current) return
      const compareKey = snapshotKey(nodesRef.current, edgesRef.current)
      if (compareKey === prevDraftSnapshotRef.current) return
      prevDraftSnapshotRef.current = compareKey
      const payload = buildPersistPayload(nodesRef.current, edgesRef.current)
      writeDraft(projectId, payload)
    }, 800)
    return () => clearTimeout(draftTimeoutRef.current)
  }, [
    nodes,
    edges,
    projectId,
    readOnly,
    shareToken,
    buildPersistPayload,
    snapshotKey,
  ])

  useEffect(() => {
    if (readOnly || shareToken || !projectId) return undefined
    const flushDraft = () => {
      if (!canvasLoadedRef.current) return
      const payload = buildPersistPayload(nodesRef.current, edgesRef.current)
      writeDraft(projectId, payload)
      const draftVp = normalizeViewport(payload.viewport)
      if (draftVp) writeLocalViewport(projectId, draftVp)
    }
    const onPageHide = () => {
      flushDraft()
      clearTimeout(saveTimeoutRef.current)
      clearTimeout(draftTimeoutRef.current)
      void runSave()
    }
    window.addEventListener("pagehide", onPageHide)
    window.addEventListener("beforeunload", flushDraft)
    return () => {
      window.removeEventListener("pagehide", onPageHide)
      window.removeEventListener("beforeunload", flushDraft)
    }
  }, [projectId, readOnly, shareToken, buildPersistPayload, runSave])

  return { writeLastModified, setLastModifiedAt, setSaveStatus, reloadFromServer }
}
