import { useQuery } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'

import { listProjectNotes, type ProjectNote } from '../../api'
import { fmtCNDate } from '../../domain'
import { workbenchKeys } from '../../hooks/use-workbench-data'

/**
 * 「AI 上下文」抽屉：把挂在本项目上的 AI 笔记读出来（只读）。
 *
 * ## 为什么分「已确认的事实 / 同事的判断」两组，且事实在前
 *
 * 有没有人确认过，决定这条笔记能不能当依据：确认过的才是项目事实，没确认的只是
 * 某位同事（或 AI）当时的一句判断。混在一列里，律师会把后者当结论用——所以顺序
 * 固定、两组各自计数，并在组头写清「能当依据 / 只是线索」。
 *
 * ## 为什么没有编辑 / 删除 / 确认按钮
 *
 * 本期只开读。确认要落确认人（后端 `NoteConfirmIn` 写 `confirmed_by`），改写笔记
 * 等于换一条结论，都属于助手那侧的写流程；这里给半套写入口只会让「谁改的」说不清。
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
  const query = useQuery({
    queryKey: workbenchKeys.projectNotes(contractId),
    queryFn: () => listProjectNotes(contractId),
    enabled: open,
    staleTime: 30_000,
  })

  const notes = query.data ?? []
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
          {query.isLoading ? (
            <LoadingBlock size="sm" text="正在加载 AI 笔记…" className="justify-start py-6" />
          ) : query.isError ? (
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
              <NoteGroup title="已确认的事实" hint="同团队确认过，可以当依据" notes={facts} />
              <NoteGroup title="同事的判断" hint="还没人确认，先当线索" notes={judgments} />
              <NoteGroup
                title="已被推翻"
                hint="仅作历史线索，不要当依据"
                notes={superseded}
                tone="muted"
              />
            </>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}

function NoteGroup({
  title,
  hint,
  notes,
  tone,
}: {
  title: string
  hint: string
  notes: ProjectNote[]
  tone?: 'muted'
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
            <NoteRow key={note.id} note={note} muted={tone === 'muted'} />
          ))}
        </ul>
      )}
    </section>
  )
}

function NoteRow({ note, muted }: { note: ProjectNote; muted?: boolean }) {
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
    </li>
  )
}
