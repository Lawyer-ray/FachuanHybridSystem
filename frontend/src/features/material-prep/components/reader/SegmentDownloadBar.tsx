import { FileDown, Loader2, PackageOpen } from 'lucide-react'

import { ContextMenuItem } from '@/components/ui/context-menu'
import type { SegmentDownloads, SegmentFileKind, SegmentRowDownload } from './use-segment-downloads'

/**
 * 「下载已转好的产物」的 UI：列表头工具条 + 段行里的勾选框与 PDF/MD 按钮。
 *
 * 产品口径（用户原话）：「打包下载已经转好的 Markdown 以及分好段的 pdf，可以
 * 单个下载、多选下载，也可以一起整包下载」——三档对应下面三个入口：
 *   · 单个 → 行右键菜单「下载 PDF / 下载 Markdown」（`/segments/{id}/pdf|md`）
 *   · 多选 → 工具条「下载选中（N）」（`/download?ids=12,15`）
 *   · 整包 → 工具条「整包下载」（`/download`，每段 pdf+md 打成 zip）
 *
 * 「单个」为什么不在行尾常驻两个按钮：段行里最贵的是段名宽度（见 RailSegRow 的
 * 宽度预算），而只要 PDF 不要 MD 是低频需求。真要一段的产物，勾上它 → 「下载选中（1）」
 * 只需两下；右键菜单只是给细粒度需求留的门。
 *
 * 状态与换票逻辑全在 `use-segment-downloads.ts` / `use-segment-selection.ts`：工具条和段行必须是**同一份**
 * 选中/置忙状态，两处各自 useState 迟早不同步。本文件只管长相。
 *
 * 落点为什么是左栏（Rail）：段列表本来就在那儿——律师在这里认段、改名、调序，
 * 下载也必须能在同一处「哪一段」上做；跳到中栏正文区下载会丢掉「按段挑」这个
 * 前提（中栏一次只显示一段，勾不出多选）。
 */

/** 工具条按钮样式：左栏只有 232~268px 宽，放不下 PBTN 的 30px 高 + 13px 内边距 */
const BAR_BTN =
  'flex h-[24px] flex-none items-center gap-1 rounded-[6px] border border-border bg-card px-1.5 text-[11.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'

export function SegmentDownloadBar({ dl, total }: { dl: SegmentDownloads; total?: number }) {
  const { segments, sel } = dl
  // 没有任何可下载段（还没跑完分段 / 段是人工拆的 / 旧草稿没产物）→ **整块不渲染**。
  // 不是把按钮置灰：一排永远点不动的灰按钮只会让人以为下载功能坏了，而这里真实
  // 情况是「后端还没有这一段的产物」，那就一个入口都不给。
  if (segments.length === 0) return null
  const jobs = new Set(segments.map((seg) => seg.jobId)).size
  const busy = dl.busy !== null
  // 只有「左栏的段多于可下载段」时才解释差额（人工拆的段没有后端产物）。
  // 绝大多数包里两者相等，此时再说「共 40 段可下载」等于把「40 份」重复一遍。
  const partial = typeof total === 'number' && total > segments.length

  return (
    // 一行放得下就一行：左栏只有 232~268px 宽，两行按钮组白吃掉约 28px 高度，
    // 而这一段列表有几十行。放不下时 flex-wrap 自然折到第二行，
    // 而不是把「整包下载」挤成两行字。
    <div
      data-segment-download-bar
      className="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-lg border border-border bg-secondary/40 px-2 py-1"
    >
      <label
        className="flex min-w-0 flex-none cursor-pointer items-center gap-1 text-[11.5px] text-muted-foreground"
        title={sel.allSelected ? '取消全选' : `全选这 ${segments.length} 段，勾中后可批量下载`}
      >
        {/* 半选态（勾了一部分）只能走 DOM 的 indeterminate：HTML 没有对应属性，
            而 checked 又是受控的（React 置回来），所以每次 render 用 ref 补一次 */}
        <input
          type="checkbox"
          aria-label="全选"
          checked={sel.allSelected}
          ref={(el) => {
            if (el) el.indeterminate = sel.indeterminate
          }}
          onChange={() => (sel.allSelected ? sel.clear() : sel.selectAll())}
          className="h-3.5 w-3.5 cursor-pointer accent-foreground"
        />
        全选
      </label>
      {(sel.count > 0 || partial) && (
        <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">
          {sel.count > 0
            ? `已选 ${sel.count}/${segments.length}`
            : `可下载 ${segments.length}/${total} 段`}
        </span>
      )}

      <div className="ml-auto flex flex-none items-center gap-1.5">
        {/* 没有选中就**不渲染**这个按钮：`下载选中（0）` 是个空入口，点下去后端
            会退回整包，等于悄悄替用户改了意图。空态的说明放在上面「全选」的 title 上。 */}
        {sel.count > 0 && (
          <button
            type="button"
            disabled={busy}
            onClick={dl.downloadSelected}
            title={`把勾中的 ${sel.count} 段打包下载（zip，每段含 PDF + Markdown）`}
            className={BAR_BTN}
          >
            {dl.busy?.startsWith('sel:') ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <PackageOpen className="h-3.5 w-3.5" aria-hidden />
            )}
            下载选中（{sel.count}）
          </button>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={dl.downloadAll}
          title={
            jobs > 1
              ? `本包有 ${jobs} 个识别任务，将依次下载 ${jobs} 个 zip（每个任务一个）`
              : '把这次拆分的全部段打包成 zip（每段含 PDF + Markdown）'
          }
          className={BAR_BTN}
        >
          {dl.busy?.startsWith('zip:') ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <FileDown className="h-3.5 w-3.5" aria-hidden />
          )}
          整包下载
        </button>
      </div>
    </div>
  )
}

/** 段行开头的勾选框；`row` 为 undefined（本段没有后端产物）时整块不渲染 */
export function SegmentSelectBox({ row, name }: { row: SegmentRowDownload | undefined; name: string }) {
  if (!row) return null
  return (
    <input
      type="checkbox"
      aria-label={`选择 ${name}`}
      checked={row.checked}
      draggable={false}
      // 行本身是复合交互（点=跳转、双击=改名、可拖拽）。不拦这些事件的话，
      // 勾一下会顺带跳到别的段、双击勾选框会弹出改名输入框、按住拖动会拖走整行。
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      onChange={row.onToggle}
      className="h-3.5 w-3.5 flex-none cursor-pointer accent-foreground"
    />
  )
}

/**
 * 段行右键菜单里的两个单文件下载项。
 *
 * 放在菜单而不是行尾：一行里最值钱的是段名宽度，而「只要这一段，只要 PDF」
 * 是低频细分需求。勾行 + 「下载选中（1）」已经覆盖了「只要这一段」，
 * 菜单只多给一个「不打包、只要单一文件」的门。
 */
export function SegmentDownloadMenuItems({ row }: { row: SegmentRowDownload | undefined }) {
  if (!row) return null
  const item = (kind: SegmentFileKind, label: string) => (
    <ContextMenuItem key={kind} disabled={row.disabled} onSelect={() => row.onDownload(kind)}>
      {/* 置忙时换成转圈：文字不变，屏幕阅读器与测试都不受影响 */}
      {row.busyKind === kind ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
      {label}
    </ContextMenuItem>
  )
  return (
    <>
      {item('pdf', '下载 PDF')}
      {item('md', '下载 Markdown')}
    </>
  )
}
