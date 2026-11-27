/**
 * OCR 的**块级几何**：照片取字的 MIME 判型、块坐标形状、按坐标重建阅读顺序。
 *
 * 从 `auto-split-helpers.ts` 拆出的原因：这一组函数处理的是「引擎返回的矩形 + 文字」
 * 这个数据形状（y 聚行、行内按 x 排、坐标缺失就不猜顺序），与「怎么轮询拆分任务」
 * （`poll-job.ts`）、「分段来源怎么归因」（`segment-backend-note.ts`）没有交集：
 * 它们一条网络请求都不发，也不读任何任务状态，是纯几何/文本变换。
 */

/** 由文件名推图片 MIME（后端只存 content_type，缺失时靠它补齐） */
export function guessImageType(name: string): string {
  const lower = name.toLowerCase()
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.webp')) return 'image/webp'
  if (lower.endsWith('.gif')) return 'image/gif'
  if (lower.endsWith('.bmp')) return 'image/bmp'
  if (lower.endsWith('.tif') || lower.endsWith('.tiff')) return 'image/tiff'
  if (lower.endsWith('.heic') || lower.endsWith('.heif')) return 'image/heic'
  return 'image/jpeg'
}

/** OCR 块的最小形状：坐标可选（只给文字的老调用方仍按返回序拼） */
export interface OcrTextBlock {
  text?: string
  x?: number
  y?: number
  w?: number
  h?: number
}

type RectBlock = OcrTextBlock & { x: number; y: number; w: number; h: number }

function hasRect(b: OcrTextBlock): b is RectBlock {
  return [b.x, b.y, b.w, b.h].every((v) => typeof v === 'number' && Number.isFinite(v))
}

const centerY = (b: RectBlock): number => b.y + b.h / 2

/** y 相近算同一行：阈值取两块平均行高的 0.6（同行抖动远小于它，相邻行间距远大于它） */
function sameLine(line: RectBlock[], b: RectBlock): boolean {
  const avgY = line.reduce((sum, x) => sum + centerY(x), 0) / line.length
  const avgH = line.reduce((sum, x) => sum + x.h, 0) / line.length
  return Math.abs(centerY(b) - avgY) <= ((avgH + b.h) / 2) * 0.6
}

/**
 * OCR 文字块 → 段落文本（按坐标重建阅读顺序）。
 *
 * 引擎返回的块序不保证是阅读序（手机拍照证据尤其乱），直接 join 会把上下行、
 * 左右块交错在一起。这里按 y 聚成行、行内按 x 排：同一行的块用空格连接，
 * 行与行之间换行，保留行结构。
 *
 * 仍不出 Markdown 表格：块是「矩形 + 文字」，没有行列语义，凭空编表格会把
 * 本来就散的手机拍照证据认成一堆假表格。
 *
 * 坐标不全时不猜阅读序，保持返回序。局限：真多栏版面同一 y 上的左右栏会被排成
 * 一行（分栏需要 x 聚类，对单栏拍照证据反而会误切），这里不做。
 */
export function blocksToMarkdown(blocks: OcrTextBlock[] | undefined): string {
  const items = (blocks ?? [])
    .map((b) => ({ ...b, text: (b.text ?? '').trim() }))
    .filter((b) => b.text)
  if (!items.length) return ''
  if (!items.every(hasRect)) return items.map((b) => b.text).join('\n')
  const rects = items as RectBlock[]
  const lines: RectBlock[][] = []
  for (const b of [...rects].sort((a, z) => centerY(a) - centerY(z) || a.x - z.x)) {
    const line = lines[lines.length - 1]
    if (line && sameLine(line, b)) line.push(b)
    else lines.push([b])
  }
  return lines
    .map((line) => line.sort((a, z) => a.x - z.x).map((b) => b.text).join(' '))
    .join('\n')
}
