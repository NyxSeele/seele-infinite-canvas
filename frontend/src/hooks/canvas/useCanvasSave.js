import { useCallback, useEffect, useRef } from "react"
import api from "../../services/api"
import { loadCanvasProject, loadCanvasShare, saveCanvasProject } from "../../services/canvasApi"
import { useCanvasStore } from "../../stores"
import { getActiveTeamId } from "../../utils/teamContext"
import { hydrateNodeMediaFields, refreshMediaTicket } from "../../utils/mediaTicket"
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
import { readDisplayName } from "../../utils/canvas/commentUserDisplay"

const LAST_MOD_KEY = "canvas-last-modified"

function lastModKey(projectId) {
  return projectId ? `${LAST_MOD_KEY}-${projectId}` : LAST_MOD_KEY
}

function draftKey(projectId) {
  return projectId ? `canvas-local-draft-${projectId}` : "canvas-local-draft"
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
}) {
  const saveTimeoutRef = useRef(null)
  const shareLoadedRef = useRef(false)
  const loadedProjectRef = useRef(null)
  const setSaveStatus = useCanvasStore((s) => s.setSaveStatus)
  const setLastModifiedAt = useCanvasStore((s) => s.setLastModifiedAt)
  const setLastModifiedBy = useCanvasStore((s) => s.setLastModifiedBy)
  const setProjectName = useCanvasStore((s) => s.setProjectName)
  const setProjectVersion = useCanvasStore((s) => s.setProjectVersion)
  const setProjectTeamId = useCanvasStore((s) => s.setProjectTeamId)
  const prevSnapshotRef = useRef(null)

  const buildPersistPayload = useCallback((nodeList, edgeList) => {
    const serializableNodes = nodeList.map((n) => {
      const { onUpdate, onDelete, ...restData } = n.data
      return normalizeTextResponseNode({
        ...n,
        data: sanitizeNodeDataForPersist(restData),
      })
    })
    return { nodes: serializableNodes, edges: edgeList }
  }, [])

  const snapshotKey = useCallback(
    (nodeList, edgeList) => JSON.stringify(buildPersistPayload(nodeList, edgeList)),
    [buildPersistPayload]
  )

  const applyCanvasData = useCallback(
    (canvasData, meta = {}) => {
      const savedNodes = canvasData?.nodes || []
      const savedEdges = canvasData?.edges || []
      const migrated = migrateCanvasBeatCards(savedNodes, savedEdges)
      const nodesToRestore = migrated.nodes
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
        const ts = Date.parse(meta.updated_at)
        if (!Number.isNaN(ts)) {
          writeLastModified(projectId, ts)
          setLastModifiedAt(ts)
        }
      } else {
        setLastModifiedAt(Date.now())
      }
      if (meta.last_modified_by) {
        setLastModifiedBy(meta.last_modified_by)
      }
      prevSnapshotRef.current = snapshotKey(restoredNodes, edgesToRestore)
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
  }, [projectId, shareToken])

  useEffect(() => {
    reloadFromServerRef.current = async () => {
      if (!projectId || shareToken) return null
      try {
        await refreshMediaTicket(api)
      } catch {
        /* ignore */
      }
      const res = await loadCanvasProject(projectId)
      loadedProjectRef.current = projectId
      applyCanvasData(res.canvas_data || { nodes: [], edges: [] }, res)
      onProjectLoaded?.(res)
      setSaveStatus("idle")
      return res
    }

    const loadCanvas = async () => {
      try {
        if (shareToken) {
          if (shareLoadedRef.current) return
          const shared = await loadCanvasShare(shareToken)
          shareLoadedRef.current = true
          applyCanvasData(shared.canvas_data || { nodes: [], edges: [] }, {
            name: shared.project_name,
          })
          onShareLoaded?.(shared.project_name)
          setSaveStatus("idle")
          return
        }

        if (!projectId) return
        if (loadedProjectRef.current === projectId) return

        try {
          await refreshMediaTicket(api)
        } catch {
          /* 未登录时跳过 */
        }

        const res = await loadCanvasProject(projectId)
        loadedProjectRef.current = projectId
        applyCanvasData(res.canvas_data || { nodes: [], edges: [] }, res)
        onProjectLoaded?.(res)
        const stored = readLastModified(projectId)
        const apiTs = res.updated_at ? Date.parse(res.updated_at) : null
        if (apiTs) setLastModifiedAt(apiTs)
        else if (stored) setLastModifiedAt(stored)
        if (res.last_modified_by) setLastModifiedBy(res.last_modified_by)
        setSaveStatus("idle")
      } catch (e) {
        console.log("画布加载失败或为空", e)
        setSaveStatus("error")
      }
    }
    loadCanvas()
  }, [shareToken, projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (readOnly || shareToken || !projectId) return undefined
    if (savePauseRef?.current) return undefined
    clearTimeout(saveTimeoutRef.current)
    saveTimeoutRef.current = setTimeout(async () => {
      if (savePauseRef?.current) return

      const payload = buildPersistPayload(nodes, edges)
      const snapshotStr = JSON.stringify(payload)
      if (snapshotStr === prevSnapshotRef.current) {
        return
      }
      const projectName = useCanvasStore.getState().projectName

      const token = localStorage.getItem("access_token")
      if (!token) {
        try {
          localStorage.setItem(draftKey(projectId), JSON.stringify(payload))
        } catch {
          /* ignore */
        }
        setSaveStatus("idle")
        return
      }

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
        const now = res.updated_at ? Date.parse(res.updated_at) : Date.now()
        writeLastModified(projectId, now)
        setLastModifiedAt(now)
        if (res.last_modified_by) {
          setLastModifiedBy(res.last_modified_by)
        } else {
          setLastModifiedBy(readDisplayName())
        }
        prevSnapshotRef.current = snapshotStr
        window.dispatchEvent(
          new CustomEvent("canvas-project-saved", {
            detail: { projectId, updated_at: res.updated_at || new Date(now).toISOString() },
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
        if (status === 401) {
          try {
            localStorage.setItem(draftKey(projectId), JSON.stringify(payload))
          } catch {
            /* ignore */
          }
          setSaveStatus("idle")
          return
        }
        if (status === 409) {
          const detail = err?.response?.data?.detail
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
      }
    }, 2000)
    return () => clearTimeout(saveTimeoutRef.current)
  }, [
    nodes,
    edges,
    projectId,
    readOnly,
    shareToken,
    setSaveStatus,
    setLastModifiedAt,
    setLastModifiedBy,
    setProjectVersion,
    getSessionId,
    onVersionConflict,
    savePauseRef,
    applyCanvasData,
    buildPersistPayload,
    snapshotKey,
  ])

  return { writeLastModified, setLastModifiedAt, setSaveStatus, reloadFromServer }
}
