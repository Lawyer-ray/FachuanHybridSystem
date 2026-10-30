import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { FileStack, Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { bankLitigation, materialPrep, projectDetail } from '@/app/paths'
import { createApiClient } from '@/lib/api'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

import { PROJECT_TEMPLATES, createFromTemplate, fetchSampleFile, type ProjectTemplate } from '../templates'

/**
 * 新建项目对话框。
 *
 * ═══ 为什么需要它 ═══
 * 之前 navbar 上的「+ 新建项目」只弹一句 toast（「可先把材料上传到材料预处理归案」）——
 * 那等于告诉用户「这里做不了」。现在把它补成真对话框：
 *   ① 空白项目：填名字 → 建合同+案件
 *   ② 从示例开始：选模板 → 字段自动填好 → 可选「同时放入示例材料」
 *
 * ═══ 「从示例开始」是什么 ═══
 * 不是「演示模式」，而是**模板**：建出来的是普通项目，名字不带任何特殊标记，
 * 后续照常编辑删除。模板只是把新建表单的字段预先填好（当事人、法院、金额），
 * 再提供一份示例材料包 —— 用户点「下一步」后，那份材料就和真实上传一样进收件箱。
 *
 * 真实产品都有这类入口（合同模板、案件模板），律师也确实常用。
 */
export function NewProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [tpl, setTpl] = useState<ProjectTemplate | null>(null)
  const [withSample, setWithSample] = useState(true)
  const [busy, setBusy] = useState(false)

  const canSubmit = name.trim().length > 0 && !busy

  async function submit() {
    if (!canSubmit) return
    setBusy(true)
    try {
      const me = await currentLawyerId()
      const caseApi = createApiClient({ prefix: '/api/v1/cases' })
      const contractApi = createApiClient({ prefix: '/api/v1/contracts' })
      const clientApi = createApiClient({ prefix: '/api/v1/client' })

      let caseId: number
      // 合同 id 与案件 id 是两套独立自增的主键，跳转时必须用对的那个：
      // `/projects/:id` 要合同 id。这里显式记下来，不在跳转处猜。
      let contractId: number | null = null
      if (tpl) {
        const r = await createFromTemplate(tpl, {
          projectName: name.trim(),
          lawyerId: me,
          caseApi,
          contractApi,
          clientApi,
        })
        caseId = r.caseId
        contractId = r.contractId
      } else {
        // 空白项目：只建合同+案件，别的等用户自己填
        const r = await contractApi
          .post('contracts/full', {
            json: {
              name: name.trim(),
              case_type: 'civil',
              status: 'active',
              start_date: new Date().toISOString().slice(0, 10),
              lawyer_ids: [me],
              fee_mode: 'FIXED',
              fixed_amount: 5000,
              cases: [
                {
                  name: `${name.trim()}·案件`,
                  case_type: 'civil',
                  status: 'active',
                  current_stage: 'first_trial',
                  cause_of_action: '',
                },
              ],
            },
          })
          .json<{ id?: number }>()
        contractId = r?.id != null ? Number(r.id) : null
        const list = await caseApi.get('cases').json<{ id?: number; name?: string; contract_id?: number }[]>()
        const hit = list.find((c) => c.contract_id === r?.id)
        if (hit?.id == null) throw new Error('建项目失败：建完案件后查不到')
        caseId = Number(hit.id)
      }

      await qc.invalidateQueries({ queryKey: ['cases'] })

      // 同时放入示例材料：与真实上传走同一条路径（进收件箱 → 待处理）
      if (tpl && withSample) {
        toast.loading('正在放入示例材料…', { id: 'newproj' })
        const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })
        const file = await fetchSampleFile(tpl)
        const fd = new FormData()
        fd.append('files', file)
        fd.append('subject', tpl.sample.label)
        await inboxApi.post('messages/upload', { body: fd, timeout: 300_000 })
        toast.success('项目已创建，示例材料已进「待处理」', { id: 'newproj', duration: 4000 })
        onOpenChange(false)
        void navigate(materialPrep('todo'))
        return
      }

      toast.success('项目已创建')
      onOpenChange(false)
      // 有合同跳项目详情（按合同视角）；没合同退回办案工作台（按案件视角）
      void navigate(contractId != null ? projectDetail(contractId) : bankLitigation(caseId))
    } catch (e) {
      toast.error(`建项目失败：${errMessage(e)}`, { duration: 6000 })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[620px]">
        <DialogHeader>
          <DialogTitle>新建项目</DialogTitle>
          <DialogDescription>可以直接建空白项目，也可以从示例开始 —— 字段会预先填好。</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 pt-1">
          <div className="flex flex-col gap-1.5">
            <label className="text-[12px] font-medium">项目名称</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={tpl ? `例：${tpl.their[0]?.name}${tpl.cause}` : '例：某某银行诉某某金融借款合同纠纷'}
              className="h-9"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="flex items-center gap-1.5 text-[12px] font-medium">
              <Sparkles className="size-3.5 text-muted-foreground" />
              从示例开始（可选）
            </span>
            <div className="flex flex-col gap-1.5">
              {PROJECT_TEMPLATES.map((t) => {
                const active = tpl?.key === t.key
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => {
                      setTpl(active ? null : t)
                      if (!name.trim() && !active) setName(`${t.their[0]?.name ?? ''}${t.cause}`)
                    }}
                    className={cn(
                      'flex items-start gap-2.5 rounded-[9px] border px-3 py-2.5 text-left transition-colors',
                      active
                        ? 'border-foreground/40 bg-secondary/60'
                        : 'border-border hover:border-foreground/20 hover:bg-secondary/40',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-[3px] size-3.5 flex-none rounded-full border',
                        active ? 'border-foreground bg-foreground' : 'border-zinc-300',
                      )}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium">{t.title}</span>
                      <span className="mt-0.5 block text-[11.5px] leading-[1.6] text-muted-foreground">
                        {t.summary}
                      </span>
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {tpl ? (
            <label className="flex items-start gap-2 rounded-[8px] border border-border bg-secondary/30 px-3 py-2">
              <input
                type="checkbox"
                checked={withSample}
                onChange={(e) => setWithSample(e.target.checked)}
                className="mt-[2px]"
              />
              <span className="min-w-0 flex-1 text-[11.5px] leading-[1.6]">
                <span className="flex items-center gap-1 font-medium">
                  <FileStack className="size-3" />
                  同时放入示例材料：{tpl.sample.label}
                </span>
                <span className="mt-0.5 block text-muted-foreground">
                  {tpl.sample.desc}（{tpl.sample.pages} 页 / {tpl.sample.docs} 份材料）。
                  放入后会出现在「材料预处理 · 待处理」，接着就能自动分段 — 和真实上传一样。
                </span>
              </span>
            </label>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            取消
          </Button>
          <Button onClick={() => void submit()} disabled={!canSubmit}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : null}
            {tpl && withSample ? '创建并放入材料' : '创建项目'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 当前律师 id（新建项目必须指派主办律师） */
async function currentLawyerId(): Promise<number> {
  const orgApi = createApiClient({ prefix: '/api/v1/organization' })
  try {
    const me = await orgApi.get('me').json<{ id?: number }>()
    if (me?.id != null) return Number(me.id)
  } catch {
    /* 端点不可用时走兜底 */
  }
  const list = await orgApi.get('lawyers').json<{ id: number }[] | { items?: { id: number }[] }>()
  const arr = Array.isArray(list) ? list : (list.items ?? [])
  if (arr[0]?.id != null) return Number(arr[0].id)
  throw new Error('无法确定当前律师，请重新登录后重试')
}
