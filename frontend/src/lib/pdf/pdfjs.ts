import * as pdfjsLib from 'pdfjs-dist'
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjsLib.GlobalWorkerOptions.workerSrc = PdfWorker

/**
 * pdf.js 6.x 的 JBIG2/CCITT G4（扫描件文字蒙版）与 JPEG2000 解码器是 WASM 实现，
 * 必须通过 wasmUrl 告知 wasm 文件目录（public/pdfjs/，构建时原样拷贝）。
 * 缺失时 pdf.js 默认 ignoreErrors=true 会**静默跳过**这些图像——典型症状：
 * 佳能扫描仪产的「JPEG 背景 + CCITT 文字蒙版」双图层 PDF 只剩淡影背景和印章，
 * 正文文字整层不渲染（PyMuPDF/浏览器原生查看器均正常，仅 pdf.js 不画）。
 */
export const PDFJS_WASM_URL = `${import.meta.env.BASE_URL}pdfjs/`

export { pdfjsLib }
