/**
 * ⑥ 校验 → 通知律师去一张网
 *
 * 这一步是**最后一道人工闸门之前**的机器检查：
 * 签字盖章齐不齐、当事人信息对不对、金额三处一致不一致。
 * 齐了才通知律师去一张网提交 —— 提交那一下仍然由律师本人点（见一张网页）。
 *
 * 与「③ 缺件」的区别：那里查「材料有没有」，这里查「材料对不对」。
 * 有了一份材料但没签字盖章，等于没有。
 */

import { AlertTriangle, CheckCircle2, Gavel, XCircle } from 'lucide-react'

import { DEMO_FILING_CHECKS, DEMO_FILING_FIXES, DEMO_SIGN_CHECKS } from '../demo-data'
import { InsetBlock, Pill, RailSection, SectionTitle, StatCell, StatStrip, StepItem, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

export function FilingPanel() {
  const sealOk = DEMO_SIGN_CHECKS.filter((d) => d.sealOk).length
  const signOk = DEMO_SIGN_CHECKS.filter((d) => d.signOk).length
  const blocked = DEMO_SIGN_CHECKS.filter((d) => !d.sealOk || !d.signOk)
  const total = DEMO_SIGN_CHECKS.length

  return (
    <div className="flex flex-col gap-3.5">
      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="待核对文书" value={`${total} 份`} />
        <StatCell label="盖章齐" value={`${sealOk}/${total}`} tone={sealOk === total ? 'green' : 'yellow'} />
        <StatCell label="签字齐" value={`${signOk}/${total}`} tone={signOk === total ? 'green' : 'yellow'} />
        <StatCell
          label="阻塞项"
          value={`${blocked.length} 份`}
          tone={blocked.length ? 'red' : 'green'}
        />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 签字盖章核对表 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="签字盖章核对" hint="机器比对扫描件的印章与签名区域" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_SIGN_CHECKS.map((d) => {
                const ok = d.sealOk && d.signOk
                return (
                  <li key={d.docName} className="flex items-start gap-3 px-5 py-3">
                    <span
                      className={cn(
                        'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                        ok ? 'bg-status-green' : 'bg-status-red',
                      )}
                    >
                      {ok ? (
                        <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                      ) : (
                        <XCircle className="size-2.5 text-white" strokeWidth={3} />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[12.5px] font-medium">{d.docName}</div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-muted-foreground">
                        <span>需盖：{d.needSeal}</span>
                        {d.needSign !== '—' ? (
                          <>
                            <span className="text-border">·</span>
                            <span>需签：{d.needSign}</span>
                          </>
                        ) : null}
                      </div>
                      <div
                        className={cn(
                          'mt-0.5 text-[10.5px]',
                          ok ? 'text-muted-foreground' : 'text-status-red',
                        )}
                      >
                        {d.note}
                      </div>
                    </div>
                    <div className="flex flex-none items-center gap-1.5">
                      <Pill tone={d.sealOk ? 'green' : 'red'}>章{d.sealOk ? '✓' : '✗'}</Pill>
                      <Pill tone={d.signOk ? 'green' : 'red'}>签{d.signOk ? '✓' : '✗'}</Pill>
                    </div>
                  </li>
                )
              })}
            </ul>
          </WorkCard>

          {/* 起诉条件机器判定 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="起诉条件机器判定" hint="法律要件 + 卷宗要件" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_FILING_CHECKS.map((c) => (
                <li key={c.check} className="flex items-start gap-3 px-5 py-2.5">
                  <span
                    className={
                      c.result === 'pass'
                        ? 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-green'
                        : c.result === 'warn'
                          ? 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-yellow'
                          : 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-red'
                    }
                  >
                    <span className="text-[9px] font-bold text-white">
                      {c.result === 'pass' ? '✓' : c.result === 'warn' ? '!' : '✕'}
                    </span>
                  </span>
                  <span className="w-[110px] flex-none text-[12px] font-medium">{c.check}</span>
                  <span className="w-[160px] flex-none truncate text-[11px] text-muted-foreground" title={c.value}>{c.value}</span>
                  <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground" title={c.detail}>{c.detail}</span>
                  <Pill tone={c.result === 'pass' ? 'green' : c.result === 'warn' ? 'yellow' : 'red'}>
                    {c.result === 'pass' ? '通过' : c.result === 'warn' ? '提示' : '不通过'}
                  </Pill>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 不通过的怎么修 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="不通过项怎么修" hint="系统能自动修的会直接修" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_FILING_FIXES.map((f) => (
                <li key={f.item} className="px-5 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium">{f.item}</span>
                    <Pill tone={f.auto ? 'green' : 'yellow'}>{f.auto ? '系统自动' : '需人工'}</Pill>
                    <span className="ml-auto text-[10px] text-muted-foreground">{f.owner} · {f.eta}</span>
                  </div>
                  <div className="mt-0.5 text-[10.5px] text-muted-foreground">{f.fix}</div>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 报送与通知 */}
          <WorkCard>
            <SectionTitle title="校验通过后怎么通知律师" hint="机器只做检查，不代提交" />
            <div className="mt-3">
              <StepItem index={1} title="签字盖章全部齐备" desc="机器核对，不齐不通知" state={blocked.length ? 'blocked' : 'done'} />
              <StepItem index={2} title="推送待办给主办律师" desc="站内通知 + 短信 + AI 助手卡片" state={blocked.length ? 'todo' : 'current'} />
              <StepItem index={3} title="律师打开一张网核对表单" desc="机器已填好，律师逐项看" state="todo" />
              <StepItem index={4} title="律师本人点提交" desc="这一步机器不代点，责任在签字律师" state="todo" />
            </div>

            <InsetBlock className="mt-3">
              <div className="flex items-start gap-2.5">
                <Gavel className="mt-[1px] size-3.5 flex-none text-muted-foreground" />
                <div className="min-w-0">
                  <div className="text-[12px] font-medium">
                    {blocked.length ? `还不能通知律师：${blocked.length} 份文书未通过核对` : '可以通知律师去一张网提交了'}
                  </div>
                  <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                    {blocked.length
                      ? blocked.map((d) => d.note).join('；')
                      : '律师会在待办里收到一条「去一张网提交」的提醒，点开即到立案页。'}
                  </div>
                </div>
              </div>
            </InsetBlock>
          </WorkCard>
        </div>

        <WorkCard padded={false}>
          <RailSection title="为什么最后才查签章">
            <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
              签章是**不可逆**的一步。前面材料不齐可以补、金额错了可以改，
              但盖了章签了字再发现不对，就要重新走一遍签署流程。
              所以放在送法院之前的最后一关。
            </p>
          </RailSection>

          <RailSection title="这台机器查什么">
            <div className="flex flex-col gap-2 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>
                <span className="font-medium text-foreground">印章</span>
                <div className="mt-0.5">识别印章图像，比对类型（公章/法代章/财务章）与位置</div>
              </div>
              <div>
                <span className="font-medium text-foreground">签名</span>
                <div className="mt-0.5">检测签名区域是否有笔迹，空白页会直接标红</div>
              </div>
              <div>
                <span className="font-medium text-foreground">骑缝</span>
                <div className="mt-0.5">核对骑缝章是否覆盖全部附件页</div>
              </div>
            </div>
          </RailSection>

          <RailSection title="不通过怎么办">
            <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>→ 生成补签清单，通知经办人</div>
              <div>→ 需重签的文书回到起草阶段</div>
              <div>→ 重签后自动重跑本页核对</div>
            </div>
          </RailSection>

          <RailSection title="一张网那一步">
            <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-[1px] size-3 flex-none text-status-yellow" />
                <p className="text-[10.5px] leading-[1.6] text-muted-foreground">
                  本页只负责「能不能去」。真正提交在「一张网立案」页，
                  由律师本人点击 —— 提交即对法院作出意思表示。
                </p>
              </div>
            </div>
          </RailSection>
        </WorkCard>
      </div>
    </div>
  )
}
