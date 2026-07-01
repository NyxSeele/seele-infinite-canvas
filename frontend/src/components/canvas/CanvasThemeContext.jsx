import { createContext, useContext, useEffect } from "react"
import { useCanvasStore } from "../../stores"

const CanvasThemeContext = createContext({ theme: "light", toggleTheme: () => {} })

export function useCanvasTheme() {
  return useContext(CanvasThemeContext)
}

export function CanvasThemeProvider({ children }) {
  const theme = useCanvasStore((s) => s.theme)
  const toggleTheme = useCanvasStore((s) => s.toggleTheme)

  useEffect(() => {
    document.body.setAttribute("data-canvas-theme", theme)
    return () => {
      document.body.removeAttribute("data-canvas-theme")
    }
  }, [theme])

  return (
    <CanvasThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </CanvasThemeContext.Provider>
  )
}
