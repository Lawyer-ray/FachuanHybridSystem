/**
 * ① 收案 —— 客户发来一整包扫描件，系统自动拆成单份材料
 *
 * 这一阶段回答一个问题：**客户到底给了什么、系统认出了几份、哪几份认不准。**
 * 所以版面是「拆分结果表 + 逐份状态」，不是统计报表。
 */

import { AlertTriangle, CheckCircle2, FileStack, HelpCircle, Upload } from 'lucide-react'

import { DEMO_INTAKE_EVENTS, DEMO_INTAKE_SEGMENTS, DEMO_INTAKE_SOURCES } from '../demo-data'
import { ActionButton, InsetBlock, Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

export function IntakePanel() {
  const total = DEMO_INTAKE_SEGMENTS.length
  const okCount = DEMO_INTAKE_SEGMENTS.filter((s) => s.status === 'ok').length
  const reviewCount = DEMO_INTAKE_SEGMENTS.filter((s) => s.status === 'review').length
  const unrecognized = DEMO_INTAKE_SEGMENTS.filter((s) => s.status === 'unrecognized').length
  const pages = DEMO_INTAKE_SEGMENTS.reduce((n, s) => {
    const m = s.pages.match(/P(\d+)(?:[–-](\d+))?/)
    if (!m) return n
    const a = Number(m[1])
    const b = m[2] ? Number(m[2]) : a
    return n + (b - a + 1)
  }, 0)

  return (
    <div className="flex flex-col gap-3.5">
      {/* 顶部：这一包材料的状况 */}
      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="总页数" value={`${pages}`} />
        <StatCell label="拆出材料" value={`${total} 份`} tone="blue" />
        <StatCell label="认准" value={`${okCount} 份`} tone="green" />
        <StatCell
          label="待核对 / 未识别"
          value={`${reviewCount} / ${unrecognized}`}
          tone={reviewCount + unrecognized > 0 ? 'yellow' : 'green'}
        />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 来源卡 */}
          <WorkCard>
            <SectionTitle title="这一包从哪来" hint="客户上传 · 6 个源文件合并" />
            <InsetBlock className="mt-2.5">
              <div className="flex items-center gap-2.5">
                <FileStack className="size-4 flex-none text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12.5px] font-medium">银行个贷不良_首批材料.zip</div>
                  <div className="mt-0.5 text-[10.5px] text-muted-foreground">
                    客户经理 王某某 通过客户链接上传 · 10-28 09:41 · 12.4 MB
                  </div>
                </div>
                <Pill tone="green">已下载</Pill>
              </div>
            </InsetBlock>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <Pill>借款合同.pdf</Pill>
              <Pill>借据.pdf</Pill>
              <Pill>还款明细.xlsx</Pill>
              <Pill>催收记录.pdf</Pill>
              <Pill>身份证.jpg</Pill>
              <Pill>流水.pdf</Pill>
            </div>
          </WorkCard>

          {/* 源文件清单 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="整包里的源文件" hint="6 个源文件合并成 38 页" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_INTAKE_SOURCES.map((f) => (
                <li key={f.name} className="flex items-center gap-3 px-5 py-2">
                  <span className="min-w-0 flex-1 truncate text-[12px]" title={f.name}>{f.name}</span>
                  <Pill>{f.kind}</Pill>
                  <span className="w-[52px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">{f.pages} 页</span>
                  <span className="w-[60px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">{f.size}</span>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 处理流水 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="处理流水" hint="从收到到拆完 · 用时 9.2 秒" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_INTAKE_EVENTS.map((e) => (
                <li key={e.at + e.event} className="flex items-center gap-3 px-5 py-2">
                  <span className="w-[82px] flex-none text-[10.5px] tabular-nums text-muted-foreground">{e.at}</span>
                  <Pill tone="blue">{e.event}</Pill>
                  <span className="min-w-0 flex-1 truncate text-[11.5px]" title={e.detail}>{e.detail}</span>
                  <span className="w-[56px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                    {e.ms ? `${e.ms} ms` : '—'}
                  </span>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 拆分结果表 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle
                title="自动拆分结果"
                hint={`按页内容识别 · ${total} 份`}
                className="w-full"
                action={
                  <ActionButton sm>
                    <Upload className="size-3" /> 追加材料
                  </ActionButton>
                }
              />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_INTAKE_SEGMENTS.map((s) => (
                <li key={s.seq} className="flex items-start gap-3 px-5 py-2.5">
                  <span
                    className={cn(
                      'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                      s.status === 'ok'
                        ? 'bg-status-green'
                        : s.status === 'review'
                          ? 'bg-status-yellow'
                          : 'bg-status-red',
                    )}
                  >
                    {s.status === 'ok' ? (
                      <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                    ) : s.status === 'review' ? (
                      <HelpCircle className="size-2.5 text-white" strokeWidth={3} />
                    ) : (
                      <AlertTriangle className="size-2.5 text-white" strokeWidth={3} />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="text-[12.5px] font-medium">{s.fileName}</span>
                      <Pill tone="blue">{s.type}</Pill>
                      <span className="text-[10.5px] tabular-nums text-muted-foreground">{s.pages}</span>
                    </div>
                    <div className="mt-0.5 text-[10.5px] text-muted-foreground">{s.note}</div>
                  </div>
                  <div className="flex flex-none items-center gap-2">
                    <span
                      className={cn(
                        'text-[11px] tabular-nums',
                        s.confidence >= 0.9
                          ? 'text-muted-foreground'
                          : s.confidence >= 0.5
                            ? 'text-status-yellow'
                            : 'text-status-red',
                      )}
                    >
                      {(s.confidence * 100).toFixed(0)}%
                    </span>
                    <span className="w-[52px] text-right">
                      <Pill
                        tone={
                          s.status === 'ok' ? 'green' : s.status === 'review' ? 'yellow' : 'red'
                        }
                      >
                        {s.status === 'ok' ? '已认准' : s.status === 'review' ? '待核对' : '未识别'}
                      </Pill>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </WorkCard>
        </div>

        {/* 右栏 */}
        <WorkCard padded={false}>
          <RailSection title="当前进度">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-[11.5px]">
                <span className="text-muted-foreground">拆分</span>
                <Pill tone="green">已完成</Pill>
              </div>
              <div className="flex items-center justify-between text-[11.5px]">
                <span className="text-muted-foreground">归入本案</span>
                <Pill tone="green">8 份已归</Pill>
              </div>
              <div className="flex items-center justify-between text-[11.5px]">
                <span className="text-muted-foreground">待人工核对</span>
                <Pill tone="yellow">2 份</Pill>
              </div>
            </div>
          </RailSection>

          <RailSection title="下一步">
            <div className="rounded-[8px] border border-status-blue/40 bg-status-blue-bg/60 px-2.5 py-2">
              <div className="text-[11.5px] font-medium">需要你确认 2 处</div>
              <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                差额补足承诺函落款被印章遮盖；手写便签疑非案件材料。
                确认后才能进入「读懂」阶段。
              </p>
            </div>
          </RailSection>

          <RailSection title="识别口径">
            <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
              按每页内容判断材料类型，不按文件名猜。
              认不准的标「待核对」，完全认不出的标「未识别」—— 都不会被硬塞进某个类型。
            </p>
          </RailSection>
        </WorkCard>
      </div>
    </div>
  )
}
