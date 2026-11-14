import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

import { docTodosOf, type DocTodo } from '../../draft/quality'
import type { PageQuality } from '../../types'

/**
 * 全卷「证件页待补录」清单（右侧抽屉）。
 *
 * ## 为什么这是最有价值的那张清单
 *
 * 图纸页看不出内容，律师翻一眼原图就过去了。证件页不一样：**姓名、身份证号、住址
 * 就在那儿，只是没读出来**，而它们恰恰是律师必须一个字一个字抄进卷宗的东西。
 * 逐页翻 164 页去找「哪张身份证没读出身份证号」是不可能完成的任务，所以给一张
 * 按「缺几个字段」排好序的清单：
 *
 * ```
 * P23  身份证      缺：姓名、身份证号、住址    [查看原页]
 * P42  身份证      缺：—（建议整页核对）      [查看原页]
 * P144 不动产权证   缺：权证号                [查看原页]
 * ```
 *
 * 打开就知道该翻哪几页、该抄什么——这比任何「识别质量」百分比都实用。
 *
 * ## 排序与配色
 *
 * 缺得多在前（3 个字段全没读出的身份证比只缺一个编号的不动产权证更急），
 * 同级按页号。整块不上彩色语义：`缺：…` 本身已经是足够强的信号，
 * 再染一层红只会让 20 条清单变成一堵红墙。
 *
 * `缺：—（建议整页核对）` 不是空行：`missing` 为空数组意味着后端认得出类型、
 * 预期字段也都命中，但整页内容可疑（满是乱码 / 拍糊）。那一页仍然要翻，只是
 * 说不出缺哪个字段——所以照样列出、照样能跳，而不是从清单里消失。
 *
 * ## 数据缺失
 *
 * 旧任务没有 `page_quality.doc_missing`，清单为空。入口在左栏就不渲染（不给一个
 * 点开是空的假入口）；真被打开时也明确说「没有记录」，而不是白屏。
 */
export function DocTodoDrawer({
  open,
  onOpenChange,
  pageQuality,
  onGotoPage,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 页级质量统计（`summary.page_quality`，旧任务为 null） */
  pageQuality: PageQuality | null
  /** 点「查看原页」跳过去；不传则只展示不可点 */
  onGotoPage?: (p: number) => void
}) {
  const todos = docTodosOf(pageQuality)
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-doc-todo-drawer aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>证件页待补录</SheetTitle>
          <SheetDescription>
            {todos.length > 0
              ? `全卷 ${todos.length} 页证件材料有字段没读出来，按缺失字段数量排序`
              : '没有发现需要补录的证件页'}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="px-6">
          {todos.length === 0 ? (
            <p className="py-6 text-[12px] leading-relaxed text-muted-foreground">
              这份材料包没有证件页缺字段的记录。旧任务的识别结果里没有这项统计，属正常。
            </p>
          ) : (
            <ul className="flex flex-col gap-2 py-2">
              {todos.map((t) => (
                <DocTodoRow key={t.page} item={t} onGotoPage={onGotoPage} />
              ))}
            </ul>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}

/** 一条待补录：页号 + 证件类型 + 缺什么 + 查看原页 */
function DocTodoRow({ item, onGotoPage }: { item: DocTodo; onGotoPage?: (p: number) => void }) {
  // 字段名用顿号分隔（「缺：姓名、身份证号、住址」），这里不是提示条那句式，
  // 不与字段名内部的「/」混用。
  // 没有字段列表不代表可以放过这一页（后端用它表示「字段都在但整页可疑」），
  // 所以给一句兜底而不是把行隐掉。
  const detail = item.missing.length > 0 ? `缺：${item.missing.join('、')}` : '缺：—（建议整页核对）'

  return (
    <li data-doc-todo className="rounded-lg border border-zinc-200 bg-card px-2.5 py-2">
      <div className="flex items-baseline gap-1.5 text-[12.5px] leading-relaxed">
        <span className="flex-none font-medium tabular-nums text-foreground">P{item.page}</span>
        <span className="flex-none text-muted-foreground">{item.label}</span>
        <span className="min-w-0 flex-1 text-muted-foreground">{detail}</span>
        {onGotoPage && (
          <button
            type="button"
            onClick={() => onGotoPage(item.page)}
            className="flex-none cursor-pointer text-[11px] text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            查看原页
          </button>
        )}
      </div>
    </li>
  )
}
