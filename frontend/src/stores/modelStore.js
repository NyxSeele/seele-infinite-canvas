import { create } from "zustand"
import api from "../services/api"

export const useModelStore = create((set, get) => ({
  imageModels: [],
  videoModels: [],
  textModels: [],
  loading: false,
  error: null,
  fetched: false,

  fetchModels: async () => {
    if (get().loading) return
    set({ loading: true, error: null })
    try {
      const { data } = await api.get("/api/models")
      const models = data?.models || []
      set({
        textModels: models.filter((m) => m.category === "text"),
        imageModels: models.filter((m) => m.category === "image"),
        videoModels: models.filter((m) => m.category === "video"),
        loading: false,
        fetched: true,
        error: null,
      })
    } catch (err) {
      console.error("加载可用模型失败", err)
      set({
        loading: false,
        error: "加载失败",
        fetched: true,
      })
    }
  },
}))
