/**
 * PDF 渲染与文档缓存的公开出口（barrel）。
 *
 * 实现按关注点拆在 `lib/pdf/` 下——原先 239 行里塞了四件互不相干的事，改一处
 * 要看整份文件。分层：
 *
 * - `lib/pdf/pdfjs.ts`        pdf.js worker/wasm 的进程级初始化（必须先于一切取文档）
 * - `lib/pdf/render-size.ts`  位图宽度策略（PDF_RENDER_* + pdfRenderWidthFor）
 * - `lib/pdf/retained-img.ts` 驻留 <img> 的 ObjectURL 登记与回收
 * - `lib/pdf/doc-cache.ts`    按 key 常驻的 PDFDocumentProxy 缓存
 * - `lib/pdf/page-render.ts`  页渲染、区域裁剪、canvas 编码
 *
 * 这里只做 re-export，消费方一律仍从 `@/lib/pdf` 取（含登出清理的
 * `import('@/lib/pdf')`），不深引子文件——worker 初始化也就不会被绕过。
 */
export { pdfjsLib } from './pdf/pdfjs'
export {
  PDF_RENDER_DPR_CAP,
  PDF_RENDER_MAX_WIDTH,
  PDF_RENDER_MIN_RATIO,
  PDF_RENDER_WIDTH,
  pdfRenderWidthFor,
} from './pdf/render-size'
export { canvasToRetainedImg, releaseRetainedImg } from './pdf/retained-img'
export { clearPdfCache, clearPdfDocuments, loadPdfDocument } from './pdf/doc-cache'
export { canvasToBlob, imageRegionBlob, renderPdfPage, renderPdfPageRegion } from './pdf/page-render'
export type { NormRect } from './pdf/page-render'
