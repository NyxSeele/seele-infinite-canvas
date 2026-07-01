import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import api from "../services/api"
import { useTeamStore } from "../stores/teamStore"
import { clearMediaTicket, refreshMediaTicket } from "../utils/mediaTicket"
import { applyServerProfileToCache, migrateLocalProfileIfNeeded } from "../utils/canvas/profileSync"
import { wsManager } from "../services/ws"

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchMe = useCallback(async ({ skipMigration = false } = {}) => {
    const token = localStorage.getItem("access_token")
    if (!token) {
      setUser(null)
      setLoading(false)
      return null
    }
    try {
      const res = await api.get("/api/auth/me")
      let profile = res.data
      if (!skipMigration) {
        profile = await migrateLocalProfileIfNeeded(profile)
      } else {
        applyServerProfileToCache(profile)
      }
      setUser(profile)
      try {
        await refreshMediaTicket(api)
      } catch {
        clearMediaTicket()
      }
      void useTeamStore.getState().ensureTeamsLoaded()
      return profile
    } catch {
      localStorage.removeItem("access_token")
      localStorage.removeItem("refresh_token")
      clearMediaTicket()
      setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMe()
  }, [fetchMe])

  const login = useCallback(async (username_or_email, password) => {
    const res = await api.post("/api/auth/login", { username_or_email, password })
    localStorage.setItem("access_token", res.data.access_token)
    localStorage.setItem("refresh_token", res.data.refresh_token)
    try {
      await refreshMediaTicket(api)
    } catch {
      clearMediaTicket()
    }
    wsManager.connect()
    await fetchMe()
    return res.data
  }, [fetchMe])

  const register = useCallback(async (username, email, password) => {
    const res = await api.post("/api/auth/register", { username, email, password })
    localStorage.setItem("access_token", res.data.access_token)
    localStorage.setItem("refresh_token", res.data.refresh_token)
    await fetchMe()
    return res.data
  }, [fetchMe])

  const logout = useCallback(async () => {
    const refresh = localStorage.getItem("refresh_token")
    try {
      if (refresh) {
        await api.post("/api/auth/logout", { refresh_token: refresh })
      }
    } catch {
      /* ignore */
    }
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    clearMediaTicket()
    wsManager.disconnect()
    useTeamStore.getState().reset()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: !!user,
      login,
      register,
      logout,
      refreshUser: () => fetchMe({ skipMigration: true }),
    }),
    [user, loading, login, register, logout, fetchMe]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
