import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { syncPendingIntakes } from '../api'
import { INVOICE_INTAKE_COUNT_KEY, INVOICE_INTAKE_PENDING_KEY } from '@/features/invoice-intake'
import { INTAKE_COUNT_KEY, INTAKE_PENDING_KEY } from '@/features/payment-intake'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/**
 * 「待认领」卡右上角的同步按钮 —— 点一下就拉最近 1 天的邮件，把没处理过的
 * 到账与发票收进来。
 *
 * ## 为什么这个按钮必须有
 *
 * 没有它，卡片一旦是空态就成了死角：用户知道"应该会有东西进来"，但只能等
 * 后台定时任务，或者绕到收件箱页去点同步。财务刚发来发票的那一分钟里，
 * 这个按钮是唯一的即时出口。
 *
 * ## 为什么按完要轮询而不是只调一次
 *
 * 后端做两件事：立即补扫**已入库**的邮件（同步、秒级出结果），再提交 IMAP
 * 异步同步去拉**新**邮件（可能要几十秒）。所以：
 *
 * 1. 先按返回的 `payment_created + invoice_created` 立刻刷新一次并与用户报数；
 * 2. 再在随后几秒里重取几次列表，把异步拉回来、刚入池的那批也接上。
 *
 * 不轮询的话，用户会看到"同步了但什么都没出现"——实际上东西在 20 秒后才到。
 */
const REFRESH_DELAYS_MS = [2500, 6000, 12000] as const

export function PendingSyncButton() {
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: INTAKE_PENDING_KEY })
    void qc.invalidateQueries({ queryKey: INTAKE_COUNT_KEY })
    void qc.invalidateQueries({ queryKey: INVOICE_INTAKE_PENDING_KEY })
    void qc.invalidateQueries({ queryKey: INVOICE_INTAKE_COUNT_KEY })
  }

  const run = async () => {
    if (busy) return
    setBusy(true)
    try {
      const res = await syncPendingIntakes(1)
      invalidate()

      const total = res.payment_created + res.invoice_created
      if (total > 0) {
        const parts = [
          res.payment_created ? `${res.payment_created} 笔款项` : '',
          res.invoice_created ? `${res.invoice_created} 张发票` : '',
        ].filter(Boolean)
        toast.success(`已收进 ${parts.join('、')}`)
      } else if (res.sources_submitted > 0) {
        // 已入库的没新东西，但还在等邮箱拉取：别报"没有"，会误导成"确实没有"
        toast.info('已提交邮箱同步，稍后若收到新通知会自动出现在这里')
      } else {
        toast.info('最近 1 天没有新的到账或发票')
      }
    } catch (e) {
      toast.error(errMessage(e, '同步失败，请重试'))
    } finally {
      // 异步拉取回来的那批：隔几秒再刷一次（失败静默，不打扰）
      for (const delay of REFRESH_DELAYS_MS) {
        window.setTimeout(invalidate, delay)
      }
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={() => void run()}
      disabled={busy}
      title="同步最近 1 天的邮件（到账通知与发票）"
      className={cn(
        'flex h-[22px] items-center gap-1 rounded-[6px] border border-border bg-card px-1.5',
        'text-[10.5px] font-medium text-secondary-foreground transition-colors',
        busy ? 'cursor-wait opacity-60' : 'hover:bg-secondary hover:text-foreground',
      )}
    >
      {busy ? (
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
      ) : (
        <RefreshCw className="h-3 w-3" aria-hidden />
      )}
      {busy ? '同步中' : '同步'}
    </button>
  )
}
