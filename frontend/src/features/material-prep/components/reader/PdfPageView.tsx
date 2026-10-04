import { useEffect, useRef, useState } from 'react'

import { canvasToRetainedImg, loadPdfDocument, pdfRenderWidthFor, releaseRetainedImg, renderPdfPage } from '@/lib/pdf'
import { fetchAttachmentBytes } from '../../api'

import { SkeletonLines } from './SkeletonLines'

/** 释放 host 内驻留 img 的 blob URL（重渲替换/卸载前调用；未登记的 no-op，幂等） */
function releaseHostRetainedImg(host: HTMLElement | null): void {
  const old = host?.querySelector('img')
  if (old) releaseRetainedImg(old)
}

export function PdfPageView({ messageId, partIndex, pageNum }: { messageId: number; partIndex: number; pageNum: number }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  // null = 尚未因宽度/DPR 变化强制重渲（首渲在渲染 effect 内自测容器宽）；
  // 有值 = 用户拉窗口/改列数/缩放/跨屏拖动后按新宽度重渲
  const [forcedWidth, setForcedWidth] = useState<number | null>(null)
  // 最近一次实际渲染用的位图宽度，供变化检测比较
  const renderedWidthRef = useRef(0)

  // 宽度变化（窗口拉宽/列数变化/缩放）→ 位图宽度显著变化时重渲。
  // 此前 effect 只依赖 [messageId, partIndex, pageNum]，位图宽度在挂载时
  // 定格——拉宽窗口或放大后小位图被 CSS 拉伸，越拉越糊。
  useEffect(() => {
    const host = hostRef.current
    if (!host || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => {
      const w = pdfRenderWidthFor(host.clientWidth)
      const prev = renderedWidthRef.current
      if (!prev || Math.abs(w - prev) > prev * 0.12) setForcedWidth(w)
    })
    ro.observe(host)
    return () => ro.disconnect()
  }, [])

  // DPR 变化（窗口跨屏拖动）不改变 CSS 宽、不触发 ResizeObserver，单独监听。
  // MQL 字符串带具体 DPR 值（如 2dppx），触发一次后浏览器 DPR 已变、不再匹配
  // 该查询——旧实现把它定格在挂载值，换屏一次后监听就永久失效。这里把当前
  // DPR 放进 state：变化后重建 MQL，保证每次换屏都能按新 DPR 触发重渲。
  const [dpr, setDpr] = useState(() => (typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1))
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia === 'undefined') return
    const mq = window.matchMedia(`(resolution: ${dpr}dppx)`)
    const onChange = () => {
      // 先记下新 DPR 让本 effect 重挂（新 DPR 的 MQL），再按新宽度强制重渲
      setDpr(window.devicePixelRatio || 1)
      const host = hostRef.current
      setForcedWidth(pdfRenderWidthFor(host?.clientWidth ?? 900))
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [dpr])

  useEffect(() => {
    let cancelled = false
    setState('loading')
    // cleanup 里 ref 可能已指向新节点：捕获本 effect 实例挂载时的 host
    const hostAtMount = hostRef.current
    async function run() {
      try {
        const bytes = await fetchAttachmentBytes(messageId, partIndex)
        const doc = await loadPdfDocument(`${messageId}:${partIndex}`, bytes)
        // 按实际显示宽 × DPR 渲染：固定 900 位图在 Retina 上被拉伸 ~2 倍，
        // 文字发虚（原生查看器清晰正是因为按屏幕物理像素足额采样）
        const host = hostRef.current
        const targetWidth = forcedWidth ?? pdfRenderWidthFor(host?.clientWidth ?? 900)
        renderedWidthRef.current = targetWidth
        const canvas = await renderPdfPage(doc, pageNum, targetWidth)
        if (cancelled) return
        if (!host) return
        // 页宽随列数/缩放收缩时，canvas 必须跟随容器等比缩放；
        // 否则固定内禀宽会把窄列撑爆，造成文字被横向压缩变形（"挤压"）
        canvas.style.width = '100%'
        canvas.style.height = 'auto'
        // 清掉上一轮的驻留 img 前先回收它的 blob URL（ObjectURL 不回收会随重渲线性泄漏）
        releaseHostRetainedImg(host)
        host.innerHTML = ''
        host.appendChild(canvas)
        setState('ready')
        // canvas 位图（~21MB/页）页面无法回收，92 页大包滚完会 ~1.9GB；
        // 编码成 WebP img 驻留（~250KB/页），浏览器可自动丢弃离屏解码位图
        const img = await canvasToRetainedImg(canvas)
        if (cancelled || !host.isConnected) {
          // 本轮渲染已作废：刚登记的 img 不会挂载，就地回收 blob URL
          releaseRetainedImg(img)
          return
        }
        img.style.width = '100%'
        img.style.height = 'auto'
        host.innerHTML = ''
        host.appendChild(img)
      } catch {
        if (!cancelled) setState('error')
      }
    }
    void run()
    return () => {
      cancelled = true
      // 卸载/重跑时 host 里可能还挂着上一轮的驻留 img（新一轮清空前）——一并回收；
      // 新一轮成功路径在清 host 前也会 release，幂等不会双重 revoke
      releaseHostRetainedImg(hostAtMount)
    }
  }, [messageId, partIndex, pageNum, forcedWidth])

  return (
    <div className="relative w-full bg-white">
      {state === 'loading' && <SkeletonLines />}
      {state === 'error' && (
        <div className="grid h-48 place-items-center text-xs text-muted-foreground">该页加载失败</div>
      )}
      {/* 无 max-w 上限：页宽治理在 layout.ts 的 fitPageWidth（缩放可超 900 允许横向滚动），
          这里再 clamp 会让 >100% 的缩放失效 */}
      <div ref={hostRef} className="mx-auto w-full" />
    </div>
  )
}
