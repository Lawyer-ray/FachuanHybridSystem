import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router'

import { projectDetail } from '@/app/paths'
import { cn } from '@/lib/utils'
import { getContractMatch } from '../api'

/**
 * 「可能关联的在办项目」面板（一期：只给候选，不写财务数据）。
 *
 * ## 为什么不做自动写入
 *
 * 只靠金额匹配必然错：真实数据里 108 个在办合同有大量 `fixed_amount` 为空或
 * 重复（30000 出现多次）。写错财务数据比不写更糟。所以这里只把候选和**理由**
 * 摆出来，由律师点进项目自己关联。
 *
 * ## 为什么要显示「理由」
 *
 * 律师需要判断「为什么系统觉得是这个项目」。只给一个名字，他要么无脑信、要么
 * 完全不看；给出「当事人命中 张某」他才能一眼判断对错。这也是匹配失败时唯一
 * 有用的信息——他能据此知道系统到底抽到了什么。
 */

const FEE_MODE_LABEL: Record<string, string> = {
  FIXED: '固定收费',
  SEMI_RISK: '半风险',
  FULL_RISK: '全风险',
  CUSTOM: '自定义',
  risk: '风险收费',
}

export function ContractMatchPanel({ messageId }: { messageId: number }) {
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ['inbox-contract-match', messageId],
    queryFn: () => getContractMatch(messageId),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })

  if (q.isLoading) {
    return (
      <div className="flex items-center gap-2 px-1 py-3 text-[12px] text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        正在匹配在办项目…
      </div>
    )
  }

  // 匹配失败不该让用户看到报错——它只是「没匹配到」，属正常结果
  if (q.error || !q.data) {
    return (
      <p className="px-1 py-3 text-[12px] text-muted-foreground">
        无法获取匹配结果，请手动在项目中关联。
      </p>
    )
  }

  const { status, candidates, extracted_amounts, extracted_case_numbers } = q.data

  if (status === 'none' || candidates.length === 0) {
    return (
      <div className="rounded-[8px] border border-dashed border-border bg-secondary/20 px-3 py-2.5">
        <p className="text-[12px] text-muted-foreground">未找到匹配的在办项目，等待人工关联。</p>
        {(extracted_amounts.length > 0 || extracted_case_numbers.length > 0) && (
          <p className="mt-1 text-[11px] text-muted-foreground/80">
            系统识别到：
            {extracted_case_numbers.length > 0 && <> 案号 {extracted_case_numbers.join('、')}</>}
            {extracted_amounts.length > 0 && <> 金额 {extracted_amounts.join('、')} 元</>}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-muted-foreground">
        {status === 'confident'
          ? '系统认为这些项目可能对应本条消息，请确认后手动关联：'
          : '可能对应的在办项目（按可信度排序），请人工确认：'}
      </p>
      <ul className="space-y-1.5">
        {candidates.map((c) => (
          <li key={c.contract_id}>
            <button
              type="button"
              onClick={() => void navigate(projectDetail(c.contract_id))}
              className={cn(
                'group w-full rounded-[8px] border border-border bg-card px-3 py-2 text-left transition-colors',
                'hover:border-ring/40 hover:bg-secondary/40',
              )}
            >
              <div className="flex items-center gap-1.5">
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground">
                  {c.contract_name}
                </span>
                <span className="flex-none rounded-[4px] border border-border px-1.5 py-px text-[10px] text-muted-foreground">
                  {FEE_MODE_LABEL[c.fee_mode] ?? c.fee_mode}
                </span>
                <ArrowRight className="h-3.5 w-3.5 flex-none text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
              {c.outstanding_amount && (
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  应收余额 ¥{c.outstanding_amount}
                </p>
              )}
              {c.reasons.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {c.reasons.map((r) => (
                    <li key={r} className="text-[11px] text-muted-foreground/90">
                      · {r}
                    </li>
                  ))}
                </ul>
              )}
              {c.caveat && <p className="mt-1 text-[11px] text-amber-600">{c.caveat}</p>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
