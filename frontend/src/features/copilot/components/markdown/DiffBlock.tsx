/**
 * 修订块：AI 改写了某份文书里的哪一句。
 *
 * **为什么要有它**：`rewrite_folder_file` 落盘成功后，界面只留下一条
 * 「已完成 · rewrite_folder_file」和一段被截到 2000 字的 JSON。律师看不到
 * 「改了哪一句」，只能自己去文件夹里翻原文对比——而这正是他最不敢放过的
 * 一步（AI 悄悄改掉一个「不超过」为「不低于」，后果是另一回事）。
 *
 * **数据从哪来**：同一次调用的 `tool_call.arguments` 里带 `original` /
 * `replacement` 全文，**只有这里完整**（`tool_result.result` 被 SSE 截断，
 * 见 `domain/reference.ts` 的长注释）。diff 由 `domain/diff.ts` 纯函数算出，
 * 不新增任何请求、不改后端。
 *
 * **为什么默认只画 16 行**：工具行嵌在转录里，铺开一份 300 行 diff 会把
 * 「助手说了什么」淹掉。留头尾各 8 行 + 明确的「还有 N 行」，比无限滚动更
 * 容易看出「两端各动了什么」。
 */

import { memo, useMemo } from 'react'
import { Check, Copy } from 'lucide-react'

import { useCopyFeedback } from '@/hooks/use-copy-feedback'

import { foldRows, hunkRows, lineDiff, type DiffRow } from '../../domain/diff'

/** 转录内默认可见行数（超出折叠，抄 DSH `DiffBlock` 的同名常量语义） */
export const DIFF_MAX_LINES = 16

const ROW_CLASS: Record<DiffRow['kind'], string> = {
  add: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  del: 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
  context: 'text-muted-foreground',
}

const SIGN: Record<DiffRow['kind'], string> = { add: '+', del: '−', context: ' ' }

/** 复制的载荷用标准 unified diff 前缀（`+`/`-`/空格），粘到别处仍能被 diff 工具认 */
function toUnified(rows: DiffRow[]): string {
  return rows
    .map((row) => `${row.kind === 'add' ? '+' : row.kind === 'del' ? '-' : ' '}${row.text}`)
    .join('\n')
}

export const DiffBlock = memo(function DiffBlock({
  original,
  replacement,
  /** 被改文件的显示名（有就放在标题行，让「改了哪个文件」一眼可见） */
  filename,
}: {
  original: string
  replacement: string
  filename?: string
}) {
  const { copied, copy } = useCopyFeedback()

  const { rows, hidden, truncated, changed } = useMemo(() => {
    const result = lineDiff(original, replacement)
    const all = result.hunks.flatMap((hunk) => hunkRows(hunk))
    const folded = foldRows(all, DIFF_MAX_LINES)
    return {
      rows: folded.rows,
      hidden: folded.hidden,
      truncated: result.truncated,
      changed: all.some((row) => row.kind !== 'context'),
    }
  }, [original, replacement])

  // 一模一样的「改写」不该画出一个空块——没有改动就是没有改动
  if (!changed) {
    return (
      <p className="mt-1.5 text-[11.5px] text-muted-foreground">改写内容与原文一致，未检测到改动。</p>
    )
  }

  return (
    <div className="mt-1.5 rounded-[8px] border border-border/70 bg-secondary/20">
      <div className="flex items-center justify-between gap-2 border-b border-border/70 px-2 py-1">
        <span className="truncate text-[11px] text-muted-foreground">
          {filename ? `修订 · ${filename}` : '修订内容'}
          {truncated && <span className="ml-1 text-amber-600 dark:text-amber-400">（改动过大，按整篇替换显示）</span>}
        </span>
        <button
          type="button"
          className="flex flex-none items-center gap-1 rounded-[5px] px-1.5 py-0.5 text-[10.5px] text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
          title={copied ? '已复制' : '复制为 unified diff'}
          aria-label={copied ? '已复制修订' : '复制修订为 unified diff'}
          onClick={() => void copy(toUnified(rows))}
        >
          {copied ? <Check className="size-3" aria-hidden /> : <Copy className="size-3" aria-hidden />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-mono text-[11px] leading-[1.55]">
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.old ?? 0}:${row.new ?? 0}:${row.kind}`} className={ROW_CLASS[row.kind]}>
                {/* 两个行号列各 2.5rem：不给行号，律师没法回原文定位 */}
                <td className="w-10 select-none pr-1 text-right text-[10px] opacity-55">{row.old ?? ''}</td>
                <td className="w-10 select-none pr-1.5 text-right text-[10px] opacity-55">{row.new ?? ''}</td>
                <td className="w-3 select-none">{SIGN[row.kind]}</td>
                <td className="whitespace-pre-wrap break-all pr-2">{row.text || '\u00a0'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <p className="border-t border-border/70 px-2 py-1 text-[10.5px] text-muted-foreground">
          另有 {hidden} 行未显示（已保留开头与结尾各 {Math.ceil(DIFF_MAX_LINES / 2)} 行）
        </p>
      )}
    </div>
  )
})
