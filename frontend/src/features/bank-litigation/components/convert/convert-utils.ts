// ───────────────────────── 小工具 ─────────────────────────
// 文书类型列表那个 hook 已挪到 `use-type-list.ts`（hook 按文件名可发现），
// 本文件只留与 React 无关的纯函数。

/** 触发浏览器下载。文件名后端已按 content-disposition 给过，这里用调用方拼的名。 */
export function saveBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // 立刻 revoke 会让 Safari 偶发下载空文件
  setTimeout(() => URL.revokeObjectURL(href), 4000)
}

export function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
