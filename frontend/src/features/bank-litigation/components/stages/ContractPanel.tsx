/**
 * ④ 文书 —— 自动生成委托合同 → 派机器人去 OA 做利冲检索并立案
 *
 * 这一段是两个动作串在一起：
 *   1. 系统拿案件数据把委托代理合同等文书套出来（律师核对后定稿）
 *   2. 派机器人登录律所 OA，**先查利益冲突**，没冲突才建卷
 *
 * 利冲放在立案之前是硬性的：先建了卷再发现冲突，撤销要走审批，
 * 而冲突本身可能意味着这案子根本不能接。
 */

import { AlertTriangle, Bot, CheckCircle2, FileText, ShieldAlert } from 'lucide-react'

import { DEMO_CONFLICT_HITS, DEMO_CONTRACT_GEN, DEMO_CONTRACT_TERMS } from '../demo-data'
import { StageActionCard } from './StageActionCard'
import { useStageAction } from './use-stage-action'
import { ActionButton } from '../ui'
import { InsetBlock, Pill, RailSection, SectionTitle, StatCell, StatStrip, StepItem, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

export function ContractPanel() {
  /* ① 生成委托材料 */
  const genDocs = useStageAction({
    steps: [
      { text: '读取案件数据', ms: 500, parallel: ['当事人', '案由与标的', '管辖法院', '收费约定'] },
      { text: '套用《民事委托代理合同 v3.2》', ms: 900 },
      { text: '填充 24 个字段', ms: 700 },
      {
        text: '生成授权委托书',
        ms: 600,
        retry: { times: 1, delay: 800, reason: '共同借款人信息不完整，补齐后重试' },
      },
      { text: '生成风险告知书 / 收费协议', ms: 600 },
      { text: '检查必填项', ms: 500 },
    ],
    toSummary: () => '4 份文书已生成，1 份待补（送达地址确认书需选管辖法院模板）',
  })
  /* ② 派机器人去 OA 做利冲检索 —— 这是本页的核心动作 */
  const conflictRun = useStageAction({
    steps: [
      { text: '启动服务端浏览器', ms: 700, parallel: ['分配容器', '加载自动化脚本'] },
      { text: '打开律所 OA 登录页', ms: 800 },
      {
        text: '登录 OA',
        ms: 900,
        retry: { times: 2, delay: 1500, reason: '登录会话超时，重新认证' },
      },
      { text: '进入当事人库检索', ms: 600 },
      { text: '检索：委托人 某某银行某某支行 → 无冲突', ms: 500 },
      { text: '检索：被告 谭某某 → 无同名记录', ms: 450 },
      { text: '检索：共同借款人 李某某 → 命中！', ms: 900 },
      {
        text: '命中红色冲突',
        ms: 600,
        confirm: '共同借款人李某某与本所在办「离婚案」当事人为同一人（证件号一致）。这属于禁止性冲突，是否终止本次委托？',
      },
      { text: '停止建卷，保留利冲结果页快照', ms: 500 },
    ],
    toSummary: () => '命中 1 处红色冲突（李某某），OA 立案已自动阻断',
  })
  const red = DEMO_CONFLICT_HITS.filter((h) => h.level === 'red')
  const yellow = DEMO_CONFLICT_HITS.filter((h) => h.level === 'yellow')
  const generated = DEMO_CONTRACT_GEN.filter((d) => d.status === 'generated')

  return (
    <div className="flex flex-col gap-3.5">
      <StageActionCard
        title="生成委托材料并做利益冲突检索"
        desc="先按案件数据把委托合同等文书套出来，再派机器人登录律所 OA 逐方比对当事人库。命中红色冲突就停在利冲页，不继续建卷。"
        actionLabel="生成文书 + 利冲检索"
        hint="5 份文书 · 6 方检索 · 约 4 秒"
        state={conflictRun}
        execute={() => void conflictRun.execute()}
        reset={conflictRun.reset}
        confirm={conflictRun.confirm}
      />

      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="已生成文书" value={`${generated.length}/${DEMO_CONTRACT_GEN.length}`} tone="green" />
        <StatCell label="检索主体" value={`${DEMO_CONFLICT_HITS.length} 方`} />
        <StatCell label="红色冲突" value={`${red.length}`} tone={red.length ? 'red' : 'green'} />
        <StatCell label="需复核" value={`${yellow.length}`} tone={yellow.length ? 'yellow' : 'green'} />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 生成的文书 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle
                title="自动生成的委托材料"
                hint="按案件数据套模板"
                className="w-full"
                action={
                  <ActionButton sm disabled={genDocs.phase === 'running'} onClick={() => void genDocs.execute()}>
                    {genDocs.phase === 'running' ? '生成中…' : genDocs.phase === 'done' ? '重新生成' : '生成文书'}
                  </ActionButton>
                }
              />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_CONTRACT_GEN.map((d) => (
                <li key={d.name} className="flex items-center gap-3 px-5 py-2.5">
                  <FileText className="size-3.5 flex-none text-muted-foreground" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12.5px] font-medium">{d.name}</span>
                    <span className="mt-0.5 block text-[10.5px] text-muted-foreground">{d.source}</span>
                  </span>
                  <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">{d.pages} 页</span>
                  <Pill tone={d.status === 'generated' ? 'green' : 'yellow'}>
                    {d.status === 'generated' ? '已生成' : '待生成'}
                  </Pill>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 委托合同关键条款（自动填充结果） */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="委托合同条款自动填充" hint="律师核对后定稿" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_CONTRACT_TERMS.map((t) => (
                <li key={t.clause} className="flex items-center gap-3 px-5 py-2">
                  <span className="w-[84px] flex-none text-[11.5px] text-muted-foreground">{t.clause}</span>
                  <span className="min-w-0 flex-1 truncate text-[12px] font-medium" title={t.value}>{t.value}</span>
                  <span className="w-[150px] flex-none truncate text-[10px] text-muted-foreground" title={t.source}>{t.source}</span>
                  <span className="w-[56px] flex-none text-right">
                    <Pill tone={t.filled ? 'green' : 'yellow'}>{t.filled ? '已填' : '待定'}</Pill>
                  </span>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 利冲检索 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <ShieldAlert className="size-3.5 flex-none text-muted-foreground" />
              <SectionTitle title="OA 利益冲突检索" hint="机器人登录 OA 当事人库逐方比对" className="w-full" />
            </div>

            {red.length > 0 ? (
              <div className="border-b border-border-light bg-status-red-bg/50 px-5 py-3">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-[1px] size-3.5 flex-none text-status-red" />
                  <div className="min-w-0">
                    <div className="text-[12px] font-semibold text-status-red">
                      命中 1 处红色冲突 · 已自动阻断立案
                    </div>
                    <p className="mt-0.5 text-[10.5px] leading-[1.6] text-status-red/90">
                      {red[0]!.detail}。同一自然人在对方阵营，按执业规范必须停止。
                      机器人已停在利冲结果页，未继续建卷。
                    </p>
                  </div>
                </div>
              </div>
            ) : null}

            <ul className="divide-y divide-border-light">
              {DEMO_CONFLICT_HITS.map((h, i) => (
                <li key={`${h.subject}-${i}`} className="flex items-center gap-3 px-5 py-2.5">
                  <span
                    className={cn(
                      'grid size-4 flex-none place-items-center rounded-full',
                      h.level === 'red'
                        ? 'bg-status-red'
                        : h.level === 'yellow'
                          ? 'bg-status-yellow'
                          : 'bg-status-green',
                    )}
                  >
                    {h.level === 'clear' ? (
                      <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                    ) : (
                      <AlertTriangle className="size-2.5 text-white" strokeWidth={3} />
                    )}
                  </span>
                  <span className="w-[140px] flex-none truncate text-[12px]" title={h.subject}>
                    {h.subject}
                  </span>
                  <Pill>{h.role}</Pill>
                  <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground" title={h.detail}>
                    {h.detail}
                  </span>
                  <Pill tone={h.level === 'red' ? 'red' : h.level === 'yellow' ? 'yellow' : 'green'}>
                    {h.level === 'red' ? '冲突' : h.level === 'yellow' ? '复核' : '无冲突'}
                  </Pill>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 机器人执行日志 */}
          <WorkCard>
            <SectionTitle title="机器人执行过程" hint="服务端浏览器自动化" />
            <div className="mt-3">
              <StepItem index={1} title="登录律所 OA" desc="用配置账号登录 · 1,840 ms" state="done" />
              <StepItem index={2} title="检索当事人库" desc="6 方逐方比对 · 2,260 ms" state="done" />
              <StepItem index={3} title="命中红色冲突" desc="李某某 与「离婚案」当事人同人" state="blocked" />
              <StepItem index={4} title="停止建卷" desc="等律师决定是否终止委托" state="todo" />
            </div>
          </WorkCard>
        </div>

        <WorkCard padded={false}>
          <RailSection title="当前卡点">
            <div className="rounded-[8px] border border-status-red/40 bg-status-red-bg/60 px-2.5 py-2">
              <div className="text-[11.5px] font-medium text-status-red">利冲未通过，OA 立案已停</div>
              <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                共同借款人李某某与本所在办离婚案当事人为同一人（证件号一致）。
                需由主任律师判定是否属于禁止性冲突。
              </p>
            </div>
          </RailSection>

          <RailSection title="先查利冲再看立案">
            <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
              利冲必须在建卷之前。先建了卷再发现冲突，撤销要走审批；
              而冲突本身可能意味着这个委托根本不能接。
            </p>
          </RailSection>

          <RailSection title="三档判定">
            <div className="flex flex-col gap-2">
              <div>
                <Pill tone="red">红色</Pill>
                <div className="mt-1 text-[10.5px] leading-[1.55] text-muted-foreground">
                  同名且证件号相同 —— 同一人在对方阵营，必须停
                </div>
              </div>
              <div>
                <Pill tone="yellow">黄色</Pill>
                <div className="mt-1 text-[10.5px] leading-[1.55] text-muted-foreground">
                  同名但证件号不同 —— 疑似重名，律师复核
                </div>
              </div>
              <div>
                <Pill tone="green">无冲突</Pill>
                <div className="mt-1 text-[10.5px] leading-[1.55] text-muted-foreground">
                  无命中，或仅历史已结案记录
                </div>
              </div>
            </div>
          </RailSection>

          <RailSection title="文书什么时候签">
            <InsetBlock>
              <div className="flex items-start gap-2">
                <Bot className="mt-[1px] size-3.5 flex-none text-muted-foreground" />
                <p className="text-[10.5px] leading-[1.65] text-muted-foreground">
                  生成的委托合同需要律师核对后定稿，再由当事人签署。
                  利冲未通过前不建议发出签署。
                </p>
              </div>
            </InsetBlock>
          </RailSection>
        </WorkCard>
      </div>
    </div>
  )
}
