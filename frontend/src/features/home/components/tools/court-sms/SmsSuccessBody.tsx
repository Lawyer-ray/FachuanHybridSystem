import { ChevronDown, Copy, Download, FileText, Link2, Loader2 } from 'lucide-react'
import { useState } from 'react'

import { courtSmsDocDownloadUrl, triggerDownload, type CourtSmsDetail } from '../../../api'
import { cn } from '@/lib/utils'
import { copyDocFile } from './copy-files'
import { SMS_STATUS_LABEL, SMS_TYPE_LABEL } from './stages'

/** 行内小按钮：描边风格（行内不放实心主按钮，主行动留给 footer） */
const ROW_BTN =
  'flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'

/** 通知结果摘要：notification_results = { 平台: { success: bool, ... } } */
function notifySummary(nr: Record<string, unknown> | null): string | null {
  if (!nr) return null
  const entries = Object.entries(nr)
  if (entries.length === 0) return null
  const ok = entries.filter(([, v]) => {
    return typeof v === 'object' && v !== null && (v as { success?: unknown }).success === true
  }).length
  return `通知 ${ok}/${entries.length} 个渠道成功`
}

/** 详情折叠区里的一行「标签: 值」 */
function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 text-[11.5px] leading-relaxed">
      <span className="w-[62px] flex-none text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 break-words">{value}</span>
    </div>
  )
}

/**
 * 处理完成（completed）的结果体：
 * 关联案件 chip + 已重命名文书列表（复制文件 / 下载，重命名后文件名即案件规范名）
 * + 「查看详情」折叠（类型 / 案号 / 当事人 / 通知 / 短信原文）。
 */
export function SmsSuccessBody({ detail }: { detail: CourtSmsDetail }) {
  const [open, setOpen] = useState(false)
  const [copyingIdx, setCopyingIdx] = useState<number | null>(null)
  const docs = detail.documents
  const notify = notifySummary(detail.notification_results)

  const copyDoc = async (i: number, name: string) => {
    setCopyingIdx(i)
    try {
      await copyDocFile(detail.id, i, name)
    } finally {
      setCopyingIdx(null)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 rounded-[10px] border border-status-green/40 bg-status-green-bg px-3 py-2">
        <Link2 className="h-3.5 w-3.5 flex-none text-status-green" />
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold">
          {detail.case ? `已归档到案件：${detail.case.name}` : '本次未关联案件（通知类短信）'}
        </span>
      </div>

      {docs.length > 0 ? (
        <div className="flex flex-col gap-2">
          <div className="text-[11px] font-semibold text-muted-foreground">
            已下载文书 {docs.length} 件（文件已按案件规范自动重命名）
          </div>
          {docs.map((d, i) => (
            <div
              key={`${d.id ?? 'doc'}-${i}`}
              className="flex items-center gap-2.5 rounded-[10px] border border-border bg-secondary/40 px-3 py-2 transition-colors hover:bg-secondary/70"
            >
              <FileText className="h-4 w-4 flex-none text-status-blue" />
              <span className="min-w-0 flex-1 truncate text-[12px] font-medium" title={d.name}>
                {d.name}
              </span>
              <button
                type="button"
                className={ROW_BTN}
                disabled={copyingIdx !== null}
                title="复制文件，可直接粘贴到对话框发送"
                onClick={() => void copyDoc(i, d.name)}
              >
                {copyingIdx === i ? <Loader2 className="h-3 w-3 animate-spin" /> : <Copy className="h-3 w-3" />}
                复制
              </button>
              <button type="button" className={ROW_BTN} onClick={() => triggerDownload(courtSmsDocDownloadUrl(detail.id, i))}>
                <Download className="h-3 w-3" />
                下载
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-[10px] border border-border bg-secondary/40 px-3 py-2 text-[11.5px] text-muted-foreground">
          本次短信没有附带可下载文书。
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 self-start text-[11.5px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
        {open ? '收起详情' : '查看详情'}
      </button>

      {open && (
        <div className="animate-in fade-in slide-in-from-top-1 flex flex-col gap-1.5 rounded-[10px] border border-border bg-secondary/30 px-3 py-2.5 duration-200">
          <Field label="状态" value={SMS_STATUS_LABEL[detail.status] ?? detail.status} />
          {detail.sms_type && <Field label="短信类型" value={SMS_TYPE_LABEL[detail.sms_type] ?? detail.sms_type} />}
          {detail.case_numbers.length > 0 && <Field label="案号" value={detail.case_numbers.join('、')} />}
          {detail.party_names.length > 0 && <Field label="当事人" value={detail.party_names.join('、')} />}
          {notify && <Field label="通知" value={notify} />}
          <Field label="重试次数" value={String(detail.retry_count)} />
          <div className="mt-1 border-t border-border pt-2">
            <div className="mb-1 text-[11.5px] text-muted-foreground">短信原文</div>
            <pre className="max-h-[120px] overflow-auto rounded-[8px] border border-border bg-background px-2.5 py-2 text-[11px] leading-[1.6] whitespace-pre-wrap break-all">
              {detail.content}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
