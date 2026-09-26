import { detectMaterialKind, loadPdfDocument } from '@/lib/pdf'
import { fetchAttachmentBytes } from '../api'
import type {
  AttachmentMeta,
  BundleMat,
  DraftState,
  InboxMessageDetail,
  PageKey,
  Segment,
} from '../types'

/**
 * 附件 → 源素材解析（本目录唯一含副作用的模块：PDF 需载入文档取页数）。
 */

/** 每个附件算出一个源素材，并解析真实页数（PDF 需要载入文档取页数）。 */
export async function resolveMats(msg: InboxMessageDetail): Promise<BundleMat[]> {
  const mats: BundleMat[] = []
  for (const att of msg.attachments) {
    const n = effectiveFileName(att)
    const k = detectMaterialKind(att.content_type, n)
    let pages = 1
    if (k === 'pdf') {
      try {
        const bytes = await fetchAttachmentBytes(msg.id, att.part_index)
        const doc = await loadPdfDocument(`${msg.id}:${att.part_index}`, bytes)
        pages = doc.numPages
      } catch {
        pages = 1
      }
    }
    mats.push({ partIndex: att.part_index, n, k, pages })
  }
  return mats
}

/** 附件展示名：优先自定义名，其次原始名 */
export function effectiveFileName(att: AttachmentMeta): string {
  return att.custom_filename?.trim() || att.original_filename || att.filename
}

/** 每个源素材默认一整段，覆盖其全部页 */
export function initialSegments(mats: BundleMat[]): Segment[] {
  return mats.map((m, mi) => {
    const refs: PageKey[] = []
    for (let p = 1; p <= m.pages; p++) refs.push({ mi, p })
    return { t: '', fn: m.n, refs, manual: false }
  })
}

/** 初始草稿：每个附件一段，右栏默认只记委托人 + 对方当事人 */
export function buildInitialDraft(_msg: InboxMessageDetail, mats: BundleMat[]): DraftState {
  return {
    mats,
    segs: initialSegments(mats),
    infos: [
      { k: '委托人', v: '', src: '', srcRef: null, ph: '姓名或单位' },
      { k: '对方当事人', v: '', src: '', srcRef: null, ph: '姓名或单位', hint: '多个用、分隔' },
    ],
  }
}
