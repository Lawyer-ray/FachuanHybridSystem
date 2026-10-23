/**
 * 业务详情页的嵌入式 AI 助手：长在页面右栏里的专属对话区，与全局浮层
 * CopilotPanel 共享同一 store——本委托的会话两处互通，嵌入区发消息、
 * 全局面板（⌘J）能接着看；反之亦然。
 *
 * 与浮层的分工：嵌入区天然绑定单一业务上下文（mount 时进入，不匹配才
 * 重进——从全局面板带着本委托会话过来时无缝延续，不打断当前对话），
 * 没有「业务范围 chip」「并排切换」这些浮层概念；会话列表用覆盖层，
 * 材料抽屉同款。unmount 不清 context：全局助手继续用当前范围（与
 * openCopilot 的既有语义一致）。
 *
 * 高度与宽度都归宿主：宿主容器决定尺寸（详情页工作区列是 sticky 满视口
 * 高、可拖宽的第三列），本组件 h-full 填充——为未来工作区内再分栏
 * （OnlyOffice 文档预览 | 对话）留空间。
 */

import { useEffect, useState } from 'react'
import { FolderTree, History, Plus } from 'lucide-react'

import { useCopilot } from '../store'
import type { CopilotLaunchContext } from '../launch'
import { useCopilotDrop } from '../hooks/use-copilot-drop'
import { Composer } from './Composer'
import { FolderTreeDrawer } from './FolderTreeDrawer'
import { MessageList } from './MessageList'
import { SessionSidebar } from './SessionSidebar'

export function CopilotEmbed({
  origin,
  refId,
  title,
}: {
  origin: CopilotLaunchContext['origin']
  refId: number
  title: string
}) {
  const enterContext = useCopilot((s) => s.enterContext)
  const switchSession = useCopilot((s) => s.switchSession)
  const [listOpen, setListOpen] = useState(false)
  const [treeDrawerOpen, setTreeDrawerOpen] = useState(false)
  const drop = useCopilotDrop()

  // 已在该业务范围内（如从全局面板延续过来）则不打断当前会话
  useEffect(() => {
    const ctx = useCopilot.getState().context
    if (!ctx || ctx.origin !== origin || ctx.refId !== refId) {
      void enterContext({ origin, refId, title })
    }
  }, [origin, refId, title, enterContext])

  const iconBtn =
    'flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground'

  return (
    <section
      className="relative flex h-full min-h-[440px] flex-col overflow-hidden rounded-[12px] border border-border bg-card shadow-sm"
      aria-label={`${title} AI 助手`}
      onDragEnter={drop.onDragEnter}
      onDragOver={drop.onDragOver}
      onDragLeave={drop.onDragLeave}
      onDrop={drop.onDrop}
    >
      <header className="flex h-10 flex-none items-center gap-1.5 border-b border-border px-2.5">
        <span className="min-w-0 flex-1 truncate px-0.5 text-[12.5px] font-semibold text-foreground" title={title}>
          本{origin === 'case' ? '案' : '委托'} AI 助手
        </span>
        <button
          type="button"
          className={iconBtn}
          onClick={() => setListOpen((v) => !v)}
          aria-label={listOpen ? '收起会话列表' : '查看本范围的会话列表'}
          aria-pressed={listOpen}
          title="历史会话（只看本范围）"
        >
          <History className="h-4 w-4" />
        </button>
        {origin === 'contract' && (
          <button
            type="button"
            className={iconBtn}
            onClick={() => setTreeDrawerOpen((v) => !v)}
            aria-label={treeDrawerOpen ? '收起合同材料目录' : '展开合同材料目录'}
            aria-pressed={treeDrawerOpen}
            title="合同绑定文件夹目录树：把文件拖到输入区即可引用"
          >
            <FolderTree className="h-4 w-4" />
          </button>
        )}
        <button
          type="button"
          className={iconBtn}
          onClick={() => {
            void switchSession(null)
            setListOpen(false)
          }}
          aria-label="开始新对话"
          title="新对话（自动归属本范围）"
        >
          <Plus className="h-4 w-4" strokeWidth={2.5} />
        </button>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {listOpen && <SessionSidebar variant="overlay" onClose={() => setListOpen(false)} />}
        <MessageList />
        {treeDrawerOpen && origin === 'contract' && (
          <FolderTreeDrawer contractId={refId} onClose={() => setTreeDrawerOpen(false)} />
        )}
      </div>
      <Composer />
    </section>
  )
}
