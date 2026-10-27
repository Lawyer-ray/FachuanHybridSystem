/**
 * 附件拖拽/选择的前端预检（与服务端白名单/限额同口径，提前拦住少跑一趟）。
 */

import { formatBytes } from '@/lib/format'

export const ATTACHMENT_EXTENSIONS = ['.pdf', '.docx', '.doc', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.txt']
export const ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024

/** 校验单个文件；不合规返回中文原因，合规返回 null */
export function validateAttachmentFile(file: { name: string; size: number }): string | null {
  const lower = file.name.toLowerCase()
  if (!ATTACHMENT_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return `不支持的格式（仅 ${ATTACHMENT_EXTENSIONS.join(' / ')}）`
  }
  if (file.size > ATTACHMENT_MAX_BYTES) {
    return `超过 20MB 限额`
  }
  if (file.size <= 0) {
    return '文件为空'
  }
  return null
}

/**
 * 人类可读的文件大小（chips 展示用）——复用 `@/lib/format` 的 `formatBytes`。
 *
 * 收敛前这里是第 5 份手写实现（只有 B/KB/MB 三档，KB 档固定取整）。
 * 与 `formatBytes` 的实测差异只在两处，且都是修正旧实现的读不成数：
 * - 1MB 前一档旧实现显示「1024KB」，`formatBytes` 升档成「1.0MB」；
 * - 旧实现没有 GB 档，大文件显示成「1536.0MB」，`formatBytes` 显示「1.5GB」。
 * 0 字节与 B/KB/MB 三档结果完全一致，故直接薄包装，不再留第二份口径。
 */
export function formatFileSize(bytes: number): string {
  return formatBytes(bytes)
}

/** 批量分拣：合规附件与拒绝原因（「文件名」+原因） */
export function splitAttachmentFiles(
  files: File[],
): { accepted: File[]; rejected: string[] } {
  const accepted: File[] = []
  const rejected: string[] = []
  for (const file of files) {
    const reason = validateAttachmentFile(file)
    if (reason) rejected.push(`「${file.name}」${reason}`)
    else accepted.push(file)
  }
  return { accepted, rejected }
}
