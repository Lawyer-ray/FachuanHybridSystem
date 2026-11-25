import type { NormRect } from '@/lib/pdf'
import type { PageRotMap, RotDeg } from '../types'

/**
 * 页旋转（人工前置）的纯领域逻辑。
 *
 * ## 为什么旋转要存在草稿里而不是改源文件
 *
 * 律师把倒着扫的卷宗转正，是为了**自己看得懂**（法院件常有 `/Rotate 90`，
 * 而扫描时把纸倒着送进去就会得到 180° 的页）。但「转正」这件事最终必须落到
 * 三个出口上才有意义：归案上传的案件材料、归档进卷宗的文件、下载给客户的 PDF。
 *
 * 三条路都做不到「前端转一下就好」，所以旋转作为**页级覆盖**记在草稿里，
 * 由各个「材料化边界」在生成 PDF 时统一烧入（见 `api/pdf-split.ts` 的
 * `extractPdfPages(..., rotations)` 与后端 `parse_page_rotations`）。
 *
 * 这样做的三个直接好处：
 * 1. **源附件一个字节都不改** —— 改源文件要重写几十 MB、还要让 OCR / 拆分缓存
 *    全部失效（转一下等几十秒），没有人会为了看图这么付代价；
 * 2. **可撤销** —— 「重置」就是删掉键，草稿天然带版本；
 * 3. **与切段解耦** —— 键是 `partIndex:page`，切段/并段/删页都不会让旋转错位
 *    （挂在段上就会：段一改，旋转跟着跑到别的页上）。
 *
 * ## 为什么 key 用 partIndex 而不是 mats 下标
 *
 * `DraftState.mats` 的下标会随「追加附件」漂移（新附件前插/位置变化都会），
 * 而 `partIndex` 是后端附件数组里的稳定标识（`Segment.splitRef` 同口径）。
 *
 * ## 角度语义
 *
 * 值是**叠加在页自身 `/Rotate` 之上的顺时针增量**。pdf.js 的
 * `page.getViewport({ rotation })` 是**覆盖**页自身的 `/Rotate`（默认值就是
 * `page.rotate`，见 `pdf.mjs` 的 `getViewport`），所以渲染时传的是
 * `page.rotate + 增量`，由 `lib/pdf/page-render.ts` 负责相加。
 */

/** 页引用：素材的 partIndex + 页号（1 起） */
export interface PageRefKey {
  partIndex: number
  page: number
}

/** 草稿里页旋转表的键（`partIndex:page`） */
export function pageRotKey(partIndex: number, page: number): string {
  return `${partIndex}:${page}`
}

/** 解析 `partIndex:page`；非法（NaN / 负数 / 缺段）返回 null，调用方按「没旋转」处理 */
export function parsePageRotKey(key: string): PageRefKey | null {
  const [rawPart, rawPage] = key.split(':')
  if (rawPart === undefined || rawPage === undefined) return null
  const partIndex = Number(rawPart)
  const page = Number(rawPage)
  if (!Number.isInteger(partIndex) || partIndex < 0) return null
  if (!Number.isInteger(page) || page < 1) return null
  return { partIndex, page }
}

/**
 * 收敛到 {0,90,180,270}。
 *
 * pdf.js 的 `PageViewport` 对非 90 倍数会直接抛错，所以入口处必须收敛，
 * 不能让 `+15°` 这类值漏进去；负数按逆时针折算（`-90` → `270`）。
 */
export function normalizeDeg(deg: number): RotDeg {
  if (!Number.isFinite(deg)) return 0
  const wrapped = ((Math.round(deg / 90) * 90) % 360 + 360) % 360
  return wrapped === 0 ? 0 : wrapped === 90 ? 90 : wrapped === 180 ? 180 : 270
}

/** 某页当前的增量（缺省 0） */
export function getPageRot(map: PageRotMap | undefined, ref: PageRefKey): RotDeg {
  const raw = map?.[pageRotKey(ref.partIndex, ref.page)]
  return normalizeDeg(Number(raw ?? 0))
}

/** 页旋转后的显示尺寸（90/270 时宽高互换） */
export function rotatedSizeOf(width: number, height: number, deg: RotDeg): { width: number; height: number } {
  return deg === 90 || deg === 270 ? { width: height, height: width } : { width, height }
}

/** 内部：写入一组页的绝对角度，0 就删键（草稿里不留 `{k:0}` 的噪音） */
function writeRefs(map: PageRotMap | undefined, refs: readonly PageRefKey[], deg: RotDeg): PageRotMap {
  const next: PageRotMap = { ...(map ?? {}) }
  for (const ref of refs) {
    const key = pageRotKey(ref.partIndex, ref.page)
    if (deg === 0) delete next[key]
    else next[key] = deg
  }
  return next
}

/**
 * 批量叠加旋转（`delta` 可为 90 / -90 / 180）。
 *
 * 返回值恒为新对象（不可变改草稿，便于 store 的 `update` 与单测直接断言）。
 * 重复点四次 90° 会回到 0 并**删键**——这样「转错了」与「本来就没转」在草稿里
 * 是同一个状态，不会留下 4 个键让「已旋转 N 页」的数不准。
 */
export function rotateRefs(map: PageRotMap | undefined, refs: readonly PageRefKey[], delta: number): PageRotMap {
  const next: PageRotMap = { ...(map ?? {}) }
  for (const ref of refs) {
    const deg = normalizeDeg(getPageRot(map, ref) + delta)
    const key = pageRotKey(ref.partIndex, ref.page)
    if (deg === 0) delete next[key]
    else next[key] = deg
  }
  return next
}

/** 批量设为某个绝对角度（右键菜单的「旋转 180°」用这个，避免与当前角度叠加） */
export function setRefsRotation(
  map: PageRotMap | undefined,
  refs: readonly PageRefKey[],
  deg: number,
): PageRotMap {
  return writeRefs(map, refs, normalizeDeg(deg))
}

/** 批量重置（回正） */
export function resetRefsRotation(map: PageRotMap | undefined, refs: readonly PageRefKey[]): PageRotMap {
  return writeRefs(map, refs, 0)
}

/**
 * 已旋转的页数。给了 `refs` 就只数这些页（工具栏/选择条要按选区计数），
 * 不给就数全包。
 */
export function countRotated(map: PageRotMap | undefined, refs?: readonly PageRefKey[]): number {
  if (!map) return 0
  if (!refs) {
    return Object.keys(map).filter((key) => normalizeDeg(Number(map[key] ?? 0)) !== 0).length
  }
  return refs.reduce((n, ref) => (getPageRot(map, ref) === 0 ? n : n + 1), 0)
}

/**
 * 把**未旋转坐标系**里的归一化矩形，换算到旋转后的坐标系。
 *
 * 为什么必须有这一步：页面上的引擎框（`EngineBoxOverlay`）、OCR 取字框
 * （`ocrPending`/`pickInfo`）都是 0–1 归一化矩形，用百分比叠在页面上。页转了、
 * 框不转，框就会指到隔壁——这比没有框更糟（律师会以为引擎识别错了位置）。
 *
 * 顺时针 90°：点 `(x,y) → (1-y, x)`，于是矩形左上角变成 `(1-y-h, x)`、
 * 宽高互换；270° 是它的逆变换；180° 是中心对称。
 */
export function rotateNormRect(rect: NormRect, deg: RotDeg): NormRect {
  if (deg === 0) return rect
  if (deg === 180) {
    return clampRect({ x: 1 - rect.x - rect.w, y: 1 - rect.y - rect.h, w: rect.w, h: rect.h })
  }
  if (deg === 90) {
    return clampRect({ x: 1 - rect.y - rect.h, y: rect.x, w: rect.h, h: rect.w })
  }
  return clampRect({ x: rect.y, y: 1 - rect.x - rect.w, w: rect.h, h: rect.w })
}

/** 浮点误差会让 `1 - 0.9997 - 0.0003` 变成 1.0000000000000002，夹回 [0,1] */
function clampRect(rect: NormRect): NormRect {
  const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
  const x = clamp01(rect.x)
  const y = clamp01(rect.y)
  return { x, y, w: Math.min(1 - x, clamp01(rect.w)), h: Math.min(1 - y, clamp01(rect.h)) }
}

/**
 * 给后端的一行编码：`页码:角度,页码:角度`（页码是**源 PDF 的绝对页号**，
 * 与 `page_start`/`page_end` 同一坐标系）。
 *
 * 只导出 `[pageStart, pageEnd]` 内非 0 的页，按页码升序：
 * - 只给范围内的页：后端切的是这个区间，区间外的旋转与它无关；
 * - 升序：日志与测试断言可读（对象 key 顺序在 JS 里是插入序，不可依赖）。
 * 无旋转时返回**空串**——后端据此完全跳过旋转路径（老前端不带该字段同理）。
 */
export function rotationsForRange(
  map: PageRotMap | undefined,
  partIndex: number,
  pageStart: number,
  pageEnd: number,
): string {
  if (!map) return ''
  const from = Math.min(pageStart, pageEnd)
  const to = Math.max(pageStart, pageEnd)
  const parts: string[] = []
  for (let page = from; page <= to; page += 1) {
    const deg = getPageRot(map, { partIndex, page })
    if (deg !== 0) parts.push(`${page}:${deg}`)
  }
  return parts.join(',')
}

/** 全包的页引用（「全部重置」用；只列真正有旋转的页，省得遍历几千页） */
export function rotatedRefsOf(map: PageRotMap | undefined): PageRefKey[] {
  if (!map) return []
  return Object.keys(map)
    .map((key) => parsePageRotKey(key))
    .filter((ref): ref is PageRefKey => ref !== null && getPageRot(map, ref) !== 0)
}
