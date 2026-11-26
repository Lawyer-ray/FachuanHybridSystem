import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2, ShieldCheck, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import { DOC_TYPES_KEY, assessDraftReadiness, draftByType, listDocTypes } from '../api'
import type { DraftAssessResult, DraftResult } from '../types'
import { PendingList } from './PendingList'
import { ReadinessPanel } from './ReadinessPanel'

/**
 * 「一句话生成文书」：先看材料够不够，再决定要不要此刻出稿。
 *
 * **为什么默认停在「看缺口」**：材料明显不全时，先告诉律师缺什么比先产出一份要重签的
 * 文书有用——一份缺被告身份的起诉状，律师一个字都用不了，却要花掉一次起草调用。
 *
 * **为什么类型必须是下拉**：每个类型对应后端一条 `DocumentSpec`（骨架模板 +
 * 槽位 + 落位目录）。让律师打一段自然语言去「猜类型」，等于把模板选择权交给
 * 模型——生成出来的结构不可复现，也没法核对到底填了哪些槽。
 *
 * **为什么 blocked 时主按钮换个说法而不是禁用**：「能不能出」是判断，不是禁令。
 * 材料确实缺、但律师有时就是要先拿一份带批注的草稿去和委托人对稿——那时缺口会写成
 * `<待填写：x>` 并挂批注，所以按钮直说这件事，并用 `force=true` 越过后端闸门。
 *
 * **为什么失败不关弹窗**：失败原因是后端原文（如「案件 399 没有匹配的文件夹
 * 模板」），那是律师唯一能看懂、也唯一能自己去修的信息（补模板 / 换案件）。
 * 关掉弹窗只留一条转瞬即逝的 toast，等于把可行动的信息丢掉。
 *
 * **为什么未决项放进 toast 的 description**：成功即关弹窗（律师下一步要看的
 * 是文档，不是表单），未决槽名只能在关窗后的提示里继续可读、可复制。
 */
/** 批注署名的默认值。**不放系统配置**：署名是「这份文书上写什么名字」，随本次起草走。 */
export const DEFAULT_COMMENT_AUTHOR = 'Lawyer'

/** 两个视图：看缺口（默认，判断材料够不够）/ 生成文书（选项与补充说明） */
type DraftDialogView = 'readiness' | 'draft'

export function DraftDialog({
  open,
  onOpenChange,
  caseId,
  onCreated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  /** 成稿落到哪个案件（P0 只接案件文书；合同侧参数位在 api 层保留） */
  caseId?: number | null
  /** 成功回调：页面拿 subpath 走现有文件夹画布打开成稿 */
  onCreated?: (fileUrl: string, subpath: string) => void
}) {
  const [view, setView] = useState<DraftDialogView>('readiness')
  const [docType, setDocType] = useState('')
  const [instruction, setInstruction] = useState('')
  /** 批注署名：律师在 Word/OnlyOffice 审阅面板里看到的「人」。默认 Lawyer。 */
  const [commentAuthor, setCommentAuthor] = useState(DEFAULT_COMMENT_AUTHOR)
  /** 失败原因原文（null = 没有失败） */
  const [failure, setFailure] = useState<string | null>(null)
  /** 最近一次判断结果（null = 还没判断 / 正在重判 / 判断失败） */
  const [readiness, setReadiness] = useState<DraftAssessResult | null>(null)

  // 只在弹窗打开时拉类型清单：详情页不该为「可能点一下」先付一次请求
  const types = useQuery({ queryKey: DOC_TYPES_KEY, queryFn: listDocTypes, enabled: open, staleTime: 5 * 60_000 })

  /**
   * 立案前判断：**手动触发**（律师自己决定要不要花这 20~40 秒），不随弹窗打开自动跑——
   * 详情页里点开弹窗又关掉的人不该产生一次模型调用。
   */
  const assess = useMutation({
    mutationFn: () => assessDraftReadiness({ case_id: caseId ?? undefined, instruction: instruction.trim() }),
    // 重判期间把上一次结论清掉：旧结论挂在新一轮加载旁边，等于给了个过期答案
    onMutate: () => setReadiness(null),
    onSuccess: (res) => setReadiness(res),
    onError: () => setReadiness(null),
  })

  /** 关窗顺手清失败态与判断结果：下一次打开不该看到上一次的红字和过期结论 */
  const close = (next: boolean) => {
    if (!next) {
      setFailure(null)
      setReadiness(null)
      setView('readiness')
      assess.reset()
    }
    onOpenChange(next)
  }

  /** 判断说「出不了」时，主按钮仍可强出，但必须让律师知道代价是成稿留空 + 批注 */
  const blocked = readiness?.verdict === 'blocked'
  const assessFailed = assess.isError

  const draft = useMutation({
    mutationFn: async (): Promise<DraftResult> => {
      // 不传 `assess_first=false`：后端那轮判断是**权威闸门**，前端这份可能已经过期
      // （律师刚补了材料），也可能压根没看过缺口就点了生成。多一轮模型调用，
      // 换的是「绝不会在没判断过材料的情况下静默放行」。
      const res = await draftByType({
        doc_type: docType,
        case_id: caseId ?? undefined,
        facts: {},
        // 起草完顺手排一轮审查，成稿才有人逐条看过；与既有 /draft 端点同一默认。
        // 只在 api 层透传，不在 UI 暴露开关：律师此刻要的是「生成」，不是调参。
        auto_review: true,
        instruction: instruction.trim(),
        comment_author: commentAuthor.trim(),
        // 只有判断明确说 blocked 且律师仍然点了生成时才强出；其余一律让后端闸门照常判
        force: blocked,
      })
      // 业务失败是 HTTP 200 + created=false：不在这里抛，弹窗就只剩空白
      if (!res.created) throw new Error(res.reason || '生成失败（后端未给出原因）')
      return res
    },
    onMutate: () => setFailure(null),
    onSuccess: (res) => {
      const pct = Math.round(res.slot_fill_rate * 100)
      toast.success(`已生成《${res.name}》，填充率 ${pct}%`, {
        description: res.warnings.length > 0 ? res.warnings.join('；') : undefined,
        duration: res.warnings.length > 0 ? 10_000 : 4000,
      })
      if (res.pending.length > 0) {
        toast.warning(`有 ${res.pending.length} 项未决，成稿里是空的`, {
          description: <PendingList pending={res.pending} />,
          // 未决清单要比普通成功提示多留一会儿：律师要照着槽名去补写
          duration: 20_000,
        })
      }
      // 只清「这一次的补充说明」：类型留着（律师常连着给几个案子出同一类文书），
      // 旧说明留着才会误导——它是针对上一份成稿写的
      setInstruction('')
      close(false)
      onCreated?.(res.file_url, res.subpath)
    },
    onError: (e) => setFailure(errMessage(e, '生成失败，请稍后重试')),
  })

  const pending = draft.isPending
  const hasDocType = docType !== ''
  const canSubmit = hasDocType && !pending

  // 「判断失败」也要能出稿，只是把按钮话说清楚：直接生成，不再等判断
  const submitLabel = pending
    ? '正在生成…'
    : blocked
      ? '仍然生成草稿（留空处会挂批注）'
      : assessFailed
        ? '直接生成'
        : '生成'

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>生成文书</DialogTitle>
          <DialogDescription>
            选一个文书类型，先判断材料够不够，再按律所已验证的骨架模板填槽；成稿直接落进本案文件夹。
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 pt-1">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium">文书类型</span>
            <select
              data-testid="draft-doc-type"
              value={docType}
              disabled={pending || types.isPending}
              onChange={(e) => setDocType(e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2.5 text-[13px] text-foreground outline-none focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">{types.isPending ? '正在加载文书类型…' : '请选择文书类型'}</option>
              {(types.data ?? []).map((t) => (
                <option key={t.doc_type} value={t.doc_type}>
                  {t.display_name}
                </option>
              ))}
            </select>
          </label>

          {types.error != null && (
            <p className="text-[12px] text-destructive">
              文书类型没拉到：{errMessage(types.error, '接口异常，请稍后重试')}
            </p>
          )}

          <div className="flex gap-1 rounded-[8px] bg-secondary p-1" role="group" aria-label="起草弹窗视图">
            {(
              [
                ['readiness', '看缺口'],
                ['draft', '生成文书'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={view === key}
                onClick={() => setView(key)}
                className={cn(
                  'flex-1 rounded-[6px] px-2 py-1 text-[12px] font-medium transition-colors',
                  view === key
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {view === 'readiness' ? (
            <div className="flex flex-col gap-2.5">
              {assess.isPending ? (
                <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  正在把材料逐条对到要件上，通常 20~40 秒。
                </p>
              ) : readiness ? (
                <>
                  <ReadinessPanel result={readiness} />
                  <div>
                    <Button variant="outline" size="sm" disabled={!hasDocType} onClick={() => assess.mutate()}>
                      重新判断
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-[12px] leading-[1.7] text-muted-foreground">
                    先判断本案材料够不够支撑这份文书：只读，不动任何文件。缺口按「必须补 / 影响金额 /
                    影响胜诉」列出来，可以直接复制给委托人或助理。
                  </p>
                  <div>
                    <Button
                      variant="outline"
                      size="sm"
                      data-testid="draft-assess"
                      disabled={!hasDocType}
                      onClick={() => assess.mutate()}
                    >
                      <ShieldCheck className="size-3.5" />
                      先看材料够不够
                    </Button>
                  </div>
                  {!hasDocType && (
                    <p className="text-[11.5px] text-muted-foreground">先选文书类型，再判断材料够不够。</p>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium">批注署名</span>
                <input
                  data-testid="draft-comment-author"
                  value={commentAuthor}
                  disabled={pending}
                  onChange={(e) => setCommentAuthor(e.target.value)}
                  placeholder={DEFAULT_COMMENT_AUTHOR}
                  className="h-9 w-full rounded-md border border-border bg-background px-2.5 text-[13px] text-foreground outline-none focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-60"
                />
                <span className="text-[11.5px] leading-[1.6] text-muted-foreground">
                  生成后，正文里没填上的位置会挂批注；这里填的名字就是律师在「审阅」面板里看到的人。
                </span>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium">补充说明（可选）</span>
                <Textarea
                  data-testid="draft-instruction"
                  value={instruction}
                  disabled={pending}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="例：被告主张合同无效，管辖条款写「约定不明」。"
                  className="min-h-[72px] text-[13px]"
                />
              </label>
            </div>
          )}

          {/* 判断失败与视图无关：错误行常驻，否则切到「生成文书」后按钮凭空变成「直接生成」 */}
          {assessFailed && (
            <p className="text-[12px] leading-[1.7] text-destructive" data-testid="draft-assess-failure">
              材料判断没跑成功：{errMessage(assess.error, '接口异常，请稍后重试')}。这不影响起草，可以直接生成。
            </p>
          )}

          {pending && (
            <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              正在按模板填槽并落盘，通常 30 秒到 2 分钟，先别关窗口。
            </p>
          )}

          {failure != null && (
            <div className="rounded-[8px] border border-destructive/40 bg-destructive/5 px-3 py-2 text-[12.5px] leading-[1.7]">
              <b className="font-[620]">没有生成成功</b>
              <p className="mt-1 break-words text-destructive" data-testid="draft-failure">
                {failure}
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)} disabled={pending}>
            取消
          </Button>
          <Button onClick={() => draft.mutate()} disabled={!canSubmit}>
            {pending ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
