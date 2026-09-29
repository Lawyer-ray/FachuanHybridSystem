import { toast } from 'sonner'

import { copyCourtSmsDocsToClipboard, courtSmsDocDownloadUrl } from '../../../api'

/** 取单件文书二进制（Safari 等支持浏览器剪贴板写文件时的降级数据源） */
export async function fetchDocBlob(smsId: number, refIndex: number): Promise<Blob> {
  const res = await fetch(courtSmsDocDownloadUrl(smsId, refIndex))
  if (!res.ok) throw new Error(`下载失败 HTTP ${res.status}`)
  return res.blob()
}

/**
 * 构造 PDF 剪贴板条目：标准类型（Safari）优先，旧版 Chromium 只认 `web ` 前缀的
 * 自定义格式；都不支持返回 null。这是后端不可用时的降级路径。
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

/**
 * 复制文书的统一入口，三级降级：
 * 1. 后端 NSPasteboard 直写 file-url（同 Finder ⌘C）——微信等直接 ⌘V 粘出文件，
 *    任意浏览器可用（要求后端与用户同机且为 macOS，本项目本地部署即是）；
 * 2. 浏览器剪贴板写 PDF——仅 Safari（及部分新 Chromium）支持；
 * 3. 复制文件名——至少粘到对话里能对上文件，并如实提示。
 */
async function copyDocs(smsId: number, indexes: number[], names: string[], fallbackVerb: string): Promise<void> {
  // 1) 后端直写系统剪贴板
  try {
    const res = await copyCourtSmsDocsToClipboard(smsId, indexes)
    if (res.success && res.copied > 0) {
      toast.success(`已复制 ${res.copied} 个文件（同 Finder 复制），到微信对话框直接 ⌘V 粘贴发送`)
      return
    }
    // reason=unsupported / 文件缺失等，继续降级；后端不可达则直接走浏览器路径
  } catch {
    // 网络层失败（远程部署后端等），继续降级
  }

  // 2) 浏览器剪贴板（Safari 可写 PDF 文件）
  try {
    const blobs = await Promise.all(indexes.map((i) => fetchDocBlob(smsId, i)))
    if (await copyBlobsToClipboard(blobs)) {
      toast.success(`文件已复制，可直接粘贴到对话框发送（若粘贴无反应请${fallbackVerb}）`)
      return
    }
  } catch {
    // 取文件失败，落到文件名降级
  }

  // 3) 文件名兜底
  if (await copyTextToClipboard(names.join('\n'))) {
    toast.info('当前环境不支持复制文件本体，已复制文件名')
  } else {
    toast.error('复制失败，请改用下载')
  }
}

export async function copyDocFile(smsId: number, refIndex: number, name: string): Promise<void> {
  await copyDocs(smsId, [refIndex], [name], '改用下载')
}

export async function copyAllDocFiles(smsId: number, names: string[]): Promise<void> {
  await copyDocs(smsId, names.map((_, i) => i), names, '改用打包下载')
}
