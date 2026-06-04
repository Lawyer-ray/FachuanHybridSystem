import { Skeleton } from '@/components/ui/skeleton'

/**
 * 页面级骨架屏
 *
 * 用于 Suspense fallback，在懒加载 chunk 未缓存时显示。
 * 只替换内容区，侧边栏和导航栏保持不动。
 */
export function PageSkeleton() {
  return (
    <div className="space-y-4">
      {/* 标题区域骨架 */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-9 w-24" />
      </div>

      {/* 内容区域骨架 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Skeleton className="h-32 rounded-lg" />
        <Skeleton className="h-32 rounded-lg" />
        <Skeleton className="h-32 rounded-lg" />
      </div>

      {/* 表格/列表骨架 */}
      <div className="space-y-2">
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-10 w-full rounded-lg" />
      </div>
    </div>
  )
}
