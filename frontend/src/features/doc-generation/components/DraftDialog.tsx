import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2, Sparkles } from 'lucide-react'
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

import { DOC_TYPES_KEY, draftByType, listDocTypes } from '../api'
import type { DraftResult } from '../types'
import { PendingList } from './PendingList'

/**
 * 「一句话生成文书」：选类型（+ 可选一句补充说明）→ 后端按骨架模板填槽 →
 * 成稿落进目标文件夹 → 交给页面用现有画布打开。
 *
 * **为什么类型必须是下拉**：每个类型对应后端一条 `DocumentSpec`（骨架模板 +
 * 槽位 + 落位目录）。让律师打一段自然语言去「猜类型」，等于把模板选择权交给
 * 模型——生成出来的结构不可复现，也没法核对到底填了哪些槽。
 *
 * **为什么失败不关弹窗**：失败原因是后端原文（如「案件 399 没有匹配的文件夹
 * 模板」），那是律师唯一能看懂、也唯一能自己去修的信息（补模板 / 换案件）。
 * 关掉弹窗只留一条转瞬即逝的 toast，等于把可行动的信息丢掉。
 *
 * **为什么未决项放进 toast 的 description**：成功即关弹窗（律师下一步要看的
 * 是文档，不是表单），未决槽名只能在关窗后的提示里继续可读、可复制。
 */
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
  const [docType, setDocType] = useState('')
  const [instruction, setInstruction] = useState('')
  /** 失败原因原文（null = 没有失败） */
  const [failure, setFailure] = useState<string | null>(null)

  // 只在弹窗打开时拉类型清单：详情页不该为「可能点一下」先付一次请求
  const types = useQuery({ queryKey: DOC_TYPES_KEY, queryFn: listDocTypes, enabled: open, staleTime: 5 * 60_000 })

  /** 关窗顺手清失败态：下一次打开不该看到上一次的红字 */
  const close = (next: boolean) => {
    if (!next) setFailure(null)
    onOpenChange(next)
  }

  const draft = useMutation({
    mutationFn: async (): Promise<DraftResult> => {
      const res = await draftByType({
        doc_type: docType,
        case_id: caseId ?? undefined,
        facts: {},
        // 起草完顺手排一轮审查，成稿才有人逐条看过；与既有 /draft 端点同一默认。
        // 只在 api 层透传，不在 UI 暴露开关：律师此刻要的是「生成」，不是调参。
        auto_review: true,
        instruction: instruction.trim(),
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
  const canSubmit = docType !== '' && !pending

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>生成文书</DialogTitle>
          <DialogDescription>
            选一个文书类型，按律所已验证的骨架模板填槽，成稿直接落进本案文件夹。
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
            {pending ? '正在生成…' : '生成'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
