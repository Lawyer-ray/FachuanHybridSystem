import { useNavigate } from 'react-router'
import { FileQuestion } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'

export function NotFoundPage() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="w-20 h-20 rounded-full bg-muted flex items-center justify-center mb-6">
        <FileQuestion className="w-10 h-10 text-muted-foreground" />
      </div>

      <h1 className="text-6xl font-bold text-muted-foreground mb-4">404</h1>

      <h2 className="text-xl font-semibold text-foreground mb-2">页面未找到</h2>

      <p className="text-sm text-muted-foreground mb-8 text-center max-w-md">
        抱歉，您访问的页面不存在或已被移除。请检查网址是否正确，或返回首页继续操作。
      </p>

      <div className="flex gap-3">
        <Button variant="outline" onClick={() => navigate(-1)}>
          返回上一页
        </Button>
        <Button onClick={() => navigate(PATHS.ADMIN_DASHBOARD)}>
          返回首页
        </Button>
      </div>
    </div>
  )
}
