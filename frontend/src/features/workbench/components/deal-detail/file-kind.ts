/**
 * 文件名 → 类型分类（纯函数，与展示组件分开：同文件导出非组件会被
 * react-refresh 拦下，热更新会失效）。
 *
 * 分类口径跟着「怎么渲染」走：pdf / word / sheet / image 各有一套颜色标识，
 * 其余归 other（仍需可点、可下载，只是不给专属色）。
 */
export type FileKind = 'pdf' | 'word' | 'sheet' | 'image' | 'other'

export function kindOf(name: string): FileKind {
  const ext = (name.match(/\.([^.]+)$/)?.[1] || '').toLowerCase()
  if (ext === 'pdf') return 'pdf'
  if (['doc', 'docx', 'dotx', 'wps', 'rtf', 'odt'].includes(ext)) return 'word'
  if (['xls', 'xlsx', 'xlsm', 'csv', 'et'].includes(ext)) return 'sheet'
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tif', 'tiff'].includes(ext)) return 'image'
  return 'other'
}
