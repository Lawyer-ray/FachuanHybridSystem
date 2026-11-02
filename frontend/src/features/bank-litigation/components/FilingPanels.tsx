import { useState } from 'react'
import { AlertTriangle, ExternalLink, Loader2 } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'

import { useCaseFilingInfo } from '../hooks/use-cases'
import { useCourtFiling } from '../hooks/use-auto-run'
import { ActionButton, InsetBlock, KeyValueRow, Pill, RailSection, SectionTitle, StatCell, StatStrip, StepItem, WorkCard } from './ui'
import { AmountCheckTable } from './court/AmountCheckTable'
import { CourtPlatform } from './court/CourtPlatform'
import { FieldMappingTable } from './court/FieldMappingTable'
import { MaterialList } from './court/MaterialList'
import { SubmitHistory } from './court/SubmitHistory'
import { PHASE_META, SessionResult, pillTone } from './filing-session'

/* `BankLitigationPage` 从本文件取两个面板，OA 那一半指向新拆出的文件，
   调用点不用改 import 路径。 */
export { OAFilingPanel } from './oa/OAFilingPanel'
import type { FilingEngine, FilingType } from '../types'
import { fmtMoney } from '../utils'

/**
 * 立案执行面板 —— 律所 OA 与一张网两个外部系统的入口。
 * 律所 OA 那一半已拆到 `oa/OAFilingPanel.tsx`（文件行数红线），
 * 这里保留一张网面板 + 两侧共用的轮询阶段/会话结果呈现。
 *
 * ═══ 这两条链路的共同形状 ═══
 * 提交 → 后台线程跑浏览器自动化（Playwright）→ 前端轮询会话状态 → 终态停。
 * 所以界面上必须诚实呈现三件事：
 *   1. **不能假装秒完成**：真实跑一次要开页面、填表单、传附件，几十秒到几分钟。
 *      面板上显示轮询次数与原始 status，让律师知道「确实在跑」而不是卡住。
 *   2. **凭证缺失要前置说**：OA 没配凭证、一张网没法院账号，点下去也是必失败，
 *      不如点之前就说清。这就是 `has_credential` / `has_court_credential` 的用途。
 *   3. **失败要把后端原话给人看**：自动化失败的原因（页面改版、验证码、法院退回）
 *      只有后端的 error_message 说得清，前端不做二次翻译。
 */

// ───────────────────────── 一张网 ─────────────────────────

export function CourtFilingPanel({ caseId }: { caseId: number }) {
  const info = useCaseFilingInfo(caseId)
  const { state, run, reset } = useCourtFiling()

  /* 立案类型与引擎：后端会给一个建议值（suggested_filing_type / default_filing_engine），
     但那只是建议 —— 同一件案子可能先起诉后执行，也可能法院插件没装只能走浏览器。
     所以两个都给用户可改，默认用后端建议。
     ⚠️ 必须用「用户改过没有」来兜：直接 `useState(info.data?.xxx)` 时，
     首次渲染 data 还是 null，值会被永久钉在 fallback 上（后端建议形同虚设）。 */
  const [typeOverride, setTypeOverride] = useState<FilingType | null>(null)
  const [engineOverride, setEngineOverride] = useState<FilingEngine | null>(null)

  if (info.loading) return <LoadingBlock text="正在读取立案信息…" size="sm" />
  if (info.error) {
    return <ErrorBlock error={info.error} fallback="立案信息读取失败" onRetry={info.reload} />
  }

  const i = info.data
  if (!i) return <EmptyBlock>没有可用的立案信息。</EmptyBlock>

  const filingType: FilingType = typeOverride ?? ((i.suggested_filing_type as FilingType) || 'civil')
  const filingEngine: FilingEngine = engineOverride ?? ((i.default_filing_engine as FilingEngine) || 'api')

  const running = state.phase === 'submitting' || state.phase === 'running'
  const blockers: string[] = []
  if (!i.has_court_credential) blockers.push('未配置一张网（法院）账号')
  if (!i.plugin_available) blockers.push('法院立案插件未安装')
  if (!i.our_party_is_plaintiff_side) blockers.push('我方不是原告方，本页只处理起诉立案')
  if (!i.court_name) blockers.push('未登记管辖法院')
  // 执行立案的前提是有生效裁判文书。后端会在执行时才校验，
  // 但那时会话已建、浏览器已开，失败得很晚。这里前置提示。
  //
  // 判定口径：本案当前阶段已经是执行（说明已经走到这一步），或者
  // 案件已有登记案号（有一审判决才会立案号）。两者都没有才提示。
  if (filingType === 'execution') {
    const alreadyExecution = /执行|enforcement/i.test(i.case_name) || i.court_name != null
    if (!alreadyExecution) {
      blockers.push('执行立案需先有生效裁判文书（本案尚未登记案号）')
    }
  }

  return (
    <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,1fr)_300px]">
      {/* ══════ 左列：立案信息 + 阻断 + 动作 + 映射/校验/历史/材料 ══════ */}
      <div className="flex min-w-0 flex-col gap-3.5">
        {/* ① + ② 两张卡并排：案件要素 / 当事人。
            原先这些字段挤在一张卡里，白卡覆盖只有屏高 6%~18%，整页像纯文字文档。 */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <WorkCard>
            <SectionTitle title="案件要素" hint="机器按案件数据填好" />
            <InsetBlock className="mt-2.5">
            <dl className="divide-y divide-border-light">
              <KeyValueRow label="案由">
                <span className="block truncate" title={i.cause_of_action || ''}>
                  {i.cause_of_action || '—'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="管辖法院">
                <span className="block truncate" title={i.court_name || ''}>
                  {i.court_name || '（未登记）'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="标的额">
                <span className="font-medium tabular-nums">
                  {i.target_amount ? `¥${fmtMoney(i.target_amount)}` : '—'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="立案类型">
                <span>{filingType === 'execution' ? '执行立案' : '民事一审'}</span>
              </KeyValueRow>
            </dl>
            </InsetBlock>
          </WorkCard>

          <WorkCard>
            <SectionTitle title="当事人" hint="递交前核对身份" />
            <InsetBlock className="mt-2.5">
            <dl className="divide-y divide-border-light">
              <KeyValueRow label="原告">
                <span className="block truncate" title={i.plaintiff_name || ''}>
                  {i.plaintiff_name || '—'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="被告">
                <span className="block truncate" title={i.defendant_name || ''}>
                  {i.defendant_name || '—'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="我方立场">
                <Pill tone={i.our_party_is_plaintiff_side ? 'green' : 'red'}>
                  {i.our_party_is_plaintiff_side ? '原告方' : '非原告方'}
                </Pill>
              </KeyValueRow>
              <KeyValueRow label="法院账号">
                <Pill tone={i.has_court_credential ? 'green' : 'red'}>
                  {i.has_court_credential ? '已配置' : '未配置'}
                </Pill>
              </KeyValueRow>
            </dl>
            </InsetBlock>
          </WorkCard>
        </div>

        {/* ③ 递交参数卡 */}
        <WorkCard>
          <SectionTitle title="递交参数" hint="一般不用改，默认取后端建议值" />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select
              value={filingType}
              onChange={(e) => setTypeOverride(e.target.value as FilingType)}
              disabled={running}
              aria-label="立案类型"
              className="h-[28px] rounded-[7px] border border-input bg-background px-2.5 text-[11.5px] outline-none transition-colors hover:border-foreground/30 disabled:opacity-60"
            >
              <option value="civil">民事一审</option>
              <option value="execution">执行立案</option>
            </select>
            <select
              value={filingEngine}
              onChange={(e) => setEngineOverride(e.target.value as FilingEngine)}
              disabled={running}
              aria-label="递交引擎"
              className="h-[28px] rounded-[7px] border border-input bg-background px-2.5 text-[11.5px] outline-none transition-colors hover:border-foreground/30 disabled:opacity-60"
            >
              <option value="api">接口引擎</option>
              <option value="playwright">浏览器自动化</option>
            </select>
            {i.suggested_filing_type !== filingType ? (
              <span className="text-[10.5px] text-status-yellow">
                已改为「{filingType === 'execution' ? '执行立案' : '民事一审'}」，后端建议「
                {i.suggested_filing_type === 'execution' ? '执行立案' : '民事一审'}」
              </span>
            ) : null}
          </div>
        </WorkCard>

        {/* ④ 字段映射：视频原型里最核心的一块 —— 机器填了什么，律师要能逐行看 */}
        <FieldMappingTable />

        {/* ⑤ 三处金额校验：立案被退回的头号原因，三列摆开比一句话有用 */}
        <AmountCheckTable />

        {/* ② 阻断原因（有才出现） */}
        {blockers.length ? (
          <div className="rounded-[12px] border border-status-red/40 bg-status-red-bg px-4 py-3.5">
            <div className="flex items-center gap-1.5 text-[12.5px] font-semibold text-status-red">
              <AlertTriangle className="size-3.5 flex-none" />
              暂不能递交 · {blockers.length} 项待处理
            </div>
            <ul className="mt-2 flex flex-col gap-1.5">
              {blockers.map((b) => (
                <li key={b} className="flex items-start gap-2 text-[11.5px] leading-[1.55] text-status-red/90">
                  <span className="mt-[6px] size-1 flex-none rounded-full bg-status-red/70" />
                  {b}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* ③ 人工闸门：全片重心，做成最重的一块 */}
        <div className="rounded-[12px] border border-foreground/15 bg-foreground px-4 py-3.5 text-background">
          <div className="flex items-start gap-2.5">
            <div className="mt-[2px] grid size-5 flex-none place-items-center rounded-full bg-status-yellow text-[11px] font-bold text-foreground">
              !
            </div>
            <div className="min-w-0">
              <div className="text-[13px] font-semibold">提交由律师本人点</div>
              <p className="mt-1 text-[11.5px] leading-[1.65] text-background/70">
                填报与推送由服务端驱动一张网。机器填到头，
                <span className="font-medium text-background">送出去那一下必须人点</span>
                —— 提交即对法院作出意思表示，责任在签字律师。
              </p>
            </div>
          </div>
        </div>

        {/* ④ 动作区 */}
        <div className="flex flex-wrap items-center gap-2.5">
          <ActionButton
            dark
            disabled={blockers.length > 0 || running}
            onClick={() => {
              reset()
              void run({ case_id: caseId, filing_type: filingType, filing_engine: filingEngine })
            }}
          >
            {running ? <Loader2 className="size-3.5 animate-spin" /> : <ExternalLink className="size-3.5" />}
            {running ? '一张网立案进行中…' : '推送到一张网'}
          </ActionButton>
          <Pill tone={pillTone(PHASE_META[state.phase].tone)}>
            {PHASE_META[state.phase].text}
          </Pill>
          {state.ticks > 0 && running ? (
            <span className="text-[10.5px] tabular-nums text-muted-foreground">
              已轮询 {state.ticks} 次
            </span>
          ) : null}
          <SessionResult error={state.error} status={state.status} phase={state.phase} hint="一张网立案" />
        </div>

        {/* ⑥ 历史递交：为什么上一次没过，比「本次成功」更常被追问 */}
        <SubmitHistory />

        {/* ⑦ 随案材料：盖章与上传是两件事，分三列写 */}
        <MaterialList />
      </div>

      {/* ══════ 右列：照 deal-detail 的 DetailRail —— 整栏一张卡，内部淡线分段 ══════ */}
      <div className="flex min-w-0 flex-col gap-3.5 xl:sticky xl:top-3">
        <WorkCard padded={false}>
          {/* 段 1：递交进度 */}
          <RailSection title="递交进度">
            <StepItem
              index={1}
              title="表单填报"
              desc={blockers.length ? '有阻塞项' : '信息已就绪'}
              state={blockers.length ? 'blocked' : 'done'}
            />
            <StepItem
              index={2}
              title="律师核对"
              desc="逐项确认"
              state={blockers.length ? 'todo' : 'current'}
            />
            <StepItem index={3} title="律师点提交" desc="机器不代点" state="todo" />
            <StepItem index={4} title="法院受理" desc="受理号回填" state="todo" />
          </RailSection>

          {/* 段 2：本次递交 */}
          <RailSection title="本次递交">
            <StatStrip className="grid-cols-2">
              <StatCell label="标的额" value={i.target_amount ? `¥${fmtMoney(i.target_amount)}` : '—'} />
              <StatCell label="递交引擎" value={filingEngine === 'api' ? '接口' : '浏览器'} />
            </StatStrip>
            <dl className="mt-2.5">
              <KeyValueRow label="管辖法院">
                <span className="block truncate text-[12px]" title={i.court_name || ''}>
                  {i.court_name || '（未登记）'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="立案类型">
                <span className="text-[12px]">{filingType === 'execution' ? '执行立案' : '民事一审'}</span>
              </KeyValueRow>
              <KeyValueRow label="递交人">
                <span className="text-[12px]">主办律师</span>
              </KeyValueRow>
            </dl>
          </RailSection>

          {/* 段 3：案号与凭证 */}
          <RailSection title="递交凭证">
            <dl>
              <KeyValueRow label="法院账号">
                <Pill tone={i.has_court_credential ? 'green' : 'red'}>
                  {i.has_court_credential ? '已配置' : '未配置'}
                </Pill>
              </KeyValueRow>
              <KeyValueRow label="立案插件">
                <Pill tone={i.plugin_available ? 'green' : 'red'}>
                  {i.plugin_available ? '已安装' : '未安装'}
                </Pill>
              </KeyValueRow>
              <KeyValueRow label="一张网受理号">
                <span className="text-[12px] text-muted-foreground">递交后回填</span>
              </KeyValueRow>
            </dl>
          </RailSection>

          {/* 段 4：风险提示 */}
          <RailSection title="注意">
            <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
              <div className="text-[11px] font-medium">提交后不可撤回</div>
              <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                误提交只能等法院退回。递交前请确认当事人、法院与金额三项无误。
              </p>
            </div>
          </RailSection>
        </WorkCard>

        {/* 法院平台信息 + 校验规则口径：递交前该读一遍的背景 */}
        <CourtPlatform />
      </div>
    </div>
  )
}
