import { inboxApi } from './inbox-packs'

/**
 * 附件字节缓存（按 messageId:partIndex）。
 *
 * 独立成模块的原因：它是 api 层里唯一持有**进程内可变状态**的部分，与
 * 「一个函数打一个端点」的纯对接代码不是同一件事——放在子模块里，拆文件时
 * 谁也不会顺手把它连带改成两份缓存（两份缓存 = 同一份附件下两次、内存翻倍）。
 */

const bytesCache = new Map<string, Promise<ArrayBuffer>>()

/**
 * 字节缓存的总量上限（字节）。
 *
 * 为什么要设限：这个 Map 以前是**无限增长**的——每打开一份附件就把整份字节
 * 永远留住。单文件上限提到 1GB 后，一个「扫描件 + 电子版 + 几张照片」的常规
 * 材料包很容易把浏览器内存顶爆（标签页直接崩，且崩得毫无迹象）。
 *
 * 取下限而非按文件：多份小图片仍能全部命中缓存（便宜），大卷宗超出预算就
 * 不缓存（重取一次比爆内存好），已缓存的老条目按插入顺序（Map 保序 = 近似
 * LRU 的 FIFO）剃掉。
 *
 * 预算用「条目数 + 估算字节」双限：Promise 未 resolve 时量不到真实长度，
 * 此时先只数条目；resolve 后再按实际长度计入总量。
 */
const BYTES_CACHE_BUDGET = 256 * 1024 * 1024
/** 单份超过这个体积就不进缓存：留着它会把整份预算吃满，而它本身复用率不高 */
const BYTES_CACHE_ENTRY_MAX = 64 * 1024 * 1024
const bytesCacheSizes = new Map<string, number>()

function evictBytesCache(): void {
  let total = 0
  for (const size of bytesCacheSizes.values()) total += size
  // Map 保序：最先插入的就是最久没被读过的（命中不重新插入，故为 FIFO）
  for (const key of bytesCacheSizes.keys()) {
    if (total <= BYTES_CACHE_BUDGET && bytesCache.size <= 16) break
    total -= bytesCacheSizes.get(key) ?? 0
    bytesCacheSizes.delete(key)
    bytesCache.delete(key)
  }
}

/**
 * 取附件字节（带鉴权），按 messageId:partIndex 缓存。供 PDF.js 渲染、OCR 取字、云端识别上传。
 *
 * 返回的是缓存的 buffer 本体（调用方会反复复用：每页渲染、OCR、识别上传各取一次）。
 * 若某个调用方会把 buffer **transfer** 给 worker 导致它被 detach（PDF.js 的
 * getDocument({ data }) 就是），请在该调用方内部先拷贝再传——不要在这里拷，
 * 否则 92 页的材料会凭空多拷 92 次。详见 lib/pdf.ts 的 loadPdfDocument。
 */
export function fetchAttachmentBytes(messageId: number, partIndex: number): Promise<ArrayBuffer> {
  const key = `${messageId}:${partIndex}`
  const hit = bytesCache.get(key)
  if (hit) return hit
  const p = inboxApi
    .get(`messages/${messageId}/attachments/${partIndex}/preview`)
    .then((res) => res.arrayBuffer())
    .then((buffer) => {
      // 超大附件不进缓存：留着它会把整份预算吃满，而它本身复用率不高
      if (buffer.byteLength > BYTES_CACHE_ENTRY_MAX) {
        bytesCache.delete(key)
        return buffer
      }
      bytesCacheSizes.set(key, buffer.byteLength)
      evictBytesCache()
      return buffer
    })
    .catch((e) => {
      bytesCache.delete(key)
      bytesCacheSizes.delete(key)
      throw e
    })
  bytesCache.set(key, p)
  evictBytesCache()
  return p
}

export function clearBytesCache(): void {
  bytesCache.clear()
  bytesCacheSizes.clear()
}
