import { useState } from 'react'
import { Loader2 } from 'lucide-react'
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
import { Input } from '@/components/ui/input'
import { errMessage } from '@/lib/errors'

import { createCaseUnderContract } from '../../api'

/**
 * 新建下一程序案件（左列「下一步」行上的 ＋ 新建X案件）。
 *
 * 只有一件事是硬约束：**阶段必须属于合同勾选的代理阶段**——后端拿 `contract_id`
 * 去解析并校验 `current_stage`，不在集合里直接 400。所以这一项不让改，就显示
 * 页面上算出来的那个「下一程序」。
 *
 * 其余字段都给好默认值（名称 / 案由 / 标的额 / 法院 从上一次程序继承），因为
 * 二审、执行这些后续程序跟一审是同一桩事，只是换了法院与案号；律师通常只需要
 * 确认一下就能建。建案后法院走 `supervising_authorities` 子表（`c.auth` 取它），
 * 所以是真写进去的，不是只显示在表单里。
 */
export function AddCaseDialog({
  open,
  contractId,
  stage,
  stageCode,
  caseType,
  defaults,
  onClose,
  onSaved,
}: {
  open: boolean
  contractId: number
  /** 阶段的**中文标签**（用于标题/提示）：详情页算出来的下一程序是标签，不是代码 */
  stage: string
  /**
   * 阶段的**代码**（first_trial / second_trial / enforcement …）。
   *
   * 必须单独给：后端 `current_stage` 收的是代码，而页面上的 `nextStage()` 给的是
   * 标签（「二审」）。把标签当代码发过去会被判「阶段不适用于此案件类型」。
   */
  stageCode: string
  caseType?: string | null
  /** 从上一个程序继承的默认值（都可改） */
  defaults: { name: string; cause: string; amount: string; court: string }
  onClose: () => void
  /** 建好后把案件 id 交回页面：页面用它滚动并高亮新卡片 */
  onSaved: (caseId: number) => void
}) {
  const [name, setName] = useState(defaults.name)
  const [cause, setCause] = useState(defaults.cause)
  const [amount, setAmount] = useState(defaults.amount)
  const [court, setCourt] = useState(defaults.court)
  const [isFiled, setIsFiled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const amountNum = amount.trim() === '' ? null : Number(amount)
  const amountBad = amountNum != null && (!Number.isFinite(amountNum) || amountNum < 0)
  const canSubmit = name.trim().length > 0 && stageCode !== '' && !amountBad && !busy

  async function submit() {
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const created = await createCaseUnderContract({
        contractId,
        name: name.trim(),
        stage: stageCode,
        caseType,
        cause: cause.trim(),
        targetAmount: amountNum,
        court: court.trim(),
        isFiled,
      })
      toast.success('已新建' + stage + '案件')
      onSaved(created.id)
      onClose()
    } catch (e) {
      // 后端在这里会给出很具体的话：「合同未激活」「当前阶段必须属于代理阶段集合」…
      // 原样展示，律师才知道该去改项目状态还是改阶段
      setError(errMessage(e, '新建案件失败，请重试'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>新建{stage}案件</DialogTitle>
          <DialogDescription>
            建在「当前委托」下，阶段固定为{stage}（合同勾选的代理阶段）。法院会写进案件的
            主管机关，案号可建好后在案件卡里补。
          </DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-col gap-3 pt-1"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-[600] text-secondary-foreground">案件名称</span>
            <Input
              aria-label="案件名称"
              value={name}
              maxLength={255}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：某某公司诉某某买卖合同纠纷"
            />
          </label>

          <div className="grid grid-cols-2 gap-3 max-[520px]:grid-cols-1">
            <label className="flex flex-col gap-1">
              <span className="text-[12px] font-[600] text-secondary-foreground">案由</span>
              <Input
                aria-label="案由"
                value={cause}
                maxLength={128}
                placeholder="例：买卖合同纠纷"
                onChange={(e) => setCause(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[12px] font-[600] text-secondary-foreground">标的额</span>
              <Input
                aria-label="标的额"
                inputMode="decimal"
                value={amount}
                placeholder="例：161762"
                onChange={(e) => setAmount(e.target.value)}
              />
              {amountBad && <span className="text-[11px] text-status-red">金额应为非负数字</span>}
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-[600] text-secondary-foreground">法院 / 仲裁机构</span>
            <Input
              aria-label="主管机关"
              value={court}
              placeholder="例：佛山市顺德区人民法院"
              onChange={(e) => setCourt(e.target.value)}
            />
            <span className="text-[11px] text-muted-foreground/80">
              留空也能建，之后在案件卡的联系人里再补。
            </span>
          </label>

          <label className="flex items-center gap-2 text-[12.5px] text-secondary-foreground">
            <input
              type="checkbox"
              className="size-4 accent-foreground"
              checked={isFiled}
              onChange={(e) => setIsFiled(e.target.checked)}
            />
            已建档
            <span className="text-[11px] text-muted-foreground/80">（建档编号由后端生成）</span>
          </label>

          {error && <p className="text-[12px] text-status-red">{error}</p>}
          {stageCode === '' && (
            <p className="text-[12px] text-status-red">
              这个阶段在前端枚举里没有对应代码，暂时无法建案（请把「{stage}」补进 contract-enums）。
            </p>
          )}

          <DialogFooter className="mt-1 gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              取消
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {busy && <Loader2 className="mr-1 size-3.5 animate-spin" />}
              新建案件
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
