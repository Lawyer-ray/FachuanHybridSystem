/**
 * 文件下载工具
 */

/**
 * 通过创建临时链接下载 Blob
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * 从 Response 中提取文件名并下载
 */
export async function downloadFromResponse(response: Response, fallbackFilename = 'download'): Promise<void> {
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition')
  let filename = fallbackFilename
  if (disposition) {
    const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i)
    if (utf8Match) filename = decodeURIComponent(utf8Match[1])
    else {
      const plainMatch = disposition.match(/filename="?([^";\n]+)"?/)
      if (plainMatch) filename = plainMatch[1]
    }
  }
  downloadBlob(blob, filename)
}
