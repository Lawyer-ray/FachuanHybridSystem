import { useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { errMessage } from '@/lib/errors'

import { listProjectNotes, PROJECT_NOTES_PAGE_SIZE, type ProjectNote } from '../../api'
import { fmtCNDate } from '../../domain'
import { workbenchKeys } from '../../hooks/use-workbench-data'

import { ProjectNoteConfirmDialog } from './ProjectNoteConfirmDialog'

/**
 * 「AI 上下文」抽屉：把挂在本项目上的 AI 笔记读出来，并给「同事的判断」一条
 * 人工确认的入口。
 *
 * ## 为什么分「已确认的事实 / 同事的判断」两组，且事实在前
 *
 * 有没有人确认过，决定这条笔记能不能当依据：确认过的才是项目事实，没确认的只是
 * 某位同事（或 AI）当时的一句判断。混在一列里，律师会把后者当结论用——所以顺序
 * 固定、两组各自计数，并在组头写清「能当依据 / 只是线索」。
 *
 * ## 为什么只在这里开「确认」，其它写入口仍留在助手那侧
 *
 * 模型写的只是判断，必须人点一下才升为项目事实——这是整套记忆设计的闸门。律师
 * 恰恰是在这一屏看到某条判断「说得对」的，让他回助手重写一遍才能确认，等于把闸门
 * 关死。改写 / 删除 / 新增仍然只走助手：这里给半套写入口会让「谁改的」说不清。
 *
 * ## 为什么用 useInfiniteQuery 分页
 *
 * 后端一次只回 limit 条，静默截断会让律师以为「本项目就这些笔记」，而漏掉的正是
 * 同事的判断。分页状态交给 react-query（而不是组件里自己攒数组）：确认成功后
 * 只需 invalidate 同一个 key，它会把已加载的每一页依次重取，列表带着新分组刷新，
 * 本地累积则得手工决定「重取哪几页、旧页怎么和新页拼」。
 *
 * 请求只在打开时发（`enabled: open`）：项目详情页是律师停留最久的一页，不该为
 * 一个默认收起的抽屉背一条请求。
 */
export function ProjectMemoryDrawer({
  open,
  onOpenChange,
  contractId,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  /** 委托合同 id（`:id`）：笔记的项目锚点就是它 */
  contractId: number
}) {
  // 正在确认的那条（null = 弹窗关闭）。放在这里而不是行内：弹窗要跨行复用，
  // 且行组件只该负责「点了一下」。
  const [confirming, setConfirming] = useState<ProjectNote | null>(null)

  const query = useInfiniteQuery({
    queryKey: workbenchKeys.projectNotes(contractId),
    queryFn: ({ pageParam }) => listProjectNotes(contractId, { offset: pageParam }),
    initialPageParam: 0,
    // 返回条数 < limit 即末页：后端没有 total，多要一次空页比猜总数诚实
    getNextPageParam: (lastPage, _pages, lastOffset) =>
      lastPage.length < PROJECT_NOTES_PAGE_SIZE ? undefined : lastOffset + PROJECT_NOTES_PAGE_SIZE,
    enabled: open,
    staleTime: 30_000,
  })

  const notes = query.data?.pages.flat() ?? []
  // 被推翻的旧结论单独放最后：留在两列里会让律师看到两条互相矛盾的判断，
  // 而且没有任何提示。它们仍要可见——「当时怎么定的」本身是线索。
  const live = notes.filter((n) => !n.is_superseded)
  const facts = live.filter((n) => n.confirmed_at !== '')
  const judgments = live.filter((n) => n.confirmed_at === '')
  const superseded = notes.filter((n) => n.is_superseded)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="max-w-[min(520px,calc(100vw-1.75rem))]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 opacity-70" />
            AI 上下文
          </SheetTitle>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            这个项目上所有律师存的 AI 笔记，同团队可见。写入在 AI 助手回答下方的书签。
          </p>
        </SheetHeader>

        <SheetBody className="px-6 pt-4">
          {query.isPending ? (
            /* isPending 而不是 isLoading：enabled 从 false 翻 true 的那一帧还没发出请求，
               用 isLoading 会先闪一下「本项目还没有笔记」的空态 */
            <LoadingBlock size="sm" text="正在加载 AI 笔记…" className="justify-start py-6" />
          ) : notes.length === 0 && query.isError ? (
            /* 失败不能退化成空列表：律师会读成「本项目没有笔记」，把同事的判断当成不存在 */
            <ErrorBlock
              error={query.error}
              fallback="AI 笔记加载失败，请稍后重试"
              retryText="重试"
              onRetry={() => void query.refetch()}
              className="py-4 text-left"
            />
          ) : notes.length === 0 ? (
            <EmptyBlock className="items-start py-6 text-left leading-relaxed">
              本项目还没有 AI 笔记。在 AI 助手里点回答下方的书签，就能把结论存到这里，同团队可见。
            </EmptyBlock>
          ) : (
            <>
              {/* 确认入口只挂在「同事的判断」：上面那组已经确认过，下面那组已被推翻 */}
              <NoteGroup title="已确认的事实" hint="同团队确认过，可以当依据" notes={facts} />
              <NoteGroup
                title="同事的判断"
                hint="还没人确认，先当线索"
                notes={judgments}
                onConfirm={setConfirming}
              />
              <NoteGroup
                title="已被推翻"
                hint="仅作历史线索，不要当依据"
                notes={superseded}
                tone="muted"
              />
              <ProjectNotesPager
                loaded={notes.length}
                hasMore={query.hasNextPage}
                fetching={query.isFetchingNextPage}
                error={query.isFetchNextPageError ? query.error : null}
                onLoadMore={() => void query.fetchNextPage()}
              />
            </>
          )}
        </SheetBody>
      </SheetContent>

      <ProjectNoteConfirmDialog
        note={confirming}
        contractId={contractId}
        onClose={() => setConfirming(null)}
      />
    </Sheet>
  )
}

/**
 * 列表底部的分页脚：加载更多 / 加载更多失败可重试 / 末页计数。
 *
 * 加载更多失败**不清空已加载内容**——重试入口原地替换按钮，律师不会因为最后一页
 * 超时就连带丢掉前面看过的那几条。
 */
function ProjectNotesPager({
  loaded,
  hasMore,
  fetching,
  error,
  onLoadMore,
}: {
  loaded: number
  hasMore: boolean
  fetching: boolean
  /** 非空 = 上一次「加载更多」失败（首屏失败走的是整块 ErrorBlock，不会到这里） */
  error: unknown
  onLoadMore: () => void
}) {
  if (error) {
    return (
      <div role="alert" className="mb-4 flex items-center justify-between gap-3 rounded-[8px] bg-secondary px-2.5 py-2 text-[12px] text-destructive">
        <span>加载更多失败：{errMessage(error, '请稍后重试')}</span>
        <button type="button" className="flex-none underline underline-offset-2" onClick={onLoadMore}>
          重试
        </button>
      </div>
    )
  }
  if (hasMore) {
    return (
      <button
        type="button"
        disabled={fetching}
        onClick={onLoadMore}
        className="mb-4 w-full rounded-[8px] border border-border px-2.5 py-2 text-[12px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-60"
      >
        {fetching ? '加载中…' : '加载更多'}
      </button>
    )
  }
  return <p className="mb-4 py-1 text-center text-[11px] text-muted-foreground">已全部加载 {loaded} 条</p>
}

function NoteGroup({
  title,
  hint,
  notes,
  tone,
  onConfirm,
}: {
  title: string
  hint: string
  notes: ProjectNote[]
  tone?: 'muted'
  /** 只有「同事的判断」传：确认入口只给还没人确认过的现行判断 */
  onConfirm?: (note: ProjectNote) => void
}) {
  // 「已被推翻」空了就整组隐藏；上面两组空着也要留标题与 0——「没人确认过」
  // 本身就是律师要知道的信息，藏掉会让他以为这条已被确认。
  if (notes.length === 0 && tone === 'muted') return null
  return (
    <section className="mb-5" aria-label={title}>
      <h3 className={'text-[12px] font-[650] ' + (tone === 'muted' ? 'text-muted-foreground' : 'text-foreground')}>
        {title}
        <span className="ml-1.5 font-normal text-muted-foreground">{notes.length}</span>
      </h3>
      <p className="mt-0.5 mb-1.5 text-[11px] text-muted-foreground/80">{hint}</p>
      {notes.length > 0 && (
        <ul className="space-y-1">
          {notes.map((note) => (
            <NoteRow
              key={note.id}
              note={note}
              muted={tone === 'muted'}
              onConfirm={onConfirm ? () => onConfirm(note) : undefined}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

function NoteRow({
  note,
  muted,
  onConfirm,
}: {
  note: ProjectNote
  muted?: boolean
  /** 不给就不渲染「确认」：已确认 / 已推翻的行没有可确认的东西 */
  onConfirm?: () => void
}) {
  const confirmed = note.confirmed_at !== ''
  return (
    <li className="flex items-start gap-2 rounded-[8px] px-2 py-1.5">
      <span className="mt-0.5 flex-none rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
        {note.case_id != null ? '本案' : '项目'}
      </span>
      <div className="min-w-0 flex-1">
        <p className={'text-[13px] leading-relaxed break-words ' + (muted ? 'text-muted-foreground line-through decoration-border' : 'text-foreground')}>
          {note.content}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          {/* 确认人名字可能是空串（历史数据 / 确认人已不在职）：退回「已确认」，别渲染出半个「 确认」 */}
          {confirmed ? (note.confirmed_by ? `${note.confirmed_by} 确认` : '已确认') : fmtCNDate(note.created_at)}
        </p>
      </div>
      {onConfirm && (
        <button
          type="button"
          onClick={onConfirm}
          aria-label="确认这条判断为项目事实"
          title="确认后本项目的所有律师都会把它当已确认的事实使用"
          className="mt-0.5 flex-none rounded-[6px] border border-border px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          确认
        </button>
      )}
    </li>
  )
}
