import { Download, Eye, Loader2, PackagePlus, ArrowRight } from 'lucide-react'
import { toast } from 'sonner'
import { useQuery } from '@tanstack/react-query'

import { ErrorBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'
import { getInboxMessage } from '../api'
import { useConvertToPack } from '../hooks/use-inbox'
import { useAttachmentOpener } from '../hooks/use-attachment-opener'
import { canConvert, isPackSource, packIdOf, type InboxDetail, type PackJudgement } from '../types'

/**
 * 内容组件需要的行形状：判定三件套的字段 + 详情查询用的 id。
 *
 * 不收完整 InboxRow —— 首页收件箱卡拿到的是 Pick 投影，硬要求完整行
 * 就会逼调用方写 `as` 假行（当初就是那么干的），假行一多，转包/下载判定
 * 就会因漏字段而静默出错。
 */
export type MessageContentRow = PackJudgement & {
  is_read?: boolean
}

/**
 * 一条收件箱消息的可读内容（正文 + 附件 + 底部动作）。
 *
 * **为什么抽出来**：右侧滑出的 `MessageDrawer` 和首页收件箱卡的**就地展开**
 * 是同一份内容、同一组动作（进材料预处理 / 转材料包），只有外壳不同
 * （抽屉会遮住列表，展开是手风琴）。两处各写一份必然漂移——尤其是附件
 * 下载必须走「换一次性票据」那条路径（见 use-attachment-opener 的 401 教训），
 * 漏抄一次就是「用自己的账号下自己的材料也失败」。
 *
 * 加载态沿用收件箱页的约定：查询失败必须与「没有正文」区分开（同 SideCards 的空态纪律）。
 */
export function MessageContent({
  row,
  onConverted,
  /** 已存在可打开的材料包时点「打开」 */
  onOpenPack,
}: {
  row: MessageContentRow
  /** 转成材料包后回调；不传则不给「转材料包」按钮（调用方自己决定跳转） */
  onConverted?: (packId: number) => void
  onOpenPack?: (packId: number) => void
}) {
  const convert = useConvertToPack()
  const packId = packIdOf(row)
  const packSource = isPackSource(row)

  const detail = useQuery({
    queryKey: ['inbox-detail', row.id],
    queryFn: () => getInboxMessage(row.id),
    // 详情含正文，一条消息入库后正文不会变；转换只改 converted_message_id，
    // 由列表失效负责，详情不必反复重拉
    staleTime: 5 * 60_000,
  })

  return (
    <div className="space-y-3">
      {detail.isLoading && (
        <p className="py-4 text-center text-[12px] text-muted-foreground">正在载入正文…</p>
      )}
      {detail.isError && (
        <ErrorBlock error={detail.error} fallback={errMessage(detail.error, '正文加载失败')} />
      )}
      {detail.data && <MessageBody detail={detail.data} />}

      {/* 动作区：材料包 → 打开；可转 → 转材料包；其余说明为什么没有动作 */}
      <div className="flex items-center gap-2 border-t border-border/60 pt-2.5">
        {packId != null && onOpenPack && (
          <button
            type="button"
            onClick={() => onOpenPack(packId)}
            className="flex h-[28px] items-center gap-1.5 rounded-[7px] bg-foreground px-2.5 text-[12px] font-semibold text-background transition-opacity hover:opacity-85"
          >
            {packSource ? '打开材料预处理' : '打开已转的材料包'}
            <ArrowRight className="h-3 w-3" aria-hidden />
          </button>
        )}
        {canConvert(row) && onConverted && (
          <button
            type="button"
            onClick={() => {
              void convert
                .mutateAsync(row.id)
                .then((res) => onConverted(res.pack_id))
                .catch((e) => toast.error(errMessage(e, '转材料包失败')))
            }}
            disabled={convert.isPending}
            className="flex h-[28px] items-center gap-1.5 rounded-[7px] bg-foreground px-2.5 text-[12px] font-semibold text-background transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {convert.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <PackagePlus className="h-3 w-3" />}
            转材料包并打开
          </button>
        )}
        {packId == null && !canConvert(row) && (
          <p className="text-[11.5px] text-muted-foreground">这条消息没有附件，无可拆分材料。</p>
        )}
      </div>
    </div>
  )
}

/** 正文 + 附件清单（把详情查询的结果渲染成可读内容） */
function MessageBody({ detail }: { detail: InboxDetail }) {
  const hasText = Boolean(detail.body_text?.trim())
  const attachments = detail.attachments ?? []
  const open = useAttachmentOpener(detail.id)

  return (
    <div className="space-y-3">
      {attachments.length > 0 && (
        <section>
          <h3 className="mb-1.5 text-[11px] font-semibold text-muted-foreground">附件</h3>
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
          <h3 className="mb-1.5 text-[11px] font-semibold text-muted-foreground">正文</h3>
          {/* 纯文本原样展示：法院送达正文里常有空格对齐的表格，富文本渲染会把它搅碎 */}
          <pre className="max-h-[280px] overflow-y-auto rounded-[8px] border border-border bg-secondary/20 p-3 text-[12px] leading-relaxed whitespace-pre-wrap break-words font-sans text-foreground/90">
            {detail.body_text}
          </pre>
        </section>
      ) : (
        !detail.body_html?.trim() && (
          <p className="py-4 text-center text-[12px] text-muted-foreground">这条消息没有正文内容</p>
        )
      )}
    </div>
  )
}
