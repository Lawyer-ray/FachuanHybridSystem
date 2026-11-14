import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

import { pagesText, sortInconsistencies } from '../../draft/quality'
import type { Inconsistency } from '../../types'

/**
 * 全本「跨页文字不一致」清单（右侧抽屉）。
 *
 * ## 为什么必须做成全局清单
 *
 * 同一枚章在一份 164 页卷宗里被识别 150+ 次，其中 5 次错成「罗问文」（应为「罗向文」）。
 * 律师逐页读不可能发现；而它恰好落在「谁签的字」这种决定性的位置。
 * 段内面板只能看到自己那一段，发现不了跨段的问题，所以需要一个全本视角的入口。
 *
 * ## 每条长什么样
 *
 * `「罗问文」出现 5 次，其它 150 次写作「罗向文」 — 疑似错字 [P12, P45]`
 *
 * 少的那个是**疑似错字**、多的那个是基准，这是后端的判定（canonical / variant），
 * 前端不重新猜。点页号跳到该页；没有页号列表时（旧数据）就只陈述不跳。
 *
 * ## 排序与配色
 *
 * high 在最前（最该看的永远在最上面），同级变体次数多的在前。整块不上彩色语义：
 * confidence 只用一个灰底小字标出，避免又造一套颜色。
 */
export function InconsistencyDrawer({
  open,
  onOpenChange,
  items,
  onGotoPage,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 已完成字段校验的清单（来源见 draft/quality.readInconsistencies） */
  items: Inconsistency[]
  /** 点页号跳原页；不传则页号只展示不可点 */
  onGotoPage?: (p: number) => void
}) {
  const sorted = sortInconsistencies(items)
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-inconsistency-drawer aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>跨页不一致</SheetTitle>
          <SheetDescription>
            {sorted.length > 0
              ? `全本共 ${sorted.length} 处同一枚章 / 同一个字段被识别成两种写法，按可疑程度排序`
              : '没有发现跨页不一致'}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="px-6">
          {sorted.length === 0 ? (
            <p className="py-6 text-[12px] leading-relaxed text-muted-foreground">
              这份材料包没有跨页不一致记录。旧任务的识别结果里没有这项统计，属正常。
            </p>
          ) : (
            <ul className="flex flex-col gap-2 py-2">
              {sorted.map((it) => (
                <InconsistencyRow key={`${it.canonical}|${it.variant}`} item={it} onGotoPage={onGotoPage} />
              ))}
            </ul>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}

/** 一条不一致：基准写法 + 疑似错字 + 次数 + 页号（可点跳转） */
function InconsistencyRow({ item, onGotoPage }: { item: Inconsistency; onGotoPage?: (p: number) => void }) {
  return (
    <li className="rounded-lg border border-zinc-200 bg-card px-2.5 py-2">
      <div className="flex items-baseline gap-1.5 text-[12.5px] leading-relaxed">
        <span className="font-medium text-foreground">「{item.variant}」</span>
        <span className="text-muted-foreground">
          出现 {item.variant_count} 次，其它 {item.canonical_count} 次写作「{item.canonical}」
        </span>
        <span className="ml-auto flex-none rounded bg-secondary px-1 text-[10px] leading-4 text-muted-foreground">
          疑似错字
        </span>
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
        {item.confidence && (
          <span className="text-[10.5px] text-muted-foreground">{item.confidence === 'high' ? '高可信' : item.confidence}</span>
        )}
        <span className="text-[10.5px] tabular-nums text-muted-foreground">{pagesText(item.pages) || '页号缺'}</span>
        {onGotoPage &&
          item.pages.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onGotoPage(p)}
              className="cursor-pointer text-[10.5px] tabular-nums text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              p{p}
            </button>
          ))}
      </div>
    </li>
  )
}
