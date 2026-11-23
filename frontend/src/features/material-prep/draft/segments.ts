
import type { AssignInfo, BundleMat, DraftState, PackStatus, PageKey, PositionedBlock, Segment } from '../types'
import { matLabel, withDefaultNames } from './labels'
import { blocksForPages, blockTextIndexOf, concatBlocks, joinMdByPages, joinWholeMd, shiftPageSpans } from './md-pages'
import { initialSegments } from './initial'
import { nextSegId } from './seg-id'

/**
 * 基础段不可变运算：所有函数返回新的 DraftState。
 */

/** 切/并段搬动正文即人工整理结果：源段有正文就打 md 痕迹，重跑不得静默覆盖 */
export function markMdMoved(seg: Segment, hadMd: boolean): Segment {
  return hadMd ? markManualEdit(seg, 'md') : seg
}

/**
 * 在段 si 内部第 k 个页缝处切开（k 为该段 refs 的切分点，0..refs.length-2）。
 * 把该段拆成两段，各自沿用原段的类型（新段类型清空、名取来源名）。
 *
 * 正文与定位块按页归属跟着走：头段留注入标题（它沿用原段身份），尾段不带旧段名。
 * 页锚点缺失时保守兜底——整段正文留给头段，尾段宁可缺正文也不拿别页的字。
 */
export function splitSegment(d: DraftState, si: number, k: number): DraftState {
  if (si < 0 || si >= d.segs.length) return d
  const cur = d.segs[si]
  if (!cur || cur.refs.length < 2) return d
  if (k < 0 || k >= cur.refs.length - 1) return d
  const head = cur.refs.slice(0, k + 1)
  const tail = cur.refs.slice(k + 1)
  const tailFirst = tail[0]! // 非空由上方 k < refs.length-1 守卫保证
  const headSlice = joinMdByPages([{ seg: cur, pages: head }], true)
  const tailSlice = joinMdByPages([{ seg: cur, pages: tail }])
  const newSeg: Segment = {
    id: nextSegId(),
    t: '',
    fn: matLabel(d.mats, tailFirst.mi),
    refs: tail,
    manual: true,
    md: tailSlice?.md || undefined,
    pageSpans: tailSlice?.pageSpans.length ? tailSlice.pageSpans : undefined,
    blocks: blocksForPages(cur.blocks, tail),
  }
  const headNext: Segment = {
    ...cur,
    refs: head,
    manual: true,
    md: headSlice ? headSlice.md || undefined : cur.md,
    pageSpans: headSlice ? (headSlice.pageSpans.length ? headSlice.pageSpans : undefined) : cur.pageSpans,
    blocks: blocksForPages(cur.blocks, head),
  }
  const hadMd = Boolean(cur.md)
  // 切开即视为人工整理过的段（与 selection 的 manual: true 口径一致）
  const next = d.segs.map((sg, i) => (i === si ? markMdMoved(headNext, hadMd) : sg))
  next.splice(si + 1, 0, markMdMoved(newSeg, hadMd))
  // 头尾两段若还用着源文件名，按各自起始页改成「源名-P起始页」——否则切几刀就有几份同名
  return withDefaultNames({ ...d, segs: next })
}

/** 段 si 并入上一段（si>0）：正文按页序拼接、定位块合并，被并段的正文不再丢弃 */
export function mergeSegment(d: DraftState, si: number): DraftState {
  if (si <= 0 || si >= d.segs.length) return d
  const cur = d.segs[si]!
  const prev = d.segs[si - 1]!
  const slice = joinMdByPages([
    { seg: prev, pages: prev.refs },
    { seg: cur, pages: cur.refs },
  ], true)
  const merged: Segment = {
    ...prev,
    refs: [...prev.refs, ...cur.refs],
    manual: prev.manual || cur.manual,
    md: slice ? slice.md || undefined : joinWholeMd([prev, cur]),
    pageSpans: slice?.pageSpans.length ? slice.pageSpans : undefined,
    blocks: concatBlocks(prev.blocks, cur.blocks),
  }
  const next = d.segs.map((sg, i) => (i === si - 1 ? markMdMoved(merged, Boolean(prev.md || cur.md)) : sg))
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
export function markManualEdit(seg: Segment, what: 'md' | 'name'): Segment {
  return { ...seg, manualEdit: { ...seg.manualEdit, [what]: true, at: new Date().toISOString() } }
}

/**
 * 改段名——这是**唯一**的归类入口。
 *
 * 原先还有一个 `setSegmentType`（右键选类型）跟它并列。已移除：类型词表有 24 个
 * 固定选项，而律师真正需要表达的只是「这份材料叫什么」，改名天然能覆盖。
 * 两个入口还会让「已归类」的判定分裂成两条（`t` 与 `fnAuto`），
 * 现在统一看 `fnAuto`：名字与系统默认名不同 = 律师亲自命名过。
 */
export function renameSegment(d: DraftState, si: number, fn: string): DraftState {
  if (si < 0 || si >= d.segs.length) return d
  const name = fn.trim()
  if (!name || name === d.segs[si]!.fn) return d
  const segs = d.segs.map((sg, i) => (i === si ? markManualEdit({ ...sg, fn: name }, 'name') : sg))
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
  // 整段改写后旧页锚点偏移必然失效（不清掉，后续块编辑会按错区间定位）；
  // 律师已给出权威正文，「块改动没同步」的痕迹一并清除
  const edited = markManualEdit({ ...seg, md: next || undefined, pageSpans: undefined, mdDrift: undefined }, 'md')
  const segs = d.segs.map((sg, i) => (i === si ? edited : sg))
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
 * ## 怎么定位到 md 里的那一处
 *
 * 按**页锚点 + 同页同文序号**精确匹配（`md-pages.blockTextIndexOf`）：先圈到该页
 * 正文区间，再取第 n 次出现。不用全段首次匹配——印章核验语这类重复行会改到别页去；
 * 也不用行号——后端拼 md 时做过格式化（表格转 GFM、标题加 #），行号必然错位。
 *
 * ## 锚不到时不静默漂移
 *
 * 只改块、md 留旧值，但打上 `mdDrift`：右栏据此提示律师「这处没同步进正文，
 * 请整段核对」。同时照样打 manualEdit.md 痕迹——律师逐块核过的内容不能被重跑抹掉。
 */
export function setSegmentBlockText(d: DraftState, si: number, blockKey: string, text: string): DraftState {
  const seg = d.segs[si]
  if (!seg?.blocks?.length) return d

  let hit: PositionedBlock | undefined
  let hitIndex = -1
  const blocks = seg.blocks.map((b, i) => {
    const samePageIdx = seg.blocks!.slice(0, i + 1).filter((x) => x.page === b.page).length - 1
    if (`${seg.id}:${b.page}:${samePageIdx}` !== blockKey) return b
    hit = b
    hitIndex = i
    return { ...b, text }
  })
  if (!hit) return d
  const oldText = hit.text ?? ''
  if (oldText === text) return d

  let md = seg.md
  let pageSpans = seg.pageSpans
  let mdDrift = seg.mdDrift
  if (md && oldText) {
    const at = blockTextIndexOf(seg, hitIndex, oldText)
    if (at >= 0) {
      md = md.slice(0, at) + text + md.slice(at + oldText.length)
      // 正文长度变了，页锚点跟着平移，否则下一次块编辑会按旧偏移圈错区间
      if (pageSpans) pageSpans = shiftPageSpans(pageSpans, at, oldText.length, text.length)
    } else {
      mdDrift = true
    }
  }

  const next = { ...seg, blocks, md, pageSpans, mdDrift }
  // 正文变了、或这次没同步进去（律师的核对成果仍在块上）都要打痕迹；无正文的段没什么可保护
  const touchedMd = Boolean(seg.md) && (md !== seg.md || mdDrift === true)
  const segs = d.segs.map((sg, i) => (i === si ? (touchedMd ? markManualEdit(next, 'md') : next) : sg))
  return { ...d, segs }
}
