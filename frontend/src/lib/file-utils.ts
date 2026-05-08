/**
 * 文件工具函数
 */

/** 5MB */
export const MAX_FILE_SIZE_5MB = 5 * 1024 * 1024

/** 10MB */
export const MAX_FILE_SIZE_10MB = 10 * 1024 * 1024

/**
 * 判断是否为 PDF 文件
 */
export function isPdf(file: File): boolean {
  return file.type === 'application/pdf'
}

/**
 * 格式化文件大小
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
