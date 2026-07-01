import { Navigate } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext.jsx"
import VeloraLoadingPage from "./common/VeloraLoadingPage.jsx"

export default function AdminRoute({ children }) {
  const { user, loading, isAuthenticated } = useAuth()

  if (loading) {
    return <VeloraLoadingPage />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (user?.role !== "admin") {
    return <Navigate to="/canvas" replace />
  }

  return children
}
