import { useRouteError, isRouteErrorResponse, useNavigate } from 'react-router'
import { AlertTriangle, RefreshCw, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function RouteError() {
  const error = useRouteError()
  const navigate = useNavigate()

  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : '发生了未知错误'

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8">
      <div className="flex size-16 items-center justify-center rounded-full bg-destructive/10">
        <AlertTriangle className="size-8 text-destructive" />
      </div>
      <div className="text-center">
        <h2 className="text-lg font-semibold">页面加载失败</h2>
        <p className="text-muted-foreground mt-1 text-sm">{message}</p>
      </div>
      <div className="flex gap-3">
        <Button variant="outline" onClick={() => navigate(-1)}>
          <ArrowLeft className="mr-2 size-4" />
          返回
        </Button>
        <Button onClick={() => window.location.reload()}>
          <RefreshCw className="mr-2 size-4" />
          刷新页面
        </Button>
      </div>
    </div>
  )
}
