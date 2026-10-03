import { loadPdfDocument } from '@/lib/pdf'
import { fetchAttachmentBytes } from '../api'
import type {
  AttachmentMeta,
  BundleMat,
  DraftState,
  InboxMessageDetail,
  PageKey,
  Segment,
} from '../types'
import { nextSegId } from './seg-id'

/**
 * 附件 → 源素材解析（本目录唯一含副作用模块：PDF 需载入文档取页数）。
 */

/** 根据附件 content_type / 文件名推断素材类型（material-prep 专属领域语义，随本模块走） */
function detectMaterialKind(contentType: string | undefined, filename: string): 'pdf' | 'photo' | 'office' {
  const ct = (contentType || '').toLowerCase()
  const name = filename.toLowerCase()
  if (ct.includes('pdf') || name.endsWith('.pdf')) return 'pdf'
  if (
    ct.startsWith('image/') ||
    /\.(jpe?g|png|gif|webp|bmp|heic|heif|tiff?)$/.test(name)
  ) {
    return 'photo'
  }
  return 'office'
}

/** 单个附件 → 源素材：PDF 页数优先用后端 page_count（零下载），缺失才下载整包用 pdf.js 数 */
async function resolveMat(msg: InboxMessageDetail, att: AttachmentMeta): Promise<BundleMat> {
  const n = effectiveFileName(att)
  const k = detectMaterialKind(att.content_type, n)
  const base = { partIndex: att.part_index, n, k }
  if (k !== 'pdf') return { ...base, pages: 1 }
  if (att.page_count && att.page_count > 0) return { ...base, pages: att.page_count }
  try {
    const bytes = await fetchAttachmentBytes(msg.id, att.part_index)
    const doc = await loadPdfDocument(`${msg.id}:${att.part_index}`, bytes)
    return { ...base, pages: doc.numPages }
  } catch {
    return { ...base, pages: 1 }
  }
}

/** 每个附件算出一个源素材，并解析真实页数（并行；此前串行 await，多 PDF 包打开时间线性叠加）。 */
export async function resolveMats(msg: InboxMessageDetail): Promise<BundleMat[]> {
  return Promise.all(msg.attachments.map((att) => resolveMat(msg, att)))
}

/** 附件展示名：优先自定义名，其次原始名（仅本模块使用） */
function effectiveFileName(att: AttachmentMeta): string {
  return att.custom_filename?.trim() || att.original_filename || att.filename
}

/** 每个源素材默认一整段，覆盖其全部页 */
export function initialSegments(mats: BundleMat[]): Segment[] {
  return mats.map((m, mi) => {
    const refs: PageKey[] = []
    for (let p = 1; p <= m.pages; p++) refs.push({ mi, p })
    return { id: nextSegId(), t: '', fn: m.n, refs, manual: false }
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
