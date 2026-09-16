import { toast } from 'sonner'
import { canvasToBlob, imageRegionBlob, loadPdfDocument, renderPdfPageRegion } from '@/lib/pdf'
import { fetchAttachmentBytes, ocrImage } from '../../api'
import { matLabel, setInfoSource, setInfoValue } from '../../draft'
import { useReader } from '../../store'
import type { PageRect } from './PageCell'

/** 标来源 ⇒ 框选 ⇒ RapidOCR 的完整流程：点页记来源、拖框取字、确认填入 */
export function useReaderOcr() {
  const pickPage = (mi: number, p: number) => {
    const s = useReader.getState()
    const pi = s.pickInfo
    if (pi < 0) return
    const label = `${matLabel(s.draft?.mats || [], mi)} 第 ${p} 页`
    s.update((d) => setInfoSource(d, pi, label, { mi, p }))
    s.setPickInfo(-1)
    toast.success(`已记来源：${label}`)
  }

  const runOcr = async (mi: number, p: number, rect: PageRect) => {
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

  const onOcrBox = (mi: number, p: number, rect: PageRect) => {
    if (useReader.getState().pickInfo < 0) return
    void runOcr(mi, p, rect)
  }

  const ocrOk = () => {
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
  }

  return { pickPage, onOcrBox, ocrOk }
}
