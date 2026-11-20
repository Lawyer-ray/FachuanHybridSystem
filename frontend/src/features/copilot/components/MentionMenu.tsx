/**
 * `@` 引用候选浮层（受控组件：状态与键盘在 use-mention-menu / Composer）。
 *
 * a11y 照 deepseek-harness `ui-input-trigger/src/client/MenuView.tsx:132-134` 的
 * combobox 模式：
 * - `role="listbox"` 挂在**滚动容器**上（不是外层壳），`aria-activedescendant`
 *   也挂这里，指向高亮行的 id——焦点始终留在 textarea，菜单只是「活动的后代」；
 * - 行用 `onMouseDown` + `preventDefault()`，不是 `onClick`：click 之前焦点已经
 *   被按钮抢走，textarea 丢焦点会连带丢掉 selectionStart，选完引用光标就跳到末尾；
 * - `onMouseMove` 而不是 `onMouseEnter`：键盘翻页把行滚到静止的指针下面时，
 *   mouseenter 会把共享高亮抢回去，看起来像「键盘失灵」。
 *
 * 分组：按源（案件/合同/文书/文件夹）分组，prune 掉「已就绪但空」的组；组还在
 * 拉取时给一个骨架行，让「在搜」和「没有」可分辨。
 */

import { FileText, Folder, Scale, ScrollText } from 'lucide-react'
import type { ComponentType } from 'react'

import { mentionOptionId, type MentionCandidate } from '../domain'
import type { MentionGroup } from '../hooks/use-mention-menu'

export interface MentionMenuProps {
  /** listbox 的 DOM id（textarea 的 aria-controls 指向它） */
  id: string
  groups: MentionGroup[]
  highlight: { key: string; index: number } | null
  onHover: (key: string, index: number) => void
  onPick: (target: { key: string; index: number }) => void
}

/** 种类 → 图标（中性灰阶，无 emoji） */
const KIND_ICON: Record<string, ComponentType<{ className?: string }>> = {
  case: Scale,
  contract: FileText,
  document: ScrollText,
  folder: Folder,
}

function KindIcon({ candidate }: { candidate: MentionCandidate }) {
  const Icon = KIND_ICON[candidate.kind] ?? FileText
  return (
    <span className="mt-0.5 flex h-4 w-4 flex-none items-center justify-center text-muted-foreground">
      <Icon className="h-3.5 w-3.5" />
    </span>
  )
}

export function MentionMenu({ id, groups, highlight, onHover, onPick }: MentionMenuProps) {
  // 「已就绪且空」的组不占位：空标题行只会让人以为有东西没加载出来
  const visible = groups.filter((group) => group.status === 'pending' || group.items.length > 0)
  const activeId = highlight ? mentionOptionId(highlight.key, highlight.index) : undefined
  return (
    <div
      id={id}
      role="listbox"
      aria-label="引用候选"
      aria-activedescendant={activeId}
      className="absolute bottom-full left-0 right-0 mb-1.5 max-h-64 overflow-y-auto rounded-[10px] border border-border bg-popover py-1 shadow-md"
    >
      {visible.length === 0 && (
        <p className="px-2.5 py-2 text-[11.5px] text-muted-foreground">
          没有匹配的引用对象 · 打两个字搜案件/合同（文书与文件夹来自当前案件/合同绑定的目录）
        </p>
      )}
      {visible.map((group) => (
        <div key={group.key} role="group" aria-label={group.title}>
          <div role="presentation" className="px-2.5 pt-1 pb-0.5 text-[10.5px] font-[620] tracking-wide text-muted-foreground">
            {group.title}
          </div>
          {group.status === 'pending' && group.items.length === 0 ? (
            <div role="status" aria-label={`${group.title}加载中`} className="px-2.5 py-1.5 text-[11.5px] text-muted-foreground">
              搜索中…
            </div>
          ) : (
            group.items.map((item, index) => {
              const active = highlight?.key === group.key && highlight.index === index
              return (
                <button
                  key={`${group.key}-${item.kind}-${item.refId ?? 'x'}-${item.subpath ?? index}`}
                  id={mentionOptionId(group.key, index)}
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={`flex w-full items-start gap-2 px-2.5 py-1.5 text-left transition-colors hover:bg-secondary/60 ${active ? 'bg-secondary/60' : ''}`}
                  // mousedown 而不是 click：保住 textarea 的焦点与光标（combobox 模式）
                  onMouseDown={(event) => {
                    event.preventDefault()
                    onPick({ key: group.key, index })
                  }}
                  onMouseMove={active ? undefined : () => onHover(group.key, index)}
                >
                  <KindIcon candidate={item} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] text-foreground">{item.label}</span>
                    {item.sublabel ? (
                      <span className="block truncate text-[11px] text-muted-foreground">{item.sublabel}</span>
                    ) : null}
                  </span>
                </button>
              )
            })
          )}
        </div>
      ))}
    </div>
  )
}
