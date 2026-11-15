import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

import {
  disagreementKey,
  disagreementKindLabel,
  engineLabel,
  groupBySeverity,
  variantTextOf,
} from '../../draft'
import type { EngineDisagreement, EngineName } from '../../types'
import { cn } from '@/lib/utils'

/**
 * 双引擎分歧清单（右侧抽屉）。
 *
 * ## 为什么这是「只找分歧」而不是「智能校验」
 *
 * 两个引擎在一份卷宗上跑，一致的部分没有信息量：一致**不等于**正确（实测存在两个
 * 引擎把同一处姓名一致地认错）。真正值钱的是它们**读得不一样**的地方——那是一个
 * 确定信号，说明这一处至少有一方错了。所以这里只列分歧，且刻意**不提供「采纳某个
 * 引擎」的按钮**：裁决权在律师，按钮一按下去，错的那一份就进了诉状的引用。
 *
 * ## 为什么每项都能跳到原页并画双框
 *
 * 文字层面的「张三丰 / 张四丰」律师看不出差别，必须回原件对对看。所以点一条就
 * 滚到那一页、同时画出两个引擎的框（实线绿 = MinerU，虚线琥珀 = VL）——
 * 这才是「两个框在这里，我自己看」。
 *
 * ## 分组与配色
 *
 * high 红、medium 橙、low 灰。low 是**版面切分差异**（一方把这几行并进了上一段），
 * 一份百页卷宗能出几十条，默认折叠——不折叠就会把真分歧淹掉。
 *
 * ## 「已核对」为什么落草稿
 *
 * 几十条分歧逐个对着原件看，是律师最可能中断的地方（接电话、关掉、换机器）。
 * 勾选记在 `draft.engineChecked` 上随草稿保存，下次打开还是勾着的。
 */
export function EngineDisagreementDrawer({
  open,
  onOpenChange,
  items,
  checked = [],
  activeKey = null,
  onJump,
  onToggleChecked,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 已完成字段校验的分歧清单（来源见 draft/engine.readEngineDisagreements） */
  items: EngineDisagreement[]
  /** 已核对的分歧键（`disagreementKey`） */
  checked?: string[]
  /** 当前在页面上高亮着的那一条（点过之后保持亮，方便眼睛在清单与页面间来回对） */
  activeKey?: string | null
  /** 点一条：跳到该页并画双框 */
  onJump?: (pageNo: number, index: number) => void
  /** 勾/取消「已核对」；不传则不显示勾选框 */
  onToggleChecked?: (key: string, checked: boolean) => void
}) {
  // low 默认折叠：那是版面切分差异，不是错字
  const [lowOpen, setLowOpen] = useState(false)
  const checkedSet = new Set(checked)
  const groups = groupBySeverity(items, checkedSet)

  const renderRow = (d: EngineDisagreement, index: number) => {
    const key = disagreementKey(d)
    return (
      <DisagreementRow
        key={key}
        item={d}
        index={index}
        checked={checkedSet.has(key)}
        active={activeKey === key}
        onJump={onJump}
        onToggleChecked={onToggleChecked ? (v) => onToggleChecked(key, v) : undefined}
      />
    )
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-engine-disagreement-drawer aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>引擎分歧</SheetTitle>
          <SheetDescription>
            {items.length > 0
              ? groups.unchecked > 0
                ? `全卷 ${items.length} 处两个引擎读得不一样，还剩 ${groups.unchecked} 处未核对`
                : `全卷 ${items.length} 处两个引擎读得不一样，已全部核对`
              : '两个引擎的识别结果一致'}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="px-6">
          {items.length === 0 ? (
            <p className="py-6 text-[12px] leading-relaxed text-muted-foreground">
              两引擎识别一致。旧任务 / 单引擎识别的结果里没有这项统计，属正常。
            </p>
          ) : (
            <div className="flex flex-col gap-4 py-2">
              <Group title="高危" tone="high" items={groups.high} renderRow={renderRow} />
              <Group title="中危" tone="medium" items={groups.medium} renderRow={renderRow} />
              {groups.low.length > 0 && (
                <section data-severity="low">
                  <button
                    type="button"
                    onClick={() => setLowOpen((v) => !v)}
                    aria-expanded={lowOpen}
                    className="flex w-full items-center gap-1 rounded-md px-1 py-1 text-left text-[12px] font-medium text-muted-foreground hover:bg-secondary"
                  >
                    {lowOpen ? (
                      <ChevronDown className="h-3.5 w-3.5 flex-none" aria-hidden />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 flex-none" aria-hidden />
                    )}
                    <span className="h-1.5 w-1.5 flex-none rounded-full bg-zinc-400" aria-hidden />
                    <span>低危（{groups.low.length}）</span>
                    <span className="ml-auto font-normal">{lowOpen ? '收起' : '展开'}</span>
                  </button>
                  {lowOpen && <div className="mt-1 flex flex-col gap-2">{groups.low.map(renderRow)}</div>}
                </section>
              )}
            </div>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}

/** 严重度分组：标题行只在组内有内容时出现（不给「高危（0）」这种空标题占版面） */
function Group({
  title,
  tone,
  items,
  renderRow,
}: {
  title: string
  tone: 'high' | 'medium'
  items: EngineDisagreement[]
  renderRow: (d: EngineDisagreement, index: number) => React.ReactNode
}) {
  if (items.length === 0) return null
  return (
    <section data-severity={tone}>
      <div className="flex items-center gap-1 px-1 py-1 text-[12px] font-medium text-foreground">
        <span
          className={cn('h-1.5 w-1.5 flex-none rounded-full', tone === 'high' ? 'bg-red-600' : 'bg-amber-500')}
          aria-hidden
        />
        <span>
          {title}（{items.length}）
        </span>
      </div>
      <div className="mt-1 flex flex-col gap-2">{items.map(renderRow)}</div>
    </section>
  )
}

/** 一条分歧：页码 + 类型 + 锚点标签 + 两个引擎的文本并列 + 已核对勾选 */
function DisagreementRow({
  item,
  index,
  checked,
  active,
  onJump,
  onToggleChecked,
}: {
  item: EngineDisagreement
  /** 在清单里的位置（跳转回调要它，页面侧据此高亮） */
  index: number
  checked: boolean
  active: boolean
  onJump?: (pageNo: number, index: number) => void
  onToggleChecked?: (checked: boolean) => void
}) {
  const rows: { engine: EngineName; text: string }[] = item.variants.map((v) => ({
    engine: v.engine,
    text: variantTextOf(item, v.engine),
  }))
  return (
    <li
      data-engine-disagreement
      data-checked={checked ? 'true' : undefined}
      className={cn(
        'rounded-lg border px-2.5 py-2 transition-colors',
        active ? 'border-zinc-800 bg-secondary/60' : 'border-zinc-200 bg-card',
        // 已核对：整条置灰但仍留在原位——删掉会让清单在律师眼下跳动，位置一变就找不回刚看到哪
        checked && 'opacity-50',
      )}
    >
      <div className="flex items-baseline gap-1.5 text-[12.5px] leading-relaxed">
        {onToggleChecked && (
          <input
            type="checkbox"
            checked={checked}
            aria-label={`第 ${item.page_no} 页这条分歧已核对`}
            onChange={(e) => onToggleChecked(e.target.checked)}
            className="mt-0.5 h-3.5 w-3.5 flex-none cursor-pointer accent-zinc-700"
          />
        )}
        <button
          type="button"
          disabled={!onJump}
          onClick={() => onJump?.(item.page_no, index)}
          title="跳到这一页，同时画出两个引擎的框"
          className={cn(
            'flex-none rounded px-1 text-[11px] tabular-nums',
            onJump
              ? 'cursor-pointer bg-secondary text-foreground hover:bg-zinc-200'
              : 'bg-secondary text-muted-foreground',
          )}
        >
          第{item.page_no}页
        </button>
        <span className="min-w-0 flex-1 truncate text-muted-foreground">{item.context || '（无上下文）'}</span>
        {item.anchor_hit && (
          <span className="flex-none rounded bg-red-50 px-1 text-[10px] leading-4 text-red-700">
            含身份证号/账号
          </span>
        )}
      </div>

      {/* 两个变体并列：引擎名 + 文本。不排先后、不加「更可能」的标记——谁对由律师判 */}
      <div className="mt-1 flex flex-col gap-0.5">
        {rows.map(({ engine, text }) => (
          <div key={engine} className="flex items-baseline gap-1.5 text-[12px] leading-relaxed">
            <span className="w-[92px] flex-none truncate text-[10.5px] text-muted-foreground">
              {engineLabel(engine)}
            </span>
            <span className={cn('min-w-0 flex-1 break-all', text ? 'text-foreground' : 'text-muted-foreground')}>
              {text || '（无此行）'}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
        <span>{disagreementKindLabel(item.kind)}</span>
        {item.similarity > 0 && <span className="tabular-nums">相似度 {Math.round(item.similarity * 100)}%</span>}
      </div>
    </li>
  )
}
