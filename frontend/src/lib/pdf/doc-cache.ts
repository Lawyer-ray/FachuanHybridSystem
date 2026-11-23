import { PDFJS_WASM_URL, pdfjsLib } from './pdfjs'

/**
 * PDF 文档缓存：按 key（`messageId:partIndex`）保存已加载的文档与加载任务。
 *
 * 为什么是 Map 而不是单槽：一个材料包会同时渲染它名下所有 PDF 的页（Flow 给每页都挂一个
 * PageCell，且 React.StrictMode 双跑 effect），loadPdfDocument 会被多个不同 key 并发调用。
 * 旧实现是单槽 + ``cachedTask.destroy()``：加载新 key 时把上一个文档连同 worker 一起干掉，
 * 而 pdf.js 的 MessageHandler.destroy() 只 abort 监听、不 reject 挂起的 sendWithPromise，
 * 于是正在渲染的那页 promise 永远 pending、页卡一直转骨架屏；并发改写 cachedDocKey 也让同一
 * key 的命中判断失效。改为按 key 常驻，关阅读器时再用 clearPdfDocuments() 统一释放。
 */
interface PdfCacheEntry {
  task: pdfjsLib.PDFDocumentLoadingTask
  doc: Promise<pdfjsLib.PDFDocumentProxy>
}
const docCache = new Map<string, PdfCacheEntry>()

/**
 * 加载一份 PDF 文档并按 key 缓存（同一附件只加载一次）。
 * data 由调用方通过带鉴权的请求取回。
 *
 * 注意：pdf.js 会把 getDocument({ data }) 里的 ArrayBuffer **transfer** 给 worker
 * （pdf.mjs: sendWithPromise("GetDocRequest", docParams, [data.buffer])），被 transfer 的
 * buffer 会 detach、byteLength 归零。调用方（material-prep 的 fetchAttachmentBytes）会把同一份
 * buffer 反复拿去渲染/OCR/上传，直接传本体就会把它废掉——所以这里必须传副本，本体留给别人用。
 *
 * 并发同 key 的调用复用缓存的加载 promise，不会重复 getDocument；加载失败则撤掉缓存以便重试。
 */
export function loadPdfDocument(key: string, data: ArrayBuffer): Promise<pdfjsLib.PDFDocumentProxy> {
  const hit = docCache.get(key)
  if (hit) return hit.doc
  // 副本给 pdf.js：它会把副本 transfer 给 worker，data 本体保持可用
  const task = pdfjsLib.getDocument({ data: data.slice(0), wasmUrl: PDFJS_WASM_URL })
  const entry: PdfCacheEntry = { task, doc: task.promise }
  docCache.set(key, entry)
  entry.doc.catch(() => {
    if (docCache.get(key) === entry) docCache.delete(key)
  })
  return entry.doc
}

/** 关闭并清空全部已缓存的 PDF 文档与 worker（退出阅读器时调用，避免跨包累积占内存）。 */
export function clearPdfDocuments(): void {
  for (const [key, entry] of docCache) {
    docCache.delete(key)
    void entry.task.destroy().catch(() => {
      /* noop */
    })
  }
}

/** 全局清理入口（登出时调用）：清空 PDF 文档缓存，语义与 clearPdfDocuments 一致。 */
export function clearPdfCache(): void {
  clearPdfDocuments()
}
