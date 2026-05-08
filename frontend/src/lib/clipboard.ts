import { toast } from 'sonner'

/**
 * 复制文本到剪贴板，显示 toast 提示
 */
export async function copyToClipboard(text: string, message = '已复制'): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(message)
  } catch {
    toast.error('复制失败')
  }
}
