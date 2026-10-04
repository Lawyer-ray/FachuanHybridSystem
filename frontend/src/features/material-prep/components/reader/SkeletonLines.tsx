/** PDF 页 / 懒渲染占位的骨架屏（PageBody 与 PdfPageView 共用） */
export function SkeletonLines() {
  return (
    <div className="mx-auto w-full animate-pulse space-y-3 p-5">
      <div className="h-3 w-2/5 rounded bg-zinc-200" />
      <div className="h-3 w-full rounded bg-zinc-200" />
      <div className="h-3 w-3/4 rounded bg-zinc-200" />
      <div className="h-3 w-5/6 rounded bg-zinc-200" />
      <div className="h-3 w-full rounded bg-zinc-200" />
      <div className="h-3 w-2/3 rounded bg-zinc-200" />
    </div>
  )
}
