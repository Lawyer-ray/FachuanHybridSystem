import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { ArrowRight, Download, Eye, Loader2, PackagePlus, X } from 'lucide-react'
import { toast } from 'sonner'
import { useQuery } from '@tanstack/react-query'

import { LoadingBlock, ErrorBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { materialPrepDetail } from '@/app/paths'
import { getInboxMessage } from '../api'
import { SOURCE_BADGE, SOURCE_LABEL } from '../constants'
import { useConvertToPack } from '../hooks/use-inbox'
import { useAttachmentOpener } from '../hooks/use-attachment-opener'
import { canConvert, isPackSource, packIdOf, type InboxDetail, type InboxRow } from '../types'

/**
 * 消息详情抽屉（右侧滑出）。
 *
 * 为什么不直接进材料预处理：收件箱里绝大多数是**纯通知**（一张网告知书正文、
 * 判决书送达通知），没有附件可拆。对这类消息给一个能读正文的抽屉，比硬塞进
 * 材料预处理阅读器（会得到一个空包 + 「附件解析失败」的误导性提示）诚实得多。
 *
 * 有附件的消息在抽屉里给「转材料包 → 进材料预处理」——一步到位，不必回列表。
 */
export function MessageDrawer({
  row,
  onClose,
  onConverted,
}: {
  row: InboxRow
  onClose: () => void
  /** 转成材料包后跳转（由页面决定怎么走，抽屉不自己 navigate） */
  onConverted: (packId: number) => void
}) {
  const navigate = useNavigate()
  const convert = useConvertToPack()
  const packSource = isPackSource(row)
  const existingPackId = packIdOf(row)

  const detail = useQuery({
    queryKey: ['inbox-detail', row.id],
    queryFn: () => getInboxMessage(row.id),
    // 详情含正文，一条消息入库后正文不会变；转换只改 converted_message_id，
    // 由列表失效负责，详情不必反复重拉
    staleTime: 5 * 60_000,
  })

  const openPack = useCallback(
    (packId: number) => {
      void navigate(materialPrepDetail(packId))
      onClose()
    },
    [navigate, onClose],
  )

  const handleConvert = useCallback(() => {
    void convert
      .mutateAsync(row.id)
      .then((res) => {
        toast.success('已转为材料包，正在打开')
        onConverted(res.pack_id)
      })
      .catch((e) => toast.error(errMessage(e, '转材料包失败')))
  }, [convert, row.id, onConverted])

  return (
    <>
      {/* 遮罩：点击关闭（抽屉内部点击不冒泡到遮罩，因为抽屉单独叠在上层） */}
      <div
        className="fixed inset-0 z-[60] bg-foreground/20 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden
      />
      <aside
        className="fixed inset-y-0 right-0 z-[61] flex w-full max-w-[560px] flex-col border-l border-border bg-card shadow-2xl"
        role="dialog"
        aria-label="消息详情"
      >
        {/* 头部：主题 + 来源 + 关闭 */}
        <header className="flex items-start gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'flex-none rounded-[4px] border px-1.5 py-px text-[10px] font-medium',
                  SOURCE_BADGE[row.source_type] ?? 'border-border bg-secondary text-secondary-foreground',
                )}
              >
                {SOURCE_LABEL[row.source_type] ?? row.source_name}
              </span>
              {row.has_attachments && (
                <span className="text-[11px] text-muted-foreground">{row.attachment_count} 个附件</span>
              )}
            </div>
            <h2 className="mt-1.5 text-[14px] font-semibold leading-snug break-words">{row.subject || '(无主题)'}</h2>
            <p className="mt-1 text-[11.5px] text-muted-foreground break-all">
              {row.sender || row.source_name}
              {row.recipient ? ` · ${row.recipient}` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 flex-none items-center justify-center rounded-[7px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* 主体：正文 + 附件 */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {detail.isLoading && <LoadingBlock text="正在载入正文…" />}
          {detail.isError && (
            <ErrorBlock error={detail.error} fallback={errMessage(detail.error, '正文加载失败')} />
          )}
          {detail.data && <MessageBody detail={detail.data} />}
        </div>

        {/* 底部动作：进材料预处理 / 转材料包 */}
        <footer className="flex items-center gap-2 border-t border-border px-5 py-3">
          {existingPackId != null && (
            <button
              type="button"
              onClick={() => openPack(existingPackId)}
              className="flex h-[32px] flex-1 items-center justify-center gap-1.5 rounded-[8px] bg-foreground px-3 text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85"
            >
              {packSource ? '打开材料预处理' : '打开已转的材料包'}
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </button>
          )}
          {canConvert(row) && (
            <button
              type="button"
              onClick={handleConvert}
              disabled={convert.isPending}
              className="flex h-[32px] flex-1 items-center justify-center gap-1.5 rounded-[8px] bg-foreground px-3 text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {convert.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PackagePlus className="h-3.5 w-3.5" />}
              转材料包并打开
            </button>
          )}
          {existingPackId == null && !canConvert(row) && (
            <p className="flex-1 text-[11.5px] text-muted-foreground">
              这条消息没有附件，无可拆分材料。
            </p>
          )}
        </footer>
      </aside>
    </>
  )
}

/** 正文 + 附件清单（把详情查询的结果渲染成可读内容） */
function MessageBody({ detail }: { detail: InboxDetail }) {
  const hasText = Boolean(detail.body_text?.trim())
  const attachments = detail.attachments ?? []
  const open = useAttachmentOpener(detail.id)

  return (
    <div className="space-y-4">
      {attachments.length > 0 && (
        <section>
          <h3 className="mb-1.5 text-[11.5px] font-semibold text-muted-foreground">附件</h3>
          <ul className="space-y-1">
            {attachments.map((att) => (
              <li
                key={att.part_index}
                className="flex items-center gap-2 rounded-[8px] border border-border bg-secondary/30 px-2.5 py-1.5"
              >
                <span className="min-w-0 flex-1 truncate text-[12px]" title={att.filename}>
                  {att.custom_filename?.trim() || att.original_filename || att.filename}
                </span>
                <button
                  type="button"
                  onClick={() => void open.run(att.part_index, 'preview')}
                  disabled={open.pending?.partIndex === att.part_index}
                  className="flex h-6 w-6 flex-none items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
                  aria-label="预览附件"
                  title="预览"
                >
                  {open.pending?.partIndex === att.part_index && open.pending.kind === 'preview' ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Eye className="h-3.5 w-3.5" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => void open.run(att.part_index, 'download')}
                  disabled={open.pending?.partIndex === att.part_index}
                  className="flex h-6 w-6 flex-none items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
                  aria-label="下载附件"
                  title="下载"
                >
                  {open.pending?.partIndex === att.part_index && open.pending.kind === 'download' ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Download className="h-3.5 w-3.5" />
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {hasText ? (
        <section>
          <h3 className="mb-1.5 text-[11.5px] font-semibold text-muted-foreground">正文</h3>
          {/* 纯文本原样展示：法院送达正文里常有空格对齐的表格，富文本渲染会把它搅碎 */}
          <pre className="rounded-[8px] border border-border bg-secondary/20 p-3 text-[12px] leading-relaxed whitespace-pre-wrap break-words font-sans text-foreground/90">
            {detail.body_text}
          </pre>
        </section>
      ) : (
        !detail.body_html?.trim() && (
          <p className="py-8 text-center text-[12.5px] text-muted-foreground">这条消息没有正文内容</p>
        )
      )}
    </div>
  )
}
