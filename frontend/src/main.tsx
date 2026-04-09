import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import { ThemeProvider } from 'next-themes'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from '@/components/ui/sonner'
import { router } from '@/routes'
import './index.css'

// 创建 QueryClient 实例
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 分钟
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

/**
 * 全局加载状态组件
 */
function GlobalLoading() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="text-muted-foreground">加载中...</div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
        <Suspense fallback={<GlobalLoading />}>
          <RouterProvider router={router} />
        </Suspense>
        <Toaster />
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>
)
