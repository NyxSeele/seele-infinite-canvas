import { useEffect } from "react"
import { createRoot } from "react-dom/client"
import { readLocale } from "./utils/locale"
import "./index.css"
import "./styles/velora-brand.css"
import "./styles/scopeSwitchTransition.css"
import "./styles/themeTransition.css"

document.documentElement.lang = readLocale() === "en" ? "en" : "zh-CN"
import { AuthProvider } from "./contexts/AuthContext.jsx"
import ProductNoticeModal from "./components/common/ProductNoticeModal.jsx"
import AppRouter from "./router.jsx"

function PreventBrowserZoom() {
  useEffect(() => {
    const onWheel = (e) => {
      if (e.ctrlKey) e.preventDefault()
    }
    const onKeyDown = (e) => {
      if (!e.ctrlKey) return
      if (e.key === "=" || e.key === "+" || e.key === "-" || e.key === "0") {
        e.preventDefault()
      }
    }
    window.addEventListener("wheel", onWheel, { passive: false })
    window.addEventListener("keydown", onKeyDown)
    return () => {
      window.removeEventListener("wheel", onWheel)
      window.removeEventListener("keydown", onKeyDown)
    }
  }, [])
  return null
}

createRoot(document.getElementById("root")).render(
  <AuthProvider>
    <PreventBrowserZoom />
    <ProductNoticeModal />
    <AppRouter />
  </AuthProvider>
)
