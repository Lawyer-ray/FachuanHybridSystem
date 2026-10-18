/**
 * 快速记一笔的剪贴板粘贴：从 paste 事件里取出可识别的文件。
 *
 * 截图 / 复制图片后 ⌘V，浏览器把图片包成泛名 File（image.png / blob）塞进
 * clipboardData.files。而 recognize 端点按**文件名后缀**校验
 * （后端 SUPPORTED_EXTENSIONS = .pdf/.jpg/.jpeg/.png），泛名直接传会被拒收，
 * 所以这里按 MIME 补全扩展名，并换成带时间戳的名字（后端记录里一堆
 * image.png 分不清是哪次粘贴的）。
 */

/** paste 事件用到的最小切面；普通对象即可构造，node 环境单测不用 jsdom */
export interface ClipboardLike {
  files?: ArrayLike<File> | null
  items?: ArrayLike<{ kind: string; getAsFile(): File | null }> | null
}

/** 已知 MIME → 后端认的扩展名（jpeg 统一落 .jpg） */
const MIME_EXT: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'application/pdf': 'pdf',
}

function extOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : ''
}

/** 浏览器给剪贴板文件的占位名，对用户没有信息量；有真实名字的不动 */
function isGenericName(name: string): boolean {
  const ext = extOf(name)
  const base = ext ? name.slice(0, -(ext.length + 1)) : name
  return !ext || /^(image|blob|pasted graphic)$/i.test(base)
}

/** 粘贴图片-20261018-103005 这类本地时间戳 */
function stamp(now: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}${p(now.getSeconds())}`
}

/** 泛名文件按 MIME 重命名；名字本身有信息量的（如 Finder 复制的 传票.pdf）原样保留 */
export function normalizePastedFile(file: File, now: Date = new Date()): File {
  if (!isGenericName(file.name)) return file
  const ext = MIME_EXT[file.type] ?? file.type.split('/')[1]?.replace(/\+.*$/, '')
  if (!ext) return file
  const label = file.type.startsWith('image/') ? '粘贴图片' : '粘贴文件'
  return new File([file], `${label}-${stamp(now)}.${ext}`, { type: file.type, lastModified: file.lastModified })
}

/**
 * 取剪贴板里的第一个文件，没有（纯文字粘贴）返回 null，调用方放行浏览器默认行为。
 * 优先读 files，个别浏览器只填 items 时兜底 getAsFile。
 */
export function fileFromClipboard(dt: ClipboardLike | null, now: Date = new Date()): File | null {
  const direct = dt?.files?.[0]
  if (direct) return normalizePastedFile(direct, now)
  for (const item of Array.from(dt?.items ?? [])) {
    if (item.kind !== 'file') continue
    const f = item.getAsFile()
    if (f) return normalizePastedFile(f, now)
  }
  return null
}
