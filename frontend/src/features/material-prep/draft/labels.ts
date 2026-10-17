import type { BundleMat, DraftState, PageKey, Segment } from '../types'

/**
 * 纯展示标签 / 汇总统计：无 DraftState 改写，供左栏、卡片、清单、进度复用。
 */

export function matLabel(mats: BundleMat[], mi: number): string {
  return mats[mi]?.customName || mats[mi]?.n || `材料 ${mi + 1}`
}

export function segMats(sg: Segment): number[] {
  return [...new Set(sg.refs.map((r) => r.mi))]
}

/** 页面唯一键（用于选中集合） */
export const selKeyOf = (r: PageKey): string => `${r.mi}:${r.p}`

export function countUnclassified(d: DraftState): number {
  // 未归类 = 这份还没处理过：没选类型，名字也还是系统默认名——改名即归类
  return d.segs.filter((s) => !s.t && isAutoSegName(d, s)).length
}

/** 段是否覆盖整个单一源文件（用于左栏「整份」行） */
export function isWholeMat(d: DraftState, si: number): boolean {
  const sg = d.segs[si]
  if (!sg || segMats(sg).length !== 1) return false
  const mi = sg.refs[0]!.mi // 非空由上一行 segMats === 1 保证（mats 由 refs 派生）
  const m = d.mats[mi]
  if (!m) return false
  const full = new Set<number>()
  for (let p = 1; p <= m.pages; p++) full.add(p)
  const have = new Set(sg.refs.map((r) => r.p))
  return full.size === have.size && [...have].every((p) => full.has(p))
}

/* ------------------------------------------------------------------ 默认命名 */

const EXT_RE = /\.[^.]+$/

function splitName(label: string): { base: string; ext: string } {
  const m = label.match(EXT_RE)
  return { base: label.replace(EXT_RE, ''), ext: m ? m[0] : '.pdf' }
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 段的默认名，按优先级：
 *   1. 选了类型 → 「类型.pdf」；同类型已有一份时 → 「类型-P起始页.pdf」（拆完选个类型名字就有了，不用再改）
 *   2. 整份 → 源文件名
 *   3. 其它 → 「源名-P起始页.ext」（跨源取首页所在的源）
 *
 * 切开 / 切出 / 合并 / 删页 / 选类型五条路径共用这一条规则。以前只有「切出」的新段
 * 带 -P 后缀，切开留下的尾段和合并留下的余段都直接沿用源文件名——切三刀就有三份
 * 同名材料，左栏看起来像凭空冒出一堆同名文件。
 */
export function defaultSegName(
  d: DraftState,
  refs: PageKey[],
  whole: boolean,
  type = '',
  used?: ReadonlySet<string>,
): string {
  const first = refs[0]
  if (type) {
    const plain = `${type}.pdf`
    return used?.has(plain) ? `${type}-P${first?.p ?? 1}.pdf` : plain
  }
  if (!first) return '材料.pdf'
  const label = matLabel(d.mats, first.mi)
  if (whole) return label
  const { base, ext } = splitName(label)
  return `${base}-P${first.p}${ext}`
}

/**
 * 段的名字是否仍是系统默认名（用户没手改过）。
 *
 * 有 `fnAuto`（系统最近一次分配的默认名）就只看 fn 是否与之相等——这是唯一可靠的
 * 来源记录；用户把名字改成恰好像默认名的字符串（如「借条.pdf」）也不会被误判。
 * 老草稿没有 fnAuto，退回按模式识别：源文件名 / 「源名-P数字.ext」/ 该段**自己类型**的
 * 「类型.pdf」「类型-P数字.pdf」。
 */
export function isAutoSegName(d: DraftState, seg: Pick<Segment, 'fn' | 't' | 'fnAuto'>): boolean {
  // 后端序列化会把缺失字段回成 null，用 != null 同时挡住 undefined 与 null
  if (seg.fnAuto != null) return seg.fn === seg.fnAuto
  const { fn, t } = seg
  if (t && (fn === `${t}.pdf` || new RegExp(`^${escapeRe(t)}-P\\d+\\.pdf$`).test(fn))) return true
  return d.mats.some((_, mi) => {
    const label = matLabel(d.mats, mi)
    if (fn === label) return true
    const { base, ext } = splitName(label)
    if (!fn.startsWith(`${base}-P`) || !fn.endsWith(ext)) return false
    return /^\d+$/.test(fn.slice(base.length + 2, fn.length - ext.length))
  })
}

/**
 * 刷新所有仍用默认名的段：类型变了 / 页区间变了（切开 / 切出 / 合并 / 删页）名字跟着变，
 * 变回整份就变回源文件名；用户改过名的段原样保留，且它们占用的名字不会再分给别人。
 * 刷新时同步写 fnAuto 记录来源。无变化返回原引用。
 */
export function withDefaultNames(d: DraftState): DraftState {
  const used = new Set(d.segs.filter((sg) => !isAutoSegName(d, sg)).map((sg) => sg.fn))
  let changed = false
  const segs = d.segs.map((sg, si) => {
    if (!isAutoSegName(d, sg)) return sg
    const fn = defaultSegName(d, sg.refs, isWholeMat(d, si), sg.t, used)
    used.add(fn)
    if (fn === sg.fn && sg.fnAuto === fn) return sg
    changed = true
    return { ...sg, fn, fnAuto: fn }
  })
  return changed ? { ...d, segs } : d
}

/* ------------------------------------------------------------------ 页区间 */

/** 页区间文案：单源连续「P5–19」、断续「P3, P7–9」、跨源「跨源」。左栏行与段头共用 */
export function segRangeText(sg: Segment): string {
  if (!sg.refs.length) return ''
  if (segMats(sg).length !== 1) return '跨源'
  const runs: string[] = []
  let start: number | undefined
  let end: number | undefined
  const flush = () => {
    if (start === undefined || end === undefined) return
    runs.push(start === end ? `P${start}` : `P${start}–${end}`)
  }
  for (const { p } of sg.refs) {
    if (end !== undefined && p === end + 1) {
      end = p
      continue
    }
    flush()
    start = end = p
  }
  flush()
  return runs.join(', ')
}
