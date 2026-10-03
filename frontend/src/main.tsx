import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from '@/components/ui/sonner'
import App from './App'
import { useAuth } from '@/features/auth'
import { setupGlobalErrorLogging } from '@/lib/error-logging'
import './index.css'

setupGlobalErrorLogging()
useAuth.getState().init()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      // 会话过期类错误（api.ts 401 刷新失败路径）不重试：重试只会再吃一次 401；
      // 其余错误重试一次（与原 retry: 1 口径一致）
      retry: (failureCount, error) =>
        failureCount < 1 && !(error instanceof Error && error.message.includes('Session expired')),
    },
  },
})

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster position="top-center" richColors />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
