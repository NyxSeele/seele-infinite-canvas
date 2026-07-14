import { create } from "zustand"
import {
  CANVAS_NAV_MODE_STORAGE_KEY,
  CANVAS_NAV_MODES,
  getInitialCanvasNavMode,
} from "../utils/canvas/canvasNavMode"

const SNAP_KEY = "canvas-snap-to-grid"
const MINIMAP_KEY = "canvas-minimap-open"
const COMMENT_MODE_KEY = "canvas-comment-mode"

const getInitialTheme = () => {
  const stored = localStorage.getItem("canvas-theme")
  if (stored === "dark" || stored === "light") return stored
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

const getInitialBool = (key, fallback = false) => {
  try {
    const v = localStorage.getItem(key)
    if (v === "1") return true
    if (v === "0") return false
  } catch {
    /* ignore */
  }
  return fallback
}

export const useCanvasStore = create((set, get) => ({
  // ── Theme ────────────────────────────────────────────────
  theme: getInitialTheme(),
  toggleTheme: () => {
    const next = get().theme === "dark" ? "light" : "dark"
    localStorage.setItem("canvas-theme", next)
    set({ theme: next })
  },

  // ── Project meta ─────────────────────────────────────────
  projectName: "未命名画布",
  setProjectName: (name) => set({ projectName: name }),

  lastModifiedAt: null,
  setLastModifiedAt: (ts) => set({ lastModifiedAt: ts || null }),

  lastModifiedBy: null,
  setLastModifiedBy: (name) => set({ lastModifiedBy: name || null }),

  /** idle | saving | saved | error */
  saveStatus: "idle",
  setSaveStatus: (status) => set({ saveStatus: status }),

  profileModalOpen: false,
  profileModalTab: "personal",
  setProfileModalOpen: (open) => set({ profileModalOpen: !!open }),
  openProfileModal: (tab = "personal") => set({ profileModalOpen: true, profileModalTab: tab }),
  setProfileModalTab: (tab) => set({ profileModalTab: tab || "personal" }),

  /** 最近聚焦/编辑的节点，用于视口回正 */
  lastFocusedNodeId: null,
  setLastFocusedNodeId: (id) => set({ lastFocusedNodeId: id || null }),

  renameRequest: 0,
  requestRename: () => set((s) => ({ renameRequest: s.renameRequest + 1 })),

  snapToGrid: getInitialBool(SNAP_KEY, false),
  setSnapToGrid: (on) => {
    try {
      localStorage.setItem(SNAP_KEY, on ? "1" : "0")
    } catch {
      /* ignore */
    }
    set({ snapToGrid: !!on })
  },
  toggleSnapToGrid: () => {
    const next = !get().snapToGrid
    get().setSnapToGrid(next)
  },

  minimapOpen: getInitialBool(MINIMAP_KEY, false),
  setMinimapOpen: (open) => {
    try {
      localStorage.setItem(MINIMAP_KEY, open ? "1" : "0")
    } catch {
      /* ignore */
    }
    set({ minimapOpen: !!open })
  },
  toggleMinimap: () => {
    const next = !get().minimapOpen
    get().setMinimapOpen(next)
  },

  // ── Canvas UI state ──────────────────────────────────────
  hasShapes: false,
  setHasShapes: (v) => set({ hasShapes: v }),

  /** PromptBar 与节点双向同步：{ nodeId, text } */
  promptBarSync: { nodeId: null, text: "" },
  syncPromptBar: (nodeId, text) =>
    set({ promptBarSync: { nodeId, text: text ?? "" } }),

  canvasId: null,
  setCanvasId: (id) => set({ canvasId: id || null }),

  projectVersion: 1,
  setProjectVersion: (v) => set({ projectVersion: Number(v) || 1 }),

  projectTeamId: null,
  setProjectTeamId: (id) => set({ projectTeamId: id || null }),

  /** 左侧飞出：资产库 */
  assetLibraryOpen: false,
  setAssetLibraryOpen: (open) => set({ assetLibraryOpen: !!open }),
  /** 打开资产库时的一次性视图偏好（主体/角色/场景等） */
  assetLibraryPref: null,
  setAssetLibraryPref: (pref) => set({ assetLibraryPref: pref || null }),
  openAssetLibrary: (pref) =>
    set({
      assetLibraryOpen: true,
      genHistoryOpen: false,
      assetLibraryPref: pref || null,
    }),
  toggleAssetLibrary: () =>
    set((s) => ({
      assetLibraryOpen: !s.assetLibraryOpen,
      genHistoryOpen: s.assetLibraryOpen ? s.genHistoryOpen : false,
    })),

  /** 左侧飞出：生成历史 */
  genHistoryOpen: false,
  setGenHistoryOpen: (open) => set({ genHistoryOpen: !!open }),
  toggleGenHistory: () =>
    set((s) => ({
      genHistoryOpen: !s.genHistoryOpen,
      assetLibraryOpen: s.genHistoryOpen ? s.assetLibraryOpen : false,
    })),
  genHistoryExpanded: false,
  setGenHistoryExpanded: (v) => set({ genHistoryExpanded: !!v }),

  /** 飞出面板 → 画布 指针拖拽 */
  dragPlaceSession: null,
  setDragPlaceSession: (session) => set({ dragPlaceSession: session }),

  // ── Active tool (mirrors tldraw but exposed globally) ────
  activeTool: "select",
  setActiveTool: (tool) => set({ activeTool: tool }),

  /** 评论模式：画布左侧工具栏开关 */
  commentMode: getInitialBool(COMMENT_MODE_KEY, false),
  commentTargetNodeId: null,
  setCommentMode: (on) => {
    try {
      localStorage.setItem(COMMENT_MODE_KEY, on ? "1" : "0")
    } catch {
      /* ignore */
    }
    set({
      commentMode: !!on,
      commentTargetNodeId: on ? get().commentTargetNodeId : null,
    })
  },
  toggleCommentMode: () => {
    const next = !get().commentMode
    get().setCommentMode(next)
  },
  setCommentTargetNodeId: (nodeId) => set({ commentTargetNodeId: nodeId || null }),

  // ── 画布导航：滚轮平移 / 滚轮缩放 ─────────────────────
  canvasNavMode: getInitialCanvasNavMode(),
  setCanvasNavMode: (mode) => {
    const next =
      mode === CANVAS_NAV_MODES.SCROLL_ZOOM
        ? CANVAS_NAV_MODES.SCROLL_ZOOM
        : CANVAS_NAV_MODES.SCROLL_PAN
    try {
      localStorage.setItem(CANVAS_NAV_MODE_STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
    set({ canvasNavMode: next })
  },
}))
