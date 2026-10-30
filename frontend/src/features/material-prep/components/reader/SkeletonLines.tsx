/**
 * PDF 页 / 懒渲染占位的骨架屏（PageBody 与 PdfPageView 共用）。
 *
 * ═══ 为什么必须撑满整页高度 ═══
 * 骨架原来只有 6 行（约 120px），而真实 A4 页渲染出来是 1236px。
 * 视口外的页挂的是骨架，滚近了才换成真页 —— 每换一页总高度就涨 1100px，
 * 滚动条随之变短。用户往下滚时看到的是「内容越滚越多、滚动条一直缩」，
 * 像在无休止加载（实测 4 张图 → 8 张 → 13 张，scrollHeight 11803 → 16059 → 21379）。
 *
 * 骨架**必须预留和真页一样的高度**，滚动条才是稳定的 ——
 * 这是懒渲染的基本要求：占位不占位，等于一边滚一边把页面撑长。
 * aspect-[1/1.414] 是 A4 比例，与 PdfPageView 的渲染尺寸一致。
 */
export function SkeletonLines() {
  return (
    <div className="mx-auto aspect-[1/1.414] w-full animate-pulse space-y-3 p-5">
      <div className="h-3 w-2/5 rounded bg-zinc-200" />
      <div className="h-3 w-full rounded bg-zinc-200" />
      <div className="h-3 w-3/4 rounded bg-zinc-200" />
      <div className="h-3 w-5/6 rounded bg-zinc-200" />
      <div className="h-3 w-full rounded bg-zinc-200" />
      <div className="h-3 w-2/3 rounded bg-zinc-200" />
    </div>
  )
}
