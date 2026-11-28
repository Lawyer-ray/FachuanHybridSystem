import { useEffect, useRef, useState } from 'react'
import { FileText } from 'lucide-react'
import type { BundleMat, RotDeg } from '../../types'
import { PdfPageView } from './PdfPageView'
import { PhotoPageView } from './PhotoPageView'
import { SkeletonLines } from './SkeletonLines'

/**
 * 页卡里的**页体本身**：按素材类型选渲染分支（PDF / 照片 / Office 占位），
 * 以及「滚到附近才真正挂载」的懒加载门。
 *
 * 从 `PageCell.tsx` 拆出的原因：`PageCell` 关心的是**叠在页上的交互**——拖框取字、
 * 选页、定位框/引擎双框的百分比坐标（都以页体这个盒子为基准），而这里关心的是
 * 「这张图怎么取、什么时候取」。两者的改动理由不同：调懒挂载的 `rootMargin` /
 * StrictMode 洗刷逻辑不该穿过整段 pointer 事件处理，改拖框阈值也不该碰取图分支。
 *
 * ⚠️ 页体是定位框的百分比基准（rect 是相对**页面图像**归一化的），所以本组件
 * 必须渲染成一个 `relative w-full` 的盒子被 `PageCell` 包住，不能自行改布局。
 */

/** 选择页体渲染分支：视口外的页只挂骨架占位，滚近了才真正取附件渲染。
 *  92 页的大包若全部立即 mount，会同时拉取全部附件并渲染全部页位图
 *  （DPR 感知宽度下单页 ~21MB，见 PdfPageView 的驻留 img 说明）。 */
export function PageBody({
  messageId,
  p,
  mat,
  rotation = 0,
}: {
  messageId: number
  p: number
  mat: BundleMat
  rotation?: RotDeg
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)

  useEffect(() => {
    if (shown) return
    const el = hostRef.current
    // 环境不支持 IntersectionObserver 时直接渲染（退化到旧行为）
    if (!el || typeof IntersectionObserver === 'undefined') {
      setShown(true)
      return
    }
    // 上下各预渲染约两屏：滚动到达时内容已在，骨架只是首开瞬间的占位
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((en) => en.isIntersecting)) setShown(true)
      },
      { rootMargin: '1600px 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [shown])

  if (!shown) {
    return (
      <div ref={hostRef} className="w-full bg-white">
        <SkeletonLines />
      </div>
    )
  }
  if (mat.k === 'pdf')
    return <PdfPageView messageId={messageId} partIndex={mat.partIndex} pageNum={p} rotation={rotation} />
  if (mat.k === 'photo')
    return <PhotoPageView messageId={messageId} partIndex={mat.partIndex} rotation={rotation} />
  return <OfficePlaceholder mat={mat} />
}

function OfficePlaceholder({ mat }: { mat: BundleMat }) {
  return (
    <div className="flex aspect-[3/4] flex-col items-center justify-center gap-3 bg-zinc-50 p-6 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-xl bg-secondary text-secondary-foreground">
        <FileText className="h-7 w-7" />
      </span>
      <div>
        <p className="text-sm font-medium">{mat.n}</p>
        <p className="mt-1 max-w-[220px] text-[11px] leading-relaxed text-muted-foreground">
          Word / Excel 等格式当前按整份处理，暂不能逐页切分
        </p>
      </div>
    </div>
  )
}
