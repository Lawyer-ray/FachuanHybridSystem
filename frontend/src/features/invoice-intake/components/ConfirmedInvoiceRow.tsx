import { useState } from 'react'
import { Copy, FileText, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { copyInvoiceToClipboard } from '../api'
import { formatAmount } from '../constants'
import { ROW_BTN } from '@/components/shared/panel-styles'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/**
 * 刚确认完、还留在列表里的那一行（换成「文件名 + 复制」形态）。
 *
 * ## 为什么这行要存在
 *
 * 确认完最想做的下一件事是**复制那个重命名后的发票**（发给财务 / 存一份 / 微信传）。
 * 如果确认后行立刻消失，用户就得绕到项目页去找——多跳两三次，动作被打断。
 *
 * ## 为什么只留在内存里
 *
 * 这只是**本次浏览期间的临时展示**：数据来自确认接口的返回，存在组件 state 里，
 * 刷新页面即消失。绝不能靠数据库状态承载它——那会让「待认领」永久堆着已处理项
 * （用户明确反对过）。
 *
 * ## 视觉上必须一眼看出“已完成”
 *
 * 灰底 + 绿勾 + 无动作按钮（只有复制），与待办行的白底 + 确认/换项目形成对比，
 * 不会被误认为还有事要做。
 */
/** 一行“刚确认完”的记录（纯前端内存态，刷新即弃） */
export interface ConfirmedRow {
  intakeId: number
  invoiceId: number
  buyerName: string
  totalAmount: string | null
  /** 重命名后的文件名（由确认接口返回，前端不自己拼） */
  displayFilename: string
}

export function ConfirmedInvoiceRow({ row }: { row: ConfirmedRow }) {
  const [busy, setBusy] = useState(false)

  const doCopy = async () => {
    if (busy) return
    setBusy(true)
    // busy 必须在 finally 复位：成功分支 return 也要清，否则图标一直转圈
    try {
      const res = await copyInvoiceToClipboard(row.invoiceId)
      if (res.success && res.copied > 0) {
        toast.success('发票已复制，微信对话框直接 ⌘V 粘贴发送')
        return
      }
      const reason = res.reason === 'unsupported' ? '当前环境不支持复制文件本体' : res.reason || '复制文件本体失败'
      if (await copyText(row.displayFilename)) toast.info(`${reason}，已复制文件名`)
      else toast.error('复制失败，请到项目页下载')
    } catch (e) {
      if (await copyText(row.displayFilename)) toast.error(`${errMessage(e, '复制失败')}，已复制文件名`)
      else toast.error(errMessage(e, '复制失败，请到项目页下载'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-[10px] border border-status-green/25 bg-status-green-bg/40 px-2.5 py-2">
      {/* 金额 + 已绑定标记 */}
      <div className="flex items-baseline gap-2">
        <span className="text-[13px] leading-none font-semibold tabular-nums text-muted-foreground">
          {row.totalAmount ? formatAmount(row.totalAmount) : '金额未识别'}
        </span>
        <span className="text-[10.5px] text-muted-foreground">{row.buyerName}</span>
        <span className="ml-auto flex-none rounded-[99px] border border-status-green/30 bg-status-green-bg px-[7px] py-[1px] text-[10px] font-semibold text-status-green">
          已绑定
        </span>
      </div>

      {/* 重命名后的文件名：这是复制出去的那个名字，必须看得见 */}
      <div className="mt-[5px] flex items-start gap-1 text-[10.5px] text-secondary-foreground">
        <FileText className="mt-[1px] h-3 w-3 flex-none opacity-60" aria-hidden />
        <span className="min-w-0 break-all">{row.displayFilename || '发票已生成'}</span>
      </div>

      <div className="mt-[7px] flex items-center gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={() => void doCopy()}
          className={cn(ROW_BTN, 'font-semibold')}
          title={`复制文件（${row.displayFilename}）`}
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
          复制发票
        </button>
      </div>
    </div>
  )
}

/** 落板失败时兜底复制文件名（至少能对上文件）。 */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
