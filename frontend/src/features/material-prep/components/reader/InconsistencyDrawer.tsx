import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

import { inconsistencyKindOf, pagesText, sortInconsistencies } from '../../draft'
import type { Inconsistency } from '../../types'

/**
 * 全本「跨页文字不一致」清单（右侧抽屉）。
 *
 * ## 为什么必须做成全局清单
 *
 * 同一枚章在一份 164 页卷宗里被识别 150+ 次，其中 5 次错成另一种写法。
 * 律师逐页读不可能发现；而它恰好落在「谁签的字」这种决定性的位置。
 * 段内面板只能看到自己那一段，发现不了跨段的问题，所以需要一个全本视角的入口。
 *
 * ## 文案必须按 kind 分支（不能一律「疑似错字」）
 *
 * 后端逐条给 `kind`，三种判据的**证据强度完全不同**：
 *  · `frequency`：频次悬殊（178 次 vs 5 次），有「哪个写法对」的统计证据 → 说「疑似错字」；
 *  · `entity_cluster`：同角色字段下姓名 ≥3 种写法跨 ≥2 页聚类，**没有任何证据说明哪个对**
 *    （同姓同名首字的兄弟姐妹完全可能落进同一簇）→ 只说「多写法候选，请核对是否同一人」。
 *    沿用「疑似错字」会让律师把两个真人合并成一个，比漏报坏得多；
 *  · `id_malformed`：证件号位数结构不合法（硬证据）配同字段唯一合法候选 → 点明结构异常。
 *
 * 缺 kind（旧任务产物 / 旧草稿）按 frequency 处理，与历史行为一致。
 *
 * ## 排序与配色
 *
 * high 在最前（frequency 恒 high，两类新判据恒 medium，所以有统计证据的永远排在候选之前），
 * 同级变体次数多的在前。整块不上彩色语义：confidence 只用一个灰底小字标出。
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
              ? `全本共 ${sorted.length} 处同一枚章 / 同一个字段出现多种写法，按可疑程度排序`
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

/**
 * 一行的标签与说明文案。
 *
 * `entity_cluster` 刻意**不提次数、不说哪个写法对**：canonical 只是簇里出现页数最多的
 * 参照写法，把「其它 M 次写作 X」摆出来等于暗示 X 是正确答案。
 */
function rowCopyOf(item: Inconsistency): { label: string; text: string } {
  switch (inconsistencyKindOf(item)) {
    case 'entity_cluster':
      return {
        label: '姓名多写法候选',
        text: `同一角色下另有「${item.canonical}」等写法，请核对是否同一人`,
      }
    case 'id_malformed':
      return {
        label: '证件号结构异常',
        text: `位数结构不合法；同字段唯一合法候选「${item.canonical}」，请核对原页`,
      }
    default:
      return {
        label: '疑似错字',
        text: `出现 ${item.variant_count} 次，其它 ${item.canonical_count} 次写作「${item.canonical}」`,
      }
  }
}

/** 一条不一致：待核对的写法 + 按判据分支的说明 + 标签 + 页号（可点跳转） */
function InconsistencyRow({ item, onGotoPage }: { item: Inconsistency; onGotoPage?: (p: number) => void }) {
  const { label, text } = rowCopyOf(item)
  return (
    <li className="rounded-lg border border-zinc-200 bg-card px-2.5 py-2">
      <div className="flex items-baseline gap-1.5 text-[12.5px] leading-relaxed">
        <span className="font-medium text-foreground">「{item.variant}」</span>
        <span className="text-muted-foreground">{text}</span>
        <span className="ml-auto flex-none rounded bg-secondary px-1 text-[10px] leading-4 text-muted-foreground">
          {label}
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
