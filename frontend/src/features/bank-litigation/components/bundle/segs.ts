import type { PdfSplitSegment } from '../../api'

/**
 * 判断一份材料属于我方还是对方。
 *
 * 依据依次为：文件名里的当事人标识 → 材料类型。
 * 这条规则故意保守：拿不准就算我方（立案材料绝大多数是我方提交的），
 * 因为 side 只是分类标签，判错不会拦住流程，但**留空会**（后端硬校验）。
 */
export function guessSide(seg: PdfSplitSegment): 'our' | 'opponent' {
  const n = `${seg.filename} ${seg.segment_label ?? ''}`
  // 对方当事人的材料：被告/被上诉人/被申请人 的身份证、答辩状、上诉状
  if (/(被告|被上诉人|被申请人|对方)[^/]*(身份证|身份证明|答辩|上诉状)/.test(n)) return 'opponent'
  if (/^(被告|被上诉人|被申请人).*\.pdf$/i.test(seg.filename)) return 'opponent'
  return 'our'
}

// ───────────────────────── zip 解包 ─────────────────────────

/**
 * 把下载到的 zip 解成 File[]。
 *
 * 为什么自己解而不是让后端逐个给：
 * 整包一次下完少 10 次往返；而且后端 export 产物本来就是一个 zip。
 * 用浏览器内置 DecompressionStream + 手写中央目录解析太重，
 * 这里用最小可用的 zip 解析：只支持 store/deflate，足够（后端就是这个）。
 */
export async function unzipToFiles(zip: Blob): Promise<File[]> {
  const buf = new Uint8Array(await zip.arrayBuffer())
  const entries = parseZipEntries(buf)
  const out: File[] = []
  for (const e of entries) {
    if (e.name.endsWith('/')) continue
    const data = await inflateEntry(buf, e)
    if (!data) continue
    // ZIP 里的中文名是 UTF-8（后端用 filename flag 0x800），这里已解好
    const name = e.name.split('/').pop() || e.name
    // Uint8Array<ArrayBufferLike> 在 TS 6 下不能直接当 BlobPart（SharedArrayBuffer 分支不兼容）。
    // 拷一份落到独立的 ArrayBuffer，既消掉类型错误，也避免 File 持有一整个 buffer 的视图。
    const bytes = new Uint8Array(data.length)
    bytes.set(data)
    out.push(new File([bytes.buffer], name, { type: 'application/pdf' }))
  }
  return out
}

interface ZipEntry {
  name: string
  method: number
  compressedSize: number
  uncompressedSize: number
  localHeaderOffset: number
}

/** 解析中央目录（zip 尾部 EOCD → 中央目录 → 每个条目） */
function parseZipEntries(buf: Uint8Array): ZipEntry[] {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  // 找 EOCD（0x06054b50），从尾部往前扫
  let eocd = -1
  for (let i = buf.length - 22; i >= 0 && i > buf.length - 65558; i--) {
    if (dv.getUint32(i, true) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) return []
  const count = dv.getUint16(eocd + 10, true)
  let off = dv.getUint32(eocd + 16, true)
  const entries: ZipEntry[] = []
  const dec = new TextDecoder('utf-8')

  for (let i = 0; i < count; i++) {
    if (dv.getUint32(off, true) !== 0x02014b50) break
    const method = dv.getUint16(off + 10, true)
    const compressedSize = dv.getUint32(off + 20, true)
    const uncompressedSize = dv.getUint32(off + 24, true)
    const nameLen = dv.getUint16(off + 28, true)
    const extraLen = dv.getUint16(off + 30, true)
    const commentLen = dv.getUint16(off + 32, true)
    const localHeaderOffset = dv.getUint32(off + 42, true)
    const name = dec.decode(buf.subarray(off + 46, off + 46 + nameLen))
    entries.push({ name, method, compressedSize, uncompressedSize, localHeaderOffset })
    off += 46 + nameLen + extraLen + commentLen
  }
  return entries
}

/** 解压单个条目（store 直接切；deflate 走 DecompressionStream） */
async function inflateEntry(buf: Uint8Array, e: ZipEntry): Promise<Uint8Array | null> {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  const off = e.localHeaderOffset
  if (dv.getUint32(off, true) !== 0x04034b50) return null
  const nameLen = dv.getUint16(off + 26, true)
  const extraLen = dv.getUint16(off + 28, true)
  const start = off + 30 + nameLen + extraLen
  const raw = buf.subarray(start, start + e.compressedSize)
  if (e.method === 0) return raw // store
  if (e.method !== 8) return null // 只支持 deflate

  try {
    const ds = new DecompressionStream('deflate-raw')
    const bytes = new Uint8Array(raw.length)
    bytes.set(raw)
    const stream = new Blob([bytes.buffer]).stream().pipeThrough(ds)
    const out = new Uint8Array(await new Response(stream).arrayBuffer())
    return out
  } catch {
    return null
  }
}
