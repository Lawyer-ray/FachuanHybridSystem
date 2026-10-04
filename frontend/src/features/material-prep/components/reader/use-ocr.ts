import { useCallback } from 'react'
import { toast } from 'sonner'
import { canvasToBlob, imageRegionBlob, loadPdfDocument, renderPdfPageRegion } from '@/lib/pdf'
import { fetchAttachmentBytes, ocrImage } from '../../api'
import { matLabel, setInfoSource, setInfoValue } from '../../draft'
import { useReader } from '../../store'
import type { PageRect } from './PageCell'

/** 标来源 ⇒ 框选 ⇒ RapidOCR 的完整流程：点页记来源、拖框取字、确认填入 */

/**
 * 框选取字主流程（模块级函数）。
 *
 * 契约：只经 useReader.getState() 在调用时读所需状态，**不得读取任何
 * 响应式值**（props / hook 内的 state）——调用方 onOcrBox 用 useCallback([])
 * 固化引用以命中 PageCell 的 memo，若此处捕获渲染期快照，会永远拿到首帧值。
 * 收敛到模块级后该约束天然成立（无闭包可捕获），也是它被提出组件外的理由。
 */
async function runOcr(mi: number, p: number, rect: PageRect) {
  const s = useReader.getState()
  const d = s.draft
  if (!d) return
  const m = d.mats[mi]
  if (!m) {
    s.setOcrPending(null)
    return
  }
  s.setOcrPending({ mi, p, rect, text: '', loading: true })
  try {
    let text = ''
    if (m.k === 'pdf') {
      const bytes = await fetchAttachmentBytes(s.openId as number, m.partIndex)
      const doc = await loadPdfDocument(`${s.openId}:${m.partIndex}`, bytes)
      const canvas = await renderPdfPageRegion(doc, p, rect)
      const blob = await canvasToBlob(canvas)
      const res = await ocrImage(blob)
      text = res.blocks.map((b) => b.text).filter(Boolean).join('\n')
    } else if (m.k === 'photo') {
      const bytes = await fetchAttachmentBytes(s.openId as number, m.partIndex)
      const blob = await imageRegionBlob(bytes, rect)
      const res = await ocrImage(blob)
      text = res.blocks.map((b) => b.text).filter(Boolean).join(' ')
    } else {
      toast('Word / Excel 暂不支持逐页取字，已在右栏记下来源页码')
      s.setOcrPending({ mi, p, rect, text: '', loading: false })
      return
    }
    s.setOcrPending({ mi, p, rect, text, loading: false })
  } catch {
    s.setOcrPending({ mi, p, rect, text: '', loading: false })
    toast.error('OCR 识别失败，可重框或手打')
  }
}

export function useReaderOcr() {
  // 固化回调引用：让 Flow → PageCell 的 memo 命中（内部直读 getState，无外部依赖）
  const pickPage = useCallback((mi: number, p: number) => {
    const s = useReader.getState()
    const pi = s.pickInfo
    if (pi < 0) return
    const label = `${matLabel(s.draft?.mats || [], mi)} 第 ${p} 页`
    s.update((d) => setInfoSource(d, pi, label, { mi, p }))
    s.setPickInfo(-1)
    toast.success(`已记来源：${label}`)
  }, [])

  // 固化回调引用（useCallback([])）：命中 PageCell memo；因此 runOcr 及本回调
  // **不得读取响应式值**——需要的运行时状态一律走 useReader.getState()
  const onOcrBox = useCallback((mi: number, p: number, rect: PageRect) => {
    if (useReader.getState().pickInfo < 0) return
    void runOcr(mi, p, rect)
  }, [])

  const ocrOk = useCallback(() => {
    const s = useReader.getState()
    const pend = s.ocrPending
    if (!pend) return
    const di = s.pickInfo
    s.setOcrPending(null)
    s.setPickInfo(-1)
    if (di < 0) return
    const fieldName = s.draft?.infos[di]?.k || '字段'
    const label = `${matLabel(s.draft?.mats || [], pend.mi)} 第 ${pend.p} 页`
    s.update((d) => {
      let nd = setInfoSource(d, di, label, { mi: pend.mi, p: pend.p, rect: pend.rect })
      if (pend.text.trim()) nd = setInfoValue(nd, di, pend.text.trim())
      return nd
    })
    toast.success(`已填入「${fieldName}」`)
  }, [])

  return { pickPage, onOcrBox, ocrOk }
}
