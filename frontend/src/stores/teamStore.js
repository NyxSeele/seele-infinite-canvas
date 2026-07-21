import { create } from "zustand"
import { fetchMyTeams } from "../services/teamApi"

const STORAGE_KEY = "ai_studio_active_team_id"
const HTTP_MIN_GAP_MS = 5000
const USER_ACTION_MIN_GAP_MS = 2000

let inflightPromise = null
let lastHttpAt = 0
let scheduleRefreshTimer = null
let pendingRefreshAfterInflight = false

function readStoredTeamId() {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v || null
  } catch {
    return null
  }
}

function writeStoredTeamId(id) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export const useTeamStore = create((set, get) => ({
  ownedTeam: null,
  joinedTeams: [],
  allTeams: [],
  activeTeamId: readStoredTeamId(),
  loading: false,
  error: null,
  loaded: false,

  activeTeam: () => {
    const { activeTeamId, allTeams } = get()
    if (!activeTeamId) return null
    return allTeams.find((t) => t.id === activeTeamId) || null
  },

  isTeamContext: () => !!get().activeTeamId,

  /** 登录后会话内只拉一次；用户操作后请用 refreshTeams */
  ensureTeamsLoaded: () => {
    const state = get()
    if (state.loaded || state.loading || inflightPromise) {
      return inflightPromise
    }
    return get().fetchTeams()
  },

  /** 团队管理里用户主动操作后刷新 */
  refreshTeams: () => get().fetchTeams({ force: true, userAction: true }),

  /** team-context-changed 等高频事件：防抖合并为一次刷新 */
  scheduleRefreshTeams: () => {
    if (inflightPromise) {
      pendingRefreshAfterInflight = true
      return inflightPromise
    }
    if (scheduleRefreshTimer) {
      window.clearTimeout(scheduleRefreshTimer)
    }
    scheduleRefreshTimer = window.setTimeout(() => {
      scheduleRefreshTimer = null
      void get().fetchTeams({ force: true, userAction: true })
    }, 400)
  },

  fetchTeams: async (options = false) => {
    const opts =
      typeof options === "boolean"
        ? { force: options, userAction: options }
        : options
    const { force = false, userAction = false } = opts
    const state = get()

    if (inflightPromise) return inflightPromise

    if (!force && state.loaded) return

    const now = Date.now()
    const minGap = userAction ? USER_ACTION_MIN_GAP_MS : HTTP_MIN_GAP_MS
    if (now - lastHttpAt < minGap) {
      if (state.loaded) return Promise.resolve()
      return
    }

    const run = async () => {
      set({ loading: true, error: null })
      lastHttpAt = Date.now()
      try {
        const data = await fetchMyTeams()
        const owned = data?.owned || null
        const joined = Array.isArray(data?.joined) ? data.joined : []
        const allTeams = [...(owned ? [owned] : []), ...joined]
        let activeTeamId = get().activeTeamId
        if (activeTeamId && !allTeams.some((t) => t.id === activeTeamId)) {
          activeTeamId = null
          writeStoredTeamId(null)
        }
        set({
          ownedTeam: owned,
          joinedTeams: joined,
          allTeams,
          activeTeamId,
          loading: false,
          loaded: true,
          error: null,
        })
      } catch (err) {
        const status = err?.response?.status
        set({
          loading: false,
          loaded: state.loaded,
          error: err?.response?.data?.detail || err.message || "加载团队失败",
        })
        if (status === 429) {
          console.warn("[team] 请求过于频繁，已暂停自动重试")
        }
      }
    }

    inflightPromise = run().finally(() => {
      inflightPromise = null
      if (pendingRefreshAfterInflight) {
        pendingRefreshAfterInflight = false
        const gap = Date.now() - lastHttpAt
        const delay = Math.max(0, USER_ACTION_MIN_GAP_MS - gap)
        window.setTimeout(() => {
          void get().fetchTeams({ force: true, userAction: true })
        }, delay)
      }
    })
    return inflightPromise
  },

  setActiveTeamId: (teamId) => {
    const id = teamId || null
    writeStoredTeamId(id)
    set({ activeTeamId: id })
  },

  switchToPersonal: () => {
    writeStoredTeamId(null)
    set({ activeTeamId: null })
  },

  reset: () => {
    inflightPromise = null
    lastHttpAt = 0
    pendingRefreshAfterInflight = false
    if (scheduleRefreshTimer) {
      window.clearTimeout(scheduleRefreshTimer)
      scheduleRefreshTimer = null
    }
    writeStoredTeamId(null)
    set({
      ownedTeam: null,
      joinedTeams: [],
      allTeams: [],
      activeTeamId: null,
      loading: false,
      error: null,
      loaded: false,
    })
  },
}))
