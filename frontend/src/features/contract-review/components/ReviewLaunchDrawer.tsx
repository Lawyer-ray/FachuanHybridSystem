import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, X } from 'lucide-react'

import { ErrorBlock } from '@/components/shared/AsyncState'
import { useLaunchUpload } from '../hooks/use-launch-upload'
import { useLaunchSubmit } from '../hooks/use-launch-submit'
import { useFocusTrap } from '../hooks/use-focus-trap'
import type { PartyKey } from '../domain'
import { DemandSection } from './launch/DemandSection'
import { PartySection } from './launch/PartySection'
import { StepSection } from './launch/StepSection'

/**
 * 发起审查抽屉。
 *
 * **顺序很重要**：先定立场、选范围、写交代，再让 AI 跑。
 * 反过来的旧形态（AI 已按某个立场算完再问「是吧？」）会因为立场选错而整批返工——
 * 同一份合同站甲方还是乙方，建议方向是相反的。
 *
 * 本文件只做壳层与编排：
 * - 第一阶段（上传 + 识别当事人、推荐我方）→ hooks/use-launch-upload
 * - 第二/三阶段（勾选步骤、写交代、确认立场）→ hooks/use-launch-submit
 * - 三段 UI → components/launch/*
 * - 模态行为（Esc 关闭、焦点圈定、aria-modal）→ hooks/use-focus-trap
 */

export type RepresentedParty = PartyKey

export function ReviewLaunchDrawer({
  open,
  onClose,
  onStarted,
  loadFile,
  fileName,
  partyHint,
  parties,
  clientName,
}: {
  open: boolean
  onClose: () => void
  /** 流水线已触发，带上 taskId 跳复审台 */
  onStarted: (taskId: string) => void
  /**
   * 取合同字节。调用方决定来源——可能是材料包附件（带票据的 preview 端点），
   * 也可能是合同文件夹里的文件（folder-file 端点），抽屉不关心。
   */
  loadFile: () => Promise<ArrayBuffer>
  fileName: string
  /**
   * 调用方已知的当事人（可空）。
   *
   * **不再作为唯一来源**：合同可能有甲乙丙丁四方，我方也不一定是甲方
   * （常见「代表客户股东去审」），所以真正的立场选项以**上传后 AI 识别
   * 的结果**为准，这里只用于首屏占位与兜底。
   */
  parties?: Record<string, string>
  /** 我方委托客户名：用于从识别结果里自动推荐「我方是哪一方」 */
  clientName?: string
  partyHint?: string
}) {
  const upload = useLaunchUpload({ open, loadFile, fileName, clientName })

  /**
   * 律师选中的立场。
   *
   * 初值跟随上传阶段的自动推荐（识别完成后才有），律师点选即覆盖。用「用户点过
   * 就只认用户的，没点过就跟随推荐」而不是把推荐值灌进 state：推荐可能在识别
   * 回来之后才变，灌值会和律师的手动选择打架。
   */
  const [pickedParty, setPickedParty] = useState<PartyKey | null>(null)
  const party = pickedParty ?? upload.party

  // 关掉抽屉（或换了一份合同）就作废手动立场，否则下次打开会沿用上一份的选择
  useEffect(() => {
    if (!open) setPickedParty(null)
  }, [open, fileName])

  /**
   * 打开 / 换了输入就上传识别一次。
   *
   * recognize 内部按「这条输入是否已有识别结果」幂等，所以这里不必再挂
   * running 守卫（旧实现正是靠一个只在错误分支复位的 runningRef 兜这个）。
   * 依赖里不能放 upload 对象（useMutation 每次渲染都新建），只放 recognize 的
   * 稳定输入：open + fileName + clientName。
   */
  const recognize = upload.recognize
  useEffect(() => {
    if (open) recognize()
    // recognize 是每次渲染新建的箭头函数（内部读 ref 取最新 loadFile），不能进依赖；
    // 真正的输入是 open / fileName / clientName，已在其闭包里被 useMemo 化。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, fileName, clientName])

  /** 可选的立场项：识别结果优先，未识别时为空 */
  const partyOptions = useMemo(() => {
    const src = upload.parties ?? parties ?? {}
    return (['party_a', 'party_b', 'party_c', 'party_d'] as PartyKey[])
      .filter((k) => !!src[k]?.trim())
      .map((k) => ({ key: k, name: (src[k] ?? '').trim() }))
  }, [upload.parties, parties])

  const submit = useLaunchSubmit({
    taskId: upload.taskId,
    party,
    setParty: setPickedParty,
    partyOptions,
    partyHint,
    onStarted,
  })

  const { panelRef } = useFocusTrap(open, onClose)
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (open) closeRef.current?.focus()
  }, [open])

  /** 上传阶段的错误（读合同失败）与提交阶段的错误（选漏 / 接口失败）都走同一条展示 */
  const err = upload.err ?? submit.submitErr
  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-[96] bg-foreground/30" onClick={onClose} />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="发起审查"
        className="fixed inset-y-0 right-0 z-[97] flex w-[440px] max-w-[92vw] flex-col bg-card shadow-[-6px_0_32px_rgba(0,0,0,0.1)]"
      >
        <div className="flex flex-none items-start gap-3 border-b border-border px-4.5 py-4">
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-[680]">发起审查</p>
            <p className="mt-0.5 truncate text-[12px] text-muted-foreground" title={fileName}>
              {fileName}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            aria-label="关闭"
            className="grid size-7 flex-none place-items-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={onClose}
          >
            <X className="size-3.5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4.5">
          {err && (
            <ErrorBlock error={err} fallback={err} className="my-3 px-3 py-2 text-left text-[11.5px]" />
          )}

          <PartySection
            phase={upload.phase}
            partyOptions={partyOptions}
            party={party}
            onPick={submit.setParty}
            partyHint={partyHint}
          />
          <StepSection steps={submit.steps} onToggle={submit.toggleStep} />
          <DemandSection
            note={submit.note}
            onChangeNote={submit.setNote}
            onToggleChip={submit.toggleChip}
          />
        </div>

        <div className="flex flex-none justify-end gap-2 border-t border-border px-4.5 py-3.5">
          <button
            type="button"
            className="h-[31px] rounded-[8px] border border-border bg-card px-3 text-[12.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
            onClick={onClose}
            disabled={submit.busy}
          >
            取消
          </button>
          <button
            type="button"
            className="inline-flex h-[31px] items-center gap-1.5 rounded-[8px] border border-foreground bg-foreground px-4 text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-60"
            onClick={() => void submit.start()}
            // 未选立场 / 还在识别 / 正在提交：三种情况下都不该让人点
            disabled={submit.busy || !party || upload.phase !== 'ready'}
          >
            {submit.busy && <Loader2 className="size-3.5 animate-spin" />}
            {submit.busy ? '正在发起…' : '开始审查'}
          </button>
        </div>
      </aside>
    </>
  )
}
