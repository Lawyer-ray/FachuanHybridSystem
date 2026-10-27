import { Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import { ErrorBlock } from '@/components/shared/AsyncState'
import { partyLabel, type PartyKey } from '../../domain'
import { SectionHead } from './SectionHead'

/**
 * ① 我方代表谁——决定全部建议方向，必须选。
 *
 * 三态：uploading（正在读合同识别当事人）/ error（读不出来，让律师关掉重试）/
 * ready（按识别出的真实当事人名渲染选项）。识别结果为空时给可执行说明，
 * 而不是留一片空白让人对着空白发愣。
 */
export function PartySection({
  phase,
  partyOptions,
  party,
  onPick,
  partyHint,
}: {
  phase: 'idle' | 'uploading' | 'ready' | 'error'
  partyOptions: Array<{ key: PartyKey; name: string }>
  party: PartyKey | null
  onPick: (k: PartyKey) => void
  partyHint?: string
}) {
  return (
    <section className="border-b border-border-light py-4">
      <SectionHead index={1} title="我方代表谁？" badge="决定全部建议方向" />
      {/* idle 也显示读合同态：抽屉一打开就已触发上传，idle 只是那一帧 */}
      {(phase === 'idle' || phase === 'uploading') && (
        <div className="flex items-center gap-2 rounded-[8px] border border-border bg-secondary/40 px-3 py-2.5 text-[12px] text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          正在读取合同、识别当事人…
        </div>
      )}

      {phase === 'error' && (
        <ErrorBlock
          // 静态文案没有「错误对象」可抽：fallback 直接给全文（errMessage 收到
          // 非 object 会回 fallback，所以不能只传 error）
          error={null}
          fallback="读取合同失败，无法识别当事人。请关闭后重试。"
          className="px-3 py-2 text-left text-[11.5px]"
        />
      )}

      {phase === 'ready' && (
        <>
          <div className="flex flex-col gap-1.5">
            {partyOptions.map((o) => (
              <button
                key={o.key}
                type="button"
                onClick={() => onPick(o.key)}
                className={cn(
                  'flex items-center gap-2 rounded-[8px] border px-3 py-2 text-left text-[12.5px] transition-colors',
                  party === o.key
                    ? 'border-foreground bg-secondary/60'
                    : 'border-border bg-card hover:border-input',
                )}
              >
                <b className="flex-none font-[600]">{partyLabel(o.key)}</b>
                <span className="truncate text-secondary-foreground" title={o.name}>
                  {o.name}
                </span>
              </button>
            ))}
          </div>

          {partyOptions.length === 0 && (
            <div className="rounded-[8px] border border-border bg-secondary/40 px-3 py-2.5 text-[11.5px] leading-relaxed text-muted-foreground">
              没有从合同里认出当事人（可能不是标准「甲方：…乙方：…」格式）。
              请到复审台后手动指定我方立场。
            </div>
          )}

          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            {party
              ? `已选：${partyLabel(party)}`
              : '请选择我方代表哪一方——决定全部建议方向，选错整批返工。'}
            {partyHint ? ` ${partyHint}` : ''}
          </p>
        </>
      )}
    </section>
  )
}
