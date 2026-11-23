import { useMemo, useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'

import {
  diffSegments,
  disagreementKindLabel,
  engineLabel,
  suggestionsOf,
  variantFullTextOf,
  type EngineSuggestion,
} from '../../draft'
import type { EngineDisagreement, Inconsistency, Segment } from '../../types'
import { cn } from '@/lib/utils'

/**
 * 「本段的双引擎分歧」——内联在右栏正文之上，不分页签。
 *
 * ## 为什么融进「材料信息」而不是独立页签
 *
 * 四块内容（正文 / 分歧 / 字段便签 / 字段库）的作用域完全一致：都是**当前这一段**。
 * 分页签反而把「发现问题」和「修复问题」拆到了两个屏上——看到「同一处姓名两引擎读得不一样」
 * 想改正文，得切页签、找块、双击，而切完清单就没了，不知道对照哪边。
 *
 * ## 为什么放在正文**上方**
 *
 * 律师的心智顺序是「先知道哪里有问题，再读/改」。分歧是这个段的健康度摘要，
 * 属于「读之前该知道的事」；放在正文下面会被长 Markdown 推到屏幕外。
 *
 * ## 为什么默认只显示本段
 *
 * 全卷 332 条平铺会把侧栏撑爆，且绝大多数与当前段无关。这里按 `seg.refs`
 * 覆盖的页过滤；全卷入口仍保留在底部（「查看全部」）。
 *
 * ## 「采用」按钮与「裁决权在律师」
 *
 * 旧注释说「刻意不提供采纳某个引擎的按钮：按钮一按下去，错的那份就进了诉状引用」。
 * 那句话在**没法核对**时是对的。但现在旁边就是原件、有双框标注、有跳转——
 * 律师点「采用」之前必须自己看着原件判断。此时按钮的价值是**省掉手工比对与
 * 抄写**，不是替他决定。所以它必须与「跳到原页」并排出现，且默认不自动应用。
 */
export function EngineDisagreementsInline({
  seg,
  items,
  keys,
  checked = [],
  onJump,
  onToggleChecked,
  onAdopt,
  onEdit,
  inconsistencies = [],
  heading,
  /** 按页分块时不再按段过滤（调用方已按页取好）——默认仍按 seg.refs 过滤 */
  skipSegmentFilter = false,
}: {
  /** 当前段；null 时不渲染 */
  seg: Segment | null
  /** 全卷分歧（会按本段页范围过滤） */
  items: EngineDisagreement[]
  /** 与 `items` 一一对应的唯一键 */
  keys: string[]
  checked?: string[]
  onJump?: (pageNo: number, key: string) => void
  onToggleChecked?: (key: string, checked: boolean) => void
  /**
   * 「采用这一侧」：把该引擎识别出的这行文字写回正文对应块。
   *
   * `blockKey` 是页面块 key（`<segId>:<page>:<idx>`），与 `onEditBlock` 同一口径；
   * 该分歧没匹配到块时为 null，调用方应退回整段编辑。
   */
  onAdopt?: (pageNo: number, text: string, disagreeKey?: string) => void
  /** 「修改」：两侧都不对时进编辑态，预填主引擎文本作起点 */
  onEdit?: (pageNo: number, text: string, disagreeKey?: string) => void
  /** 全卷不一致统计：用于「更推荐改成什么」（只认 high 置信度） */
  inconsistencies?: Inconsistency[]
  /** 标题文案。按页挂载时传「P4 分歧」，否则用默认的「本段识别分歧」 */
  heading?: string
  skipSegmentFilter?: boolean
}) {
  const [open, setOpen] = useState(true)

  // 本段覆盖的页集合：refs 可能不连续（切出几页 / 删页后是 [1,3,7] 这种）
  const pageSet = useMemo(() => new Set((seg?.refs ?? []).map((r) => r.p)), [seg])

  const mine = useMemo(() => {
    if (!seg || (!skipSegmentFilter && pageSet.size === 0)) return []
    const out: { item: EngineDisagreement; key: string }[] = []
    items.forEach((d, i) => {
      const k = keys[i]
      if (k && (skipSegmentFilter || pageSet.has(d.page_no))) out.push({ item: d, key: k })
    })
    return out
  }, [items, keys, seg, pageSet, skipSegmentFilter])

  if (!seg || mine.length === 0) return null

  const unchecked = mine.filter(({ key }) => !checked.includes(key)).length

  return (
    <section data-engine-inline className="@container flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1 rounded-md px-1 py-1 text-left hover:bg-secondary"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 flex-none text-muted-foreground" aria-hidden />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 flex-none text-muted-foreground" aria-hidden />
        )}
        <AlertTriangle className="h-3.5 w-3.5 flex-none text-amber-600" aria-hidden />
        <span className="text-[12.5px] font-medium">{heading ?? '本段识别分歧'}</span>
        <span className="rounded-full bg-amber-100 px-1.5 text-[10.5px] leading-4 tabular-nums text-amber-800">
          {mine.length}
        </span>
        {unchecked > 0 && unchecked !== mine.length && (
          <span className="text-[11px] text-muted-foreground">（{unchecked} 处未核对）</span>
        )}
      </button>

      {open && (
        <div className="flex flex-col gap-2">
          {mine.map(({ item, key }) => (
            <InlineRow
              key={key}
              item={item}
              itemKey={key}
              checked={checked.includes(key)}
              onJump={onJump}
              onToggleChecked={onToggleChecked ? (v) => onToggleChecked(key, v) : undefined}
              onAdopt={onAdopt}
              onEdit={onEdit}
              inconsistencies={inconsistencies}
            />
          ))}
        </div>
      )}
    </section>
  )
}

/** 一条内联分歧：页码 + 两个引擎文本 + 采用 / 跳转 */
function InlineRow({
  item,
  itemKey,
  checked,
  onJump,
  onToggleChecked,
  onAdopt,
  onEdit,
  inconsistencies = [],
}: {
  item: EngineDisagreement
  itemKey: string
  checked: boolean
  onJump?: (pageNo: number, key: string) => void
  onToggleChecked?: (checked: boolean) => void
  /** 「采用」：确认这一侧对，**直接写入**（不再进编辑态，那语义太绕） */
  onAdopt?: (pageNo: number, text: string, disagreeKey?: string) => void
  /** 「修改」：两侧都不对时进编辑态，预填 TXT 作起点 */
  onEdit?: (pageNo: number, text: string, disagreeKey?: string) => void
  /** 全卷不一致统计：用来给「更推荐改成什么」的建议（只信 high） */
  inconsistencies?: Inconsistency[]
}) {
  // 「更推荐改成什么」：只认 high 置信度的全卷低频变体，没有就空着（不猜）
  const suggestions: Record<string, EngineSuggestion> = suggestionsOf(item, inconsistencies)
  // 哪些「侧」被展开了全文。键是 `${itemKey}:${engine}`——同一页多条分歧各自记，
  // 不会因为展开第 1 条而把第 2 条也撑开。
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set())
  const toggleExpanded = (k: string) =>
    setExpanded((cur) => {
      const next = new Set(cur)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })
  return (
    <div
      data-engine-inline-row
      data-checked={checked ? 'true' : undefined}
      // 双击整行 = 「带我去本体」：跳页 + 画双框 + 滚到框的位置。
      // 与「第N页」按钮的分工：单击那个按钮只是「先看看那页」，
      // 双击是「直接定位到出问题的地方」，两个粒度。
      onDoubleClick={() => onJump?.(item.page_no, itemKey)}
      title="双击定位到原页并画出两个引擎的框"
      className={cn(
        'cursor-pointer rounded-lg border px-2 py-1.5 transition-colors',
        checked ? 'border-zinc-200 bg-card opacity-50' : 'border-amber-200 bg-amber-50/40',
        'hover:border-amber-300',
      )}
    >
      <div className="flex items-baseline gap-1.5 text-[11.5px] leading-relaxed">
        {onToggleChecked && (
          <input
            type="checkbox"
            checked={checked}
            aria-label={`第 ${item.page_no} 页这条分歧已核对`}
            onChange={(e) => onToggleChecked(e.target.checked)}
            className="mt-[3px] flex-none accent-zinc-700"
          />
        )}
        <button
          type="button"
          disabled={!onJump}
          onClick={() => onJump?.(item.page_no, itemKey)}
          title="跳到这一页，同时画出两个引擎的框"
          className="flex-none rounded bg-card px-1 text-[11px] tabular-nums text-foreground hover:bg-secondary"
        >
          第{item.page_no}页
        </button>
        {item.anchor_hit && (
          <span className="flex-none rounded bg-red-50 px-1 text-[10px] leading-4 text-red-700">
            含身份证号/账号
          </span>
        )}
        <span className="flex-none text-[10px] leading-4 text-muted-foreground">
          {disagreementKindLabel(item.kind)}
        </span>
      </div>

      <dl className="mt-1 flex flex-col gap-0.5">
        {item.variants.map((v) => {
          // 用**全文**而不是摘要：摘要带省略号，既看不清（判断不了哪侧对），
          // 拿去和另一侧做 diff 也会在截断处伪造出差异。
          const text = variantFullTextOf(item, v.engine)
          const otherEngine = item.variants.find((x) => x.engine !== v.engine)?.engine
          const other = otherEngine ? variantFullTextOf(item, otherEngine) : ''
          const parts = diffSegments(text, other)
          // 长文本默认折叠：一页 6 条 × 300 字会把正文推到看不见
          const isLong = text.length > 160
          return (
            <div
              key={v.engine}
              // 窄栏（默认 128px）下「引擎名 + 文字 + 采用按钮」挤在一行会把正文压得只剩
              // 两三个字。用容器查询把布局一切为二：宽栏并排、窄栏上下叠。
              // 不用断点（@media）：宽度由用户拖拽决定，与视口宽不是一回事——
              // 用户完全可以在大屏上把右栏拖到最窄。
              className="flex flex-col gap-0.5 text-[11.5px] leading-relaxed @[220px]:flex-row @[220px]:items-start @[220px]:gap-1"
            >
              <dt className="flex-none break-words text-muted-foreground @[220px]:w-[64px]">{engineLabel(v.engine)}</dt>
              {/* break-words + min-w-0：长行必须自动换行，否则窄栏会把内容挤没 */}
              <dd
                className={cn(
                  'min-w-0 flex-1 break-words',
                  !text.trim() && 'text-muted-foreground',
                )}
              >
                {text.trim() ? (
                  <VariantBody
                    parts={parts}
                    collapsed={isLong && !expanded.has(`${itemKey}:${v.engine}`)}
                    onToggle={() => toggleExpanded(`${itemKey}:${v.engine}`)}
                    total={text.length}
                  />
                ) : (
                  '（无此行）'
                )}
              </dd>
              {onAdopt && text.trim() && (
                <button
                  type="button"
                  onClick={() => onAdopt(item.page_no, variantFullTextOf(item, v.engine), itemKey)}
                  title={`确认 ${engineLabel(v.engine)} 这版是对的，直接写入正文`}
                  className="flex-none self-start rounded bg-card px-1 text-[10.5px] text-secondary-foreground hover:bg-secondary @[220px]:self-auto"
                >
                  采用
                </button>
              )}
            </div>
          )
        })}

        {/* 推荐提示：只在高置信度命中全卷低频变体时出现。
            「低频写法出现 3 次 / 高频写法出现 73 次」——后者大概率才对。
            没有命中就整块不渲染，不给「可能」「疑似」这类含糊话。 */}
        {Object.keys(suggestions).length > 0 && (
          <div
            data-engine-suggestion
            className="mt-1 rounded bg-sky-50 px-1.5 py-1 text-[10.5px] leading-relaxed text-sky-900"
          >
            {Object.values(suggestions).map((sg) => (
              <div key={sg.variant} className="break-words">
                全卷里「{sg.canonical}」出现 {sg.canonicalCount} 次，「{sg.variant}」仅 {sg.variantCount} 次 ——
                建议改成「<b className="font-medium">{sg.canonical}</b>」
              </div>
            ))}
          </div>
        )}

        {/* 修改：两侧都不对时走这里。采用是「确认这侧对」，修改是「都不对，我来写」。 */}
        {onEdit && (
          <div className="mt-1 flex justify-end">
            <button
              type="button"
              onClick={() => onEdit(item.page_no, item.variants[0] ? variantFullTextOf(item, item.variants[0].engine) : '', itemKey)}
              title="两个引擎都不对：进编辑态，以主引擎文本为起点改"
              className="rounded bg-card px-1.5 text-[10.5px] text-secondary-foreground hover:bg-secondary"
            >
              ✎ 修改
            </button>
          </div>
        )}
      </dl>
    </div>
  )
}


/**
 * 一行的正文渲染：差异高亮 + 长文本折叠。
 *
 * ## 为什么要折叠
 *
 * 全文平均 200–300 字，一页 6 条分歧全部展开会把下面的正文推到看不见。
 * 但**不能直接截断**（那就是原来的问题）：截断后律师判断不了哪侧对。
 * 所以默认折叠、一键展开，折叠时也给字数，让人知道还有多少没看到。
 */
function VariantBody({
  parts,
  collapsed,
  onToggle,
  total,
}: {
  parts: { text: string; changed: boolean }[]
  collapsed: boolean
  onToggle: () => void
  total: number
}) {
  // 折叠时只渲染前 160 字：分段数取决于差异分布（全文一致时只有 1 段），
  // 不能拿段数判断「还有多少没看到」。
  const LIMIT = 160
  let acc = 0
  const shown: { text: string; changed: boolean }[] = []
  for (const seg of parts) {
    if (!collapsed) {
      shown.push(seg)
      continue
    }
    if (acc >= LIMIT) break
    const room = LIMIT - acc
    shown.push(seg.text.length <= room ? seg : { text: seg.text.slice(0, room), changed: seg.changed })
    acc += Math.min(seg.text.length, room)
  }
  const truncated = collapsed && total > LIMIT
  return (
    <>
      {shown.map((seg, si) =>
        seg.changed ? (
          <mark
            key={si}
            data-diff-changed
            className="rounded bg-amber-200/80 px-0.5 font-medium text-amber-950"
          >
            {seg.text}
          </mark>
        ) : (
          <span key={si}>{seg.text}</span>
        ),
      )}
      {collapsed && (
        <button
          type="button"
          onClick={onToggle}
          data-expand-fulltext
          className="ml-1 rounded bg-secondary px-1 text-[10px] text-secondary-foreground hover:bg-zinc-200"
        >
          {truncated ? `展开全文（${total} 字）` : '展开'}
        </button>
      )}
      {!collapsed && (
        <button
          type="button"
          onClick={onToggle}
          data-collapse-fulltext
          className="ml-1 rounded bg-secondary px-1 text-[10px] text-secondary-foreground hover:bg-zinc-200"
        >
          收起
        </button>
      )}
    </>
  )
}
