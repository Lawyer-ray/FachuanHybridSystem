import { createApiClient, UPLOAD_TIMEOUT_MS } from '@/lib/api'

/* ============ Office（Word / Excel）取字 ============ */

const parsingApi = createApiClient({ prefix: '/api/v1/document-parsing' })

/** /document-parsing/parse 的同步响应（生成物 ParseDocumentResponse 的消费子集） */
type OfficeParseResult = {
  success?: boolean
  text?: string | null
  markdown?: string | null
  parse_method?: string | null
  error?: string | null
}

/**
 * Word / Excel 转 Markdown + 正文。
 *
 * 走后端 `document-parsing` 的 `backend=office`（本地 python-docx / openpyxl），
 * **不是** OnlyOffice：DS 是给人看和改的编辑器画布，抽文本要绕两跳网络 + 容器
 * 内转换，而且它返回的是渲染结果、拿文字还得再 OCR 一遍——Word 里的文字本来
 * 就是结构化的，OCR 反而把可靠的字变成可能认错的东西。详见后端
 * `apps/document_parsing/services/backends/office_backend.py` 头注释。
 */
export async function parseOfficeFile(file: File): Promise<{ markdown: string; text: string }> {
  // 显式补 content type：后端 storage_service 会校验「MIME 与扩展名一致」，
  // 而 File.type 可能是空串（从 ArrayBuffer 重建 File 时很常见），空值时
  // 后端拿到 application/octet-stream 会直接报「文件类型与扩展名不匹配」。
  const type = file.type || officeMimeOf(file.name)
  const fd = new FormData()
  fd.append('file', type ? new File([file], file.name, { type }) : file, file.name)
  fd.append('backend', 'office')
  fd.append('return_markdown', 'true')
  const r = await parsingApi.post('parse', { body: fd, timeout: UPLOAD_TIMEOUT_MS }).json<OfficeParseResult>()
  if (r.success === false) throw new Error(r.error || 'Office 文档解析失败')
  return { markdown: (r.markdown ?? '').trim(), text: (r.text ?? '').trim() }
}

/** Office 扩展名 → MIME（后端按 MIME 校验，必须与 mimetypes 标准值一致） */
function officeMimeOf(name: string): string {
  const lower = name.toLowerCase()
  if (lower.endsWith('.docx')) return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  if (lower.endsWith('.doc')) return 'application/msword'
  if (lower.endsWith('.xlsx')) return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if (lower.endsWith('.xls')) return 'application/vnd.ms-excel'
  return ''
}
