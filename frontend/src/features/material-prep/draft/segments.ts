import { SEGMENT_TYPES } from '../constants'
import type { AssignInfo, BundleMat, DraftState, PackStatus, PageKey, PositionedBlock, Segment } from '../types'
import { matLabel, withDefaultNames } from './labels'
import { initialSegments } from './resolve'
import { nextSegId } from './seg-id'

/**
 * 基础段不可变运算：所有函数返回新的 DraftState。
 */

/**
 * 在段 si 内部第 k 个页缝处切开（k 为该段 refs 的切分点，0..refs.length-2）。
 * 把该段拆成两段，各自沿用原段的类型（新段类型清空、名取来源名）。
 */
export function splitSegment(d: DraftState, si: number, k: number): DraftState {
  if (si < 0 || si >= d.segs.length) return d
  const cur = d.segs[si]
  if (!cur || cur.refs.length < 2) return d
  if (k < 0 || k >= cur.refs.length - 1) return d
  const head = cur.refs.slice(0, k + 1)
  const tail = cur.refs.slice(k + 1)
  const tailFirst = tail[0]! // 非空由上方 k < refs.length-1 守卫保证
  const newSeg: Segment = {
    id: nextSegId(),
    t: '',
    fn: matLabel(d.mats, tailFirst.mi),
    refs: tail,
    manual: true,
  }
  // 切开即视为人工整理过的段（与 selection 的 manual: true 口径一致）
  const next = d.segs.map((sg, i) => (i === si ? { ...sg, refs: head, manual: true } : sg))
  next.splice(si + 1, 0, newSeg)
  // 头尾两段若还用着源文件名，按各自起始页改成「源名-P起始页」——否则切几刀就有几份同名
  return withDefaultNames({ ...d, segs: next })
}

/** 段 si 并入上一段（si>0） */
export function mergeSegment(d: DraftState, si: number): DraftState {
  if (si <= 0 || si >= d.segs.length) return d
  const cur = d.segs[si]!
  const next = d.segs.map((sg, i) => {
    if (i === si - 1) return { ...sg, refs: [...sg.refs, ...cur.refs], manual: sg.manual || cur.manual }
    return sg
  })
  next.splice(si, 1)
  // 并回整份时默认名变回源文件名
  return withDefaultNames({ ...d, segs: next })
}

/**
 * 把段 si 移动到 targetSi 的前 / 后（左栏拖拽换位）。只是段序调整，refs 与名字都不动。
 */
export function moveSegment(d: DraftState, si: number, targetSi: number, position: 'before' | 'after'): DraftState {
  if (si < 0 || si >= d.segs.length || targetSi < 0 || targetSi >= d.segs.length || si === targetSi) return d
  const moved = d.segs[si]!
  const rest = d.segs.filter((_, i) => i !== si)
  const anchor = rest.findIndex((sg) => sg === d.segs[targetSi])
  if (anchor < 0) return d
  rest.splice(position === 'before' ? anchor : anchor + 1, 0, moved)
  return { ...d, segs: rest }
}

/** 打上「人工改过某字段」的痕迹；只置位不取消——律师改过就是改过，回退也不抹掉 */
function markManualEdit(seg: Segment, what: 'md' | 'name' | 'type'): Segment {
  return { ...seg, manualEdit: { ...seg.manualEdit, [what]: true, at: new Date().toISOString() } }
}

/** 改段类型；仍用默认名的段名字跟着类型走（「起诉状.pdf」），拆完选个类型就不用再改名 */
export function setSegmentType(d: DraftState, si: number, t: string): DraftState {
  if (si < 0 || si >= d.segs.length || t === d.segs[si]!.t) return d
  const segs = d.segs.map((sg, i) => (i === si ? markManualEdit({ ...sg, t }, 'type') : sg))
  return withDefaultNames({ ...d, segs })
}

/** 改段名；名字恰好是类型词（如「借条.pdf」）时自动归类——改名即归类，一个控件两个信息 */
export function renameSegment(d: DraftState, si: number, fn: string): DraftState {
  if (si < 0 || si >= d.segs.length) return d
  const name = fn.trim()
  if (!name || name === d.segs[si]!.fn) return d
  const base = name.replace(/\.[^.]+$/, '')
  const matched = SEGMENT_TYPES.find((t) => t === base)
  const segs = d.segs.map((sg, i) => (i === si ? markManualEdit({ ...sg, fn: name, t: matched ?? sg.t }, 'name') : sg))
  return withDefaultNames({ ...d, segs })
}

/** 恢复初始分段 */
export function resetSegments(d: DraftState): DraftState {
  return { ...d, segs: initialSegments(d.mats) }
}

export function setPackStatus(d: DraftState, status: PackStatus): DraftState {
  if (d.status === status) return d
  return { ...d, status }
}

export function setPackAssign(d: DraftState, assign: AssignInfo): DraftState {
  return { ...d, assign, status: 'done' }
}

export function appendMatsToDraft(d: DraftState, added: BundleMat[]): DraftState {
  if (!added.length) return d
  const mats = [...d.mats, ...added]
  const segs = [...d.segs]
  added.forEach((m, idx) => {
    const mi = d.mats.length + idx
    const refs: PageKey[] = []
    for (let p = 1; p <= m.pages; p++) refs.push({ mi, p })
    segs.push({ id: nextSegId(), t: '', fn: m.n, refs, manual: false })
  })
  return { ...d, mats, segs }
}

/**
 * 给某个源素材的段回填正文 Markdown（图片 / Office 等单页材料用）。
 *
 * 为什么单独一个函数、而不是复用 applyAutoSplit：图片是**单页**，谈不上「分段」
 * ——它只有一个整段，需要的是「把这一页的文字填进段里」。applyAutoSplit 的
 * 语义是「用后端的页区间建议替换该源的整组分段」，套到图片上会要求
 * covered.size === mat.pages 的完整性校验，语义不符，硬用会把单页材料判成
 * 「覆盖不全」而整份丢弃。
 *
 * 只填 md，不动 pg 区间 / 类型 / 名字：正文是附加信息，段的结构由律师决定。
 * 已经有人工填写过 md 的段不覆盖（与 applyAutoSplit 保护人工结果同一原则）。
 */
export function fillSegmentText(d: DraftState, mi: number, md: string): DraftState {
  const text = md.trim()
  if (!text) return d
  let changed = false
  const segs = d.segs.map((sg) => {
    if (sg.refs.length === 0 || !sg.refs.every((r) => r.mi === mi)) return sg
    if (sg.md) return sg // 已有正文：人工/上次识别的结果不覆盖
    changed = true
    return { ...sg, md: text }
  })
  return changed ? { ...d, segs } : d
}

/**
 * 手改某段的 Markdown 正文。
 *
 * 识别不可能全对：表格拍平、标题层级错、页眉页脚混进正文都是常态。
 * 律师改过之后要能留下来（进草稿、可撤销、随包保存），而不是一刷新就没了。
 *
 * 与 `fillSegmentText` 的分工：那个是**填**（只填空段，保护人工结果），
 * 这个是**改**（人工显式编辑，直接覆盖）。
 */
export function setSegmentMarkdown(d: DraftState, si: number, md: string): DraftState {
  const seg = d.segs[si]
  if (!seg) return d
  // 去掉首尾空白后与现值相同就不产生新对象：避免 Undo 栈里塞满「点开又关掉」的空改动
  const next = md.replace(/\s+$/, '')
  if ((seg.md ?? '') === next) return d
  const segs = d.segs.map((sg, i) => (i === si ? markManualEdit({ ...sg, md: next || undefined }, 'md') : sg))
  return { ...d, segs }
}

/**
 * 删掉某段里的一个定位块（识别出来的框位置画错了）。
 *
 * 只删坐标索引，**不动 Markdown 正文**：框画歪不等于文字读错，两件事分开处理。
 * 律师多半会接着用「标来源」重拖一个框，或者干脆不要这个框。
 *
 * key 的规则必须与 `draft/block-keys.ts` 的 `blockKeyOf` 逐字一致
 * （段 id + 绝对页号 + 同页内序号），否则会删错块。
 */
export function removeSegmentBlock(d: DraftState, si: number, blockKey: string): DraftState {
  const seg = d.segs[si]
  if (!seg?.blocks?.length) return d

  const next = seg.blocks.filter((b, i) => {
    const samePageIdx = seg.blocks!.slice(0, i + 1).filter((x) => x.page === b.page).length - 1
    return `${seg.id}:${b.page}:${samePageIdx}` !== blockKey
  })
  if (next.length === seg.blocks.length) return d

  const segs = d.segs.map((sg, i) => (i === si ? { ...sg, blocks: next.length ? next : undefined } : sg))
  return { ...d, segs }
}

/**
 * 改某一段里**一行**（一个定位块）的文字，并把改动同步进 Markdown 正文。
 *
 * ## 为什么必须同步 md
 *
 * `blocks[].text` 与 `seg.md` 是同一批文字的两种视图：前者带坐标给定位用，
 * 后者是给下游 AI 消费的正文。只改一处会出现「列表里改好了、Markdown 里还是错的」
 * ——那比不改更糟（人以为已经修好了）。
 *
 * ## 怎么定位到 md 里的那一行
 *
 * 用原文做替换：把该块**改前的文字**在 md 中第一次出现的位置替换成新文字。
 * 不用行号——后端拼 md 时做过格式化（表格转 GFM、标题加 #），块文本与 md 的行
 * 不是一一对应的，按行号改必然错位。原文匹配至少能保证"改的就是这段字"。
 *
 * 找不到原文时**只改块、不动 md**：宁可正文保留旧值，也不能乱替换别处的文字。
 */
export function setSegmentBlockText(d: DraftState, si: number, blockKey: string, text: string): DraftState {
  const seg = d.segs[si]
  if (!seg?.blocks?.length) return d

  let hit: PositionedBlock | undefined
  const blocks = seg.blocks.map((b, i) => {
    const samePageIdx = seg.blocks!.slice(0, i + 1).filter((x) => x.page === b.page).length - 1
    if (`${seg.id}:${b.page}:${samePageIdx}` !== blockKey) return b
    hit = b
    return { ...b, text }
  })
  if (!hit) return d

  const oldText = hit.text ?? ''
  let md = seg.md
  if (md && oldText && oldText !== text) {
    const at = md.indexOf(oldText)
    if (at >= 0) md = md.slice(0, at) + text + md.slice(at + oldText.length)
  }

  const segs = d.segs.map((sg, i) => (i === si ? { ...sg, blocks, md } : sg))
  return { ...d, segs }
}
