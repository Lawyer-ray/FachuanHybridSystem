import type { ParseBackend } from '../../api'

/**
 * 各解析后端支持的文件格式（与后端 backends/*.py 的 get_supported_formats 对齐）。
 *
 * 用于两件事：
 *   1. `<input accept>` 只列出所选后端的格式，别让用户选到必然失败的文件；
 *   2. 提交前拦住明确不支持的扩展名，省掉一次注定失败的往返。
 *
 * 后端没有提供「列出支持的格式」的 API，所以这里按后端源码抄一份。
 * 后端改动格式列表时同步改这里（后端 app 有单测守着，改漏了会亮）。
 */
export const BACKEND_FORMATS: Record<ParseBackend, string[]> = {
  // auto 由后端挑平台（mineru / textin），取二者并集，别误伤
  auto: ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'webp', 'ofd', 'rtf', 'html', 'csv', 'txt'],
  mineru: ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'],
  textin: ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'webp', 'ofd', 'rtf', 'html', 'csv', 'txt'],
  local: ['pdf', 'jpg', 'jpeg', 'png', 'bmp', 'tiff'],
}

/** 卡片上展示给用户的一行格式说明（auto 说全，具体后端报自己的集合） */
export const FORMAT_HINT: Record<ParseBackend, string> = {
  auto: 'PDF / Word / PPT / Excel / 图片 / OFD / RTF / HTML / CSV / TXT',
  mineru: 'PDF / Word / PPT / Excel / JPG / PNG',
  textin: 'PDF / Word / PPT / Excel / 图片 / OFD / RTF / HTML / CSV / TXT',
  local: 'PDF / JPG / PNG / BMP / TIFF（本地无网络依赖）',
}

/** 取文件名扩展名（小写，不含点）；无扩展名返回空串 */
export function extOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : ''
}

/** accept 字符串，供 <input type="file"> 用 */
export function acceptOf(backend: ParseBackend): string {
  return BACKEND_FORMATS[backend].map((e) => `.${e}`).join(',')
}

/**
 * 校验所选后端是否支持该文件。返回 null 表示放行，否则是给用户看的原因。
 */
export function rejectReason(name: string, backend: ParseBackend): string | null {
  const ext = extOf(name)
  if (!ext) return '文件没有扩展名，判断不出格式'
  if (!BACKEND_FORMATS[backend].includes(ext)) {
    return `「${backend === 'local' ? '本地后端' : backend}」不支持 .${ext} 格式——可换 TextinParse，或另选文件`
  }
  return null
}

/** 单文件大小上限（与后端 DATA_UPLOAD_MAX_MEMORY_SIZE 默认 100MB 对齐） */
export const MAX_PARSE_FILE_BYTES = 100 * 1024 * 1024

/** 超限返回提示，未超限返回 null */
export function sizeReason(bytes: number): string | null {
  return bytes > MAX_PARSE_FILE_BYTES ? '文件超过 100MB，请压缩或拆分后再试' : null
}
