import { lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import ProtectedRoute from "./components/ProtectedRoute.jsx"
import AdminRoute from "./components/AdminRoute.jsx"
import Login from "./pages/Login.jsx"
import Register from "./pages/Register.jsx"
import Workspace from "./pages/Workspace.jsx"
import JoinTeam from "./pages/JoinTeam.jsx"
import NetworkTest from "./pages/NetworkTest.jsx"
import TeamFiles from "./pages/TeamFiles.jsx"
import AppUpdateBanner from "./components/common/AppUpdateBanner.jsx"
import VeloraLoadingPage from "./components/common/VeloraLoadingPage.jsx"

const Canvas = lazy(() => import("./pages/Canvas.jsx"))
const WorkspaceProjects = lazy(() => import("./pages/WorkspaceProjects.jsx"))
const AdminLayout = lazy(() => import("./pages/Admin/AdminLayout.jsx"))
const Dashboard = lazy(() => import("./pages/Admin/Dashboard.jsx"))
const UserManagement = lazy(() => import("./pages/Admin/UserManagement.jsx"))
const ModelManagement = lazy(() => import("./pages/Admin/ModelManagement.jsx"))
const TaskMonitor = lazy(() => import("./pages/Admin/TaskMonitor.jsx"))
const FeedbackAnalysis = lazy(() => import("./pages/Admin/FeedbackAnalysis.jsx"))
const UserFiles = lazy(() => import("./pages/Admin/UserFiles.jsx"))
const ReviewPublish = lazy(() => import("./pages/ReviewPublish.jsx"))
const ReviewSite = lazy(() => import("./pages/ReviewSite.jsx"))
const ReviewDetail = lazy(() => import("./pages/ReviewDetail.jsx"))

export default function AppRouter() {
  return (
    <BrowserRouter>
      <AppUpdateBanner />
      <Suspense fallback={<VeloraLoadingPage message="正在加载…" />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/review" element={<ReviewSite />} />
          <Route path="/review/:id" element={<ReviewDetail />} />
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
            path="/team-files"
            element={
              <ProtectedRoute>
                <TeamFiles />
              </ProtectedRoute>
            }
          />
          <Route
            path="/review-publish"
            element={
              <ProtectedRoute>
                <ReviewPublish />
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
            path="/network-test"
            element={
              <ProtectedRoute>
                <NetworkTest />
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
            <Route path="files" element={<UserFiles />} />
            <Route path="feedback" element={<FeedbackAnalysis />} />
          </Route>
          <Route path="/" element={<Navigate to="/workspace" replace />} />
          <Route path="*" element={<Navigate to="/workspace" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
