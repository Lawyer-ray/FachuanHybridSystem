import { ExternalLink, MapPin, TriangleAlert, UserRound } from 'lucide-react'

import { DOC_TYPE_LABELS, EXTRACTION_METHOD_LABELS } from '../constants'
import { formatContacts, resolveMediaUrl } from '../domain'
import type { RecognitionInfo, TaskOut } from '../types'
import { safeHttpUrl } from '@/lib/url'
import { cn } from '@/lib/utils'

interface Props {
  task: TaskOut
  recognition: RecognitionInfo
}

const DOC_TYPE_STYLES: Record<string, string> = {
  summons: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  execution: 'border-status-purple/40 bg-status-purple-bg text-status-purple',
}

/** 识别结果摘要卡：类型/案号/置信度/引擎 + 联系人/地址 + 文书预览。 */
export function RecognitionSummary({ task, recognition }: Props) {
  const contactsText = formatContacts(task.contacts ?? [])
  const fileUrl = resolveMediaUrl(task.file_url)
  const methodLabel = recognition.extraction_method
    ? EXTRACTION_METHOD_LABELS[recognition.extraction_method] ?? recognition.extraction_method
    : null

  return (
    <div className="dr-stagger flex animate-in fade-in slide-in-from-top-1 duration-300 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
        <span
          className={cn(
            'rounded-[6px] border px-2 py-[3px] font-semibold',
            DOC_TYPE_STYLES[recognition.document_type ?? ''] ?? 'border-border bg-secondary',
          )}
        >
          {DOC_TYPE_LABELS[recognition.document_type ?? ''] ?? '文书'}
        </span>
        {recognition.case_number && (
          <span className="rounded-[6px] bg-secondary/60 px-2 py-[3px] font-medium tabular-nums">
            {recognition.case_number}
          </span>
        )}
        {recognition.confidence != null && (
          <span className="tabular-nums text-muted-foreground">
            置信度 {Math.round(recognition.confidence * 100)}%
          </span>
        )}
        <span className="text-muted-foreground">
          {recognition.llm_model ?? '关键词+规则'}
          {methodLabel ? ` · ${methodLabel}` : ''}
        </span>
        {recognition.degraded && (
          <span className="inline-flex items-center gap-1 rounded-[6px] border border-status-yellow/50 bg-status-yellow-bg px-1.5 py-[2px] text-[10.5px] font-semibold text-status-yellow">
            <TriangleAlert className="h-3 w-3" />
            降级识别·建议核对
          </span>
        )}
        {fileUrl && (
          <a
            href={safeHttpUrl(fileUrl)}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1 rounded-[6px] border border-border px-2 py-[3px] text-[11px] text-muted-foreground transition-colors hover:border-ring/40 hover:text-foreground"
          >
            <ExternalLink className="h-3 w-3" />
            查看文书
          </a>
        )}
      </div>

      {(contactsText || task.address) && (
        <div className="flex animate-in fade-in slide-in-from-bottom-1 delay-150 duration-300 flex-col gap-1 rounded-[10px] border border-border bg-secondary/40 px-3 py-2 text-[12px]">
          {contactsText && (
            <div className="flex items-center gap-1.5">
              <UserRound className="h-3.5 w-3.5 flex-none text-muted-foreground" />
              <span className="min-w-0 truncate">{contactsText}</span>
            </div>
          )}
          {task.address && (
            <div className="flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5 flex-none text-muted-foreground" />
              <span className="min-w-0 truncate">{task.address}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
