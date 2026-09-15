import { Navigate, Route, Routes } from 'react-router'
import { hasToken } from '@/lib/token'
import { LoginPage } from '@/features/auth/LoginPage'
import { DeskPage } from '@/features/material-prep/components/DeskPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!hasToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <DeskPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
