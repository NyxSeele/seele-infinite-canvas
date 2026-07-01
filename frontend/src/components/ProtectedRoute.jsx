import { Navigate, useLocation } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext.jsx"
import VeloraLoadingPage from "./common/VeloraLoadingPage.jsx"

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <VeloraLoadingPage />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return children
}
