import { toast } from 'sonner'

import type { ParseOutcome } from '../../api'

/**
 * 解析结果的展示与导出小工具：DocParseCard 的结果弹窗与历史记录详情弹窗共用。
 * （从 DocParseCard 提取；下载是前端本地合成 Blob——后端 parse 只返回内容。）
 */

/** 结果内容与格式（本地引擎不出 Markdown，按真实内容报格式） */
export function outcomeText(o: Pick<ParseOutcome, 'markdown' | 'text'> | null): { text: string; isMd: boolean } {
  const text = o?.markdown || o?.text || ''
  return { text, isMd: !!o?.markdown }
}

/** 下载解析产物：前端本地合成 Blob */
export function downloadOutcome(o: Pick<ParseOutcome, 'markdown' | 'text'> | null, baseName: string) {
  const { text, isMd } = outcomeText(o)
  if (!text) {
    toast.info('没有可下载的解析内容')
    return
  }
  const mime = isMd ? 'text/markdown;charset=utf-8' : 'text/plain;charset=utf-8'
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = `${baseName}.${isMd ? 'md' : 'txt'}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export async function copyOutcome(o: Pick<ParseOutcome, 'markdown' | 'text'> | null) {
  const { text } = outcomeText(o)
  if (!text) {
    toast.info('没有可复制的解析内容')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    toast.success('已复制解析结果')
  } catch {
    toast.error('浏览器拒绝了剪贴板，可在预览区手动选中复制')
  }
}
