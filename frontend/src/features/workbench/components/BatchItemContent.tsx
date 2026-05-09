/** 批量分析结果卡片（结构化渲染 JSON 结果） */

import { cn } from '@/lib/utils'
import { MarkdownContent } from './MarkdownContent'
import { parseBatchResult } from '../utils/format-batch'

export function BatchItemContent({ content }: { content: string }) {
  const headerMatch = content.match(/^###\s+(.+)\n\n([\s\S]*)$/)
  const fileName = headerMatch?.[1]
  const body = headerMatch?.[2] ?? content

  const parsed = parseBatchResult(body)

  if (!parsed) {
    return <MarkdownContent content={content} />
  }

  const metaFields = [
    parsed.case_number !== '未注明' && { label: '案号', value: parsed.case_number },
    parsed.cause !== '未注明' && { label: '案由', value: parsed.cause },
    parsed.court !== '未注明' && { label: '法院', value: parsed.court },
    parsed.judge !== '未注明' && { label: '法官', value: parsed.judge },
    parsed.clerk !== '未注明' && { label: '书记员', value: parsed.clerk },
  ].filter(Boolean) as { label: string; value: string }[]

  return (
    <div className="space-y-3">
      {fileName && (
        <div className="text-sm font-semibold">{fileName}</div>
      )}

      {metaFields.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {metaFields.map((f) => (
            <span
              key={f.label}
              className="inline-flex items-center gap-1 rounded-md bg-background/60 px-2 py-0.5 text-[11px] border border-border/40"
            >
              <span className="text-muted-foreground">{f.label}</span>
              <span className="font-medium">{f.value}</span>
            </span>
          ))}
        </div>
      )}

      <div>
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium',
            parsed.is_relevant
              ? 'bg-green-500/10 text-green-600 dark:text-green-400'
              : 'bg-muted text-muted-foreground',
          )}
        >
          {parsed.is_relevant ? '相关' : '无关'}
        </span>
      </div>

      {parsed.conclusion && (
        <div className="rounded-md border-l-2 border-primary/40 bg-primary/5 px-3 py-2 text-sm">
          <div className="text-[11px] font-medium text-muted-foreground mb-1">结论</div>
          <div>{parsed.conclusion}</div>
        </div>
      )}

      {parsed.analysis && (
        <MarkdownContent content={parsed.analysis} />
      )}
    </div>
  )
}
