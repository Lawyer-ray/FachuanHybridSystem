import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import App from './App'
import { useAuth } from '@/features/auth'
import { setupGlobalErrorLogging } from '@/lib/error-logging'
import { errMessage } from '@/lib/errors'
import './index.css'

setupGlobalErrorLogging()
useAuth.getState().init()

const queryClient = new QueryClient({
  // 变更失败的统一兜底：useMutation 自带 onError 的视为局部已处理（跳过），
  // 其余在这里弹一次错误 toast——此前无人兜底的变更失败会被静默吞掉，
  // 用户只看到「点了没反应」。文案与各域局部 onError 的口径一致（errMessage 提取）。
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      if (mutation.options?.onError) return
      toast.error(errMessage(error, '操作失败，请稍后重试'))
    },
  }),
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
