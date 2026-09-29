import { toast } from 'sonner'

import { courtSmsDocDownloadUrl } from '../../../api'

/** 取单件文书二进制（带 token 的下载直链，same-origin 由 Vite proxy / 同源部署承担） */
export async function fetchDocBlob(smsId: number, refIndex: number): Promise<Blob> {
  const res = await fetch(courtSmsDocDownloadUrl(smsId, refIndex))
  if (!res.ok) throw new Error(`下载失败 HTTP ${res.status}`)
  return res.blob()
}

/**
 * 构造 PDF 剪贴板条目：标准类型（Safari / 新版 Chromium）优先，
 * 旧版 Chromium 只认 `web ` 前缀的自定义格式；都不支持返回 null。
 * 注意：即便写入成功，目标应用（如微信）是否识别剪贴板里的 PDF 由对方决定，
 * 识别不了时用户应改用「下载」——调用方的 toast 要把这个边界讲清楚。
 */
function makePdfClipboardItem(blob: Blob): ClipboardItem | null {
  for (const type of ['application/pdf', 'web application/pdf']) {
    try {
      return new ClipboardItem({ [type]: blob })
    } catch {
      // 该类型此浏览器不支持，试下一个
    }
  }
  return null
}

/** 把若干文件写入剪贴板；任一环节不支持 / 被拒绝返回 false，由调用方降级 */
export async function copyBlobsToClipboard(blobs: Blob[]): Promise<boolean> {
  if (typeof ClipboardItem === 'undefined' || !navigator.clipboard?.write) return false
  const items = blobs
    .map(makePdfClipboardItem)
    .filter((item): item is ClipboardItem => item !== null)
  if (items.length === 0) return false
  try {
    await navigator.clipboard.write(items)
    return true
  } catch {
    return false
  }
}

export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/** 复制单件文书：优先复制文件（微信等可直接粘贴发送），不支持则降级复制文件名并如实提示。 */
export async function copyDocFile(smsId: number, refIndex: number, name: string): Promise<void> {
  try {
    const blob = await fetchDocBlob(smsId, refIndex)
    if (await copyBlobsToClipboard([blob])) {
      toast.success('文件已复制，可直接粘贴到对话框发送（若粘贴无反应请改用下载）')
      return
    }
    if (await copyTextToClipboard(name)) toast.info('当前浏览器不支持复制文件，已复制文件名')
    else toast.error('浏览器拒绝了剪贴板，请改用下载')
  } catch {
    toast.error('复制失败，请改用下载')
  }
}

/** 复制全部文书到剪贴板（一次 write 多个条目）；不支持时降级为复制全部文件名清单。 */
export async function copyAllDocFiles(smsId: number, names: string[]): Promise<void> {
  try {
    const blobs = await Promise.all(names.map((_, i) => fetchDocBlob(smsId, i)))
    if (await copyBlobsToClipboard(blobs)) {
      toast.success(`已复制 ${blobs.length} 个文件，可直接粘贴到对话框发送（若粘贴无反应请改用打包下载）`)
      return
    }
    if (await copyTextToClipboard(names.join('\n'))) toast.info('当前浏览器不支持复制文件，已复制全部文件名')
    else toast.error('浏览器拒绝了剪贴板，请改用打包下载')
  } catch {
    toast.error('复制失败，请改用打包下载')
  }
}
