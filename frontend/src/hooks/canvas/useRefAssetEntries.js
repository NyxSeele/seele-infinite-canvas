import { useCallback, useMemo } from "react"
import { useAssetStore, useCanvasStore } from "../../stores"
import { getActiveTeamId } from "../../utils/teamContext"

/**
 * 参考图浮层用资产列表（对齐分镜表 ScriptCastLibrary 的 assetPool 模式）
 */
export default function useRefAssetEntries() {
  const assets = useAssetStore((s) => s.assets)
  const teamAssets = useAssetStore((s) => s.teamAssets)
  const fetchAssets = useAssetStore((s) => s.fetchAssets)
  const fetchTeamAssets = useAssetStore((s) => s.fetchTeamAssets)
  const projectTeamId = useCanvasStore((s) => s.projectTeamId)
  const teamId = projectTeamId ?? getActiveTeamId()

  const ensureLoaded = useCallback(() => {
    fetchAssets()
    if (teamId) fetchTeamAssets(false, teamId)
  }, [fetchAssets, fetchTeamAssets, teamId])

  const assetEntries = useMemo(() => {
    const pool = teamId ? (teamAssets || []) : (assets || [])
    return (pool || []).filter((a) => a?.imageUrl && a?.name)
  }, [teamId, teamAssets, assets])

  return { assetEntries, ensureLoaded, teamId }
}
