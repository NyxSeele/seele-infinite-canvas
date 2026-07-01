import { create } from "zustand"
import {
  createUserAsset,
  deleteUserAsset,
  fetchUserAssets,
  updateUserAsset,
  uploadUserAsset,
} from "../services/assetsApi"
import { normalizeUserAsset } from "../utils/canvas/globalAssets"
import { getActiveTeamId } from "../utils/teamContext"

export const useAssetStore = create((set, get) => ({
  assets: [],
  teamAssets: [],
  teamAssetsTeamId: null,
  loading: false,
  teamLoading: false,
  error: null,
  loaded: false,
  teamLoaded: false,

  fetchAssets: async (force = false) => {
    if (get().loading) return
    if (get().loaded && !force) return
    set({ loading: true, error: null })
    try {
      const rows = await fetchUserAssets({ teamId: null })
      const assets = rows.map(normalizeUserAsset).filter(Boolean)
      set({ assets, loading: false, loaded: true })
    } catch (err) {
      set({
        loading: false,
        error: err?.response?.data?.detail || err.message || "加载资产库失败",
      })
    }
  },

  fetchTeamAssets: async (force = false, teamId = null) => {
    const scopedTeamId = teamId || getActiveTeamId()
    if (!scopedTeamId) {
      set({ teamAssets: [], teamLoaded: false, teamAssetsTeamId: null })
      return
    }
    if (get().teamLoading) return
    if (get().teamLoaded && !force && get().teamAssetsTeamId === scopedTeamId) return
    set({ teamLoading: true, error: null })
    try {
      const rows = await fetchUserAssets({ teamId: scopedTeamId })
      const teamAssets = rows.map(normalizeUserAsset).filter(Boolean)
      set({
        teamAssets,
        teamLoading: false,
        teamLoaded: true,
        teamAssetsTeamId: scopedTeamId,
      })
    } catch (err) {
      set({
        teamLoading: false,
        error: err?.response?.data?.detail || err.message || "加载团队资产库失败",
      })
    }
  },

  addAssetFromUpload: async ({
    file,
    name,
    kind,
    note,
    sourceCanvasId,
    sourceCanvasName,
    sourceNodeId,
    teamId = null,
  }) => {
    const scopedTeamId = teamId ?? (getActiveTeamId() || null)
    const row = await uploadUserAsset({
      file,
      name,
      kind,
      note,
      source_canvas_id: sourceCanvasId,
      source_canvas_name: sourceCanvasName,
      source_node_id: sourceNodeId,
      team_id: scopedTeamId,
    })
    const asset = normalizeUserAsset(row)
    if (!asset) return null
    if (asset.teamId) {
      set((s) => ({
        teamAssets: [asset, ...s.teamAssets.filter((a) => a.id !== asset.id)],
        teamLoaded: true,
        teamAssetsTeamId: asset.teamId,
      }))
    } else {
      set((s) => ({ assets: [asset, ...s.assets.filter((a) => a.id !== asset.id)] }))
    }
    return asset
  },

  addAssetFromUrl: async ({
    name,
    kind,
    imageUrl,
    note,
    sourceCanvasId,
    sourceCanvasName,
    sourceNodeId,
    teamId = null,
  }) => {
    const scopedTeamId = teamId ?? (getActiveTeamId() || null)
    const row = await createUserAsset({
      name,
      kind: kind || "image",
      image_url: imageUrl,
      note,
      source_canvas_id: sourceCanvasId,
      source_canvas_name: sourceCanvasName,
      source_node_id: sourceNodeId,
      team_id: scopedTeamId,
    })
    const asset = normalizeUserAsset(row)
    if (!asset) return null
    if (asset.teamId) {
      set((s) => ({ teamAssets: [asset, ...s.teamAssets] }))
    } else {
      set((s) => ({ assets: [asset, ...s.assets] }))
    }
    return asset
  },

  publishToTeam: async (id, teamId = null) => {
    const scopedTeamId = teamId || getActiveTeamId()
    if (!scopedTeamId) throw new Error("请先选择团队")
    const row = await updateUserAsset(id, { team_id: scopedTeamId })
    const asset = normalizeUserAsset(row)
    if (!asset) return null
    set((s) => ({
      assets: s.assets.filter((a) => a.id !== id),
      teamAssets: [asset, ...s.teamAssets.filter((a) => a.id !== id)],
      teamLoaded: true,
      teamAssetsTeamId: scopedTeamId,
    }))
    return asset
  },

  unpublishFromTeam: async (id) => {
    const row = await updateUserAsset(id, { team_id: null })
    const asset = normalizeUserAsset(row)
    if (!asset) return null
    set((s) => ({
      assets: [asset, ...s.assets.filter((a) => a.id !== id)],
      teamAssets: s.teamAssets.filter((a) => a.id !== id),
    }))
    return asset
  },

  updateAssetLocal: async (id, patch) => {
    const row = await updateUserAsset(id, {
      name: patch.name,
      kind: patch.kind,
      image_url: patch.imageUrl,
      note: patch.note,
      team_id: patch.teamId !== undefined ? patch.teamId : undefined,
    })
    const asset = normalizeUserAsset(row)
    if (!asset) return null
    set((s) => ({
      assets: asset.teamId
        ? s.assets.filter((a) => a.id !== id)
        : s.assets.map((a) => (a.id === id ? asset : a)),
      teamAssets: asset.teamId
        ? [asset, ...s.teamAssets.filter((a) => a.id !== id)]
        : s.teamAssets.filter((a) => a.id !== id),
    }))
    return asset
  },

  removeAsset: async (id) => {
    await deleteUserAsset(id)
    set((s) => ({
      assets: s.assets.filter((a) => a.id !== id),
      teamAssets: s.teamAssets.filter((a) => a.id !== id),
    }))
  },

  getAsset: (id) =>
    get().assets.find((a) => a.id === id)
    ?? get().teamAssets.find((a) => a.id === id)
    ?? null,
}))
