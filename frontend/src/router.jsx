import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import ProtectedRoute from "./components/ProtectedRoute.jsx"
import AdminRoute from "./components/AdminRoute.jsx"
import Login from "./pages/Login.jsx"
import Register from "./pages/Register.jsx"
import Workspace from "./pages/Workspace.jsx"
import WorkspaceProjects from "./pages/WorkspaceProjects.jsx"
import JoinTeam from "./pages/JoinTeam.jsx"
import Canvas from "./pages/Canvas.jsx"
import AdminLayout from "./pages/Admin/AdminLayout.jsx"
import Dashboard from "./pages/Admin/Dashboard.jsx"
import UserManagement from "./pages/Admin/UserManagement.jsx"
import ModelManagement from "./pages/Admin/ModelManagement.jsx"
import TaskMonitor from "./pages/Admin/TaskMonitor.jsx"

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/workspace"
          element={
            <ProtectedRoute>
              <Workspace />
            </ProtectedRoute>
          }
        />
        <Route
          path="/workspace/projects"
          element={
            <ProtectedRoute>
              <WorkspaceProjects />
            </ProtectedRoute>
          }
        />
        <Route
          path="/join-team"
          element={
            <ProtectedRoute>
              <JoinTeam />
            </ProtectedRoute>
          }
        />
        <Route
          path="/canvas/:projectId"
          element={
            <ProtectedRoute>
              <Canvas />
            </ProtectedRoute>
          }
        />
        <Route
          path="/canvas"
          element={
            <ProtectedRoute>
              <Canvas />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <AdminLayout />
            </AdminRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="users" element={<UserManagement />} />
          <Route path="models" element={<ModelManagement />} />
          <Route path="tasks" element={<TaskMonitor />} />
        </Route>
        <Route path="/" element={<Navigate to="/workspace" replace />} />
        <Route path="*" element={<Navigate to="/workspace" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
