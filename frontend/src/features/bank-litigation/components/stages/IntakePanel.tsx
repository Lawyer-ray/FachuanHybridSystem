/**
 * ① 收案 —— 客户发来一整包扫描件，系统自动拆成单份材料
 *
 * 这一阶段回答一个问题：**客户到底给了什么、系统认出了几份、哪几份认不准。**
 * 所以版面是「拆分结果表 + 逐份状态」，不是统计报表。
 */

import { AlertTriangle, CheckCircle2, FileStack, HelpCircle, Upload } from 'lucide-react'

import { DEMO_INTAKE_EVENTS, DEMO_INTAKE_SEGMENTS, DEMO_INTAKE_SOURCES } from '../demo-data'
import { useState } from 'react'
import { StageActionCard } from './StageActionCard'
import { DetailDrawer } from './DetailDrawer'
import { useStageAction } from './use-stage-action'
import { ActionButton, InsetBlock, KeyValueRow, Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

export function IntakePanel() {
  /** 点开的那一份材料（null = 抽屉关闭） */
  const [picked, setPicked] = useState<number | null>(null)
  /** 已排除的材料 seq（演示：把「手写便签」排除掉） */
  const [excluded, setExcluded] = useState<Set<number>>(new Set())

  /* 重新拆分：演示时可反复点，展示系统的处理过程 */
  const resplit = useStageAction({
    steps: [
      { text: '连接客户上传通道，拉取整包', ms: 600, parallel: ['鉴权客户链接', '查询对象存储'] },
      { text: '下载 12.4 MB · 6 个源文件', ms: 900 },
      {
        text: '合并为单一 PDF',
        ms: 700,
        retry: { times: 1, delay: 1100, reason: '还款明细.xlsx 解析超时，重试中' },
      },
      { text: '逐页文本提取', ms: 1200, parallel: ['第 1-10 页', '第 11-20 页', '第 21-30 页', '第 31-38 页'] },
      { text: '版式判断与段落切分', ms: 800 },
      { text: '按内容切分并命名', ms: 900 },
      { text: '识别材料类型与置信度', ms: 700 },
      {
        text: '核对低置信度项',
        ms: 500,
        confirm: '差额补足承诺函置信度 61%（落款被印章遮盖）、手写便签 24%（疑似非案件材料）。确认按「待核对」保留，不自动归入任何类型？',
      },
      { text: '归入本案 8 份材料', ms: 400 },
    ],
    toSummary: () => '识别出 8 份材料，其中 6 份已认准、2 份标为待核对',
  })

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
      <StageActionCard
        title="重新拆一次这包材料"
        desc="客户发来的是一叠扫描件（几十页混在一起）。系统按每页内容切成单份、重命名、认类型。认不准的会标出来让人核，不会硬塞进某个类型。"
        actionLabel="开始拆分"
        hint="8 份材料 · 约 3 秒"
        state={resplit}
        execute={() => void resplit.execute()}
        reset={resplit.reset}
        confirm={resplit.confirm}
      />

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
                <li
                  key={s.seq}
                  onClick={() => setPicked(s.seq)}
                  className="flex cursor-pointer items-start gap-3 px-5 py-2.5 transition-colors hover:bg-secondary/40"
                >
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

      {/* 材料详情抽屉 */}
      <MaterialDrawer
        seq={picked}
        onClose={() => setPicked(null)}
        excluded={excluded}
        onExclude={(seq) => {
          setExcluded((prev) => new Set(prev).add(seq))
          setPicked(null)
        }}
      />
    </div>
  )
}

/** 单份材料的详情抽屉：能看到识别依据、页码内容、可排除/重认 */
function MaterialDrawer({
  seq,
  onClose,
  excluded,
  onExclude,
}: {
  seq: number | null
  onClose: () => void
  excluded: Set<number>
  onExclude: (seq: number) => void
}) {
  const seg = seq == null ? null : DEMO_INTAKE_SEGMENTS.find((x) => x.seq === seq)
  const isExcluded = seg ? excluded.has(seg.seq) : false

  return (
    <DetailDrawer
      open={seg != null}
      onClose={onClose}
      title={seg?.fileName ?? ''}
      subtitle={seg ? `${seg.type} · ${seg.pages} · 置信度 ${(seg.confidence * 100).toFixed(0)}%` : undefined}
      badge={
        seg ? (
          <Pill tone={seg.status === 'ok' ? 'green' : seg.status === 'review' ? 'yellow' : 'red'}>
            {isExcluded ? '已排除' : seg.status === 'ok' ? '已认准' : seg.status === 'review' ? '待核对' : '未识别'}
          </Pill>
        ) : null
      }
      footer={
        seg ? (
          <>
            <ActionButton dark onClick={onClose}>
              确认识别结果
            </ActionButton>
            <ActionButton onClick={onClose}>重新识别</ActionButton>
            <ActionButton onClick={() => onExclude(seg.seq)}>排除这份</ActionButton>
          </>
        ) : null
      }
    >
      {seg ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="页码区间">{seg.pages}</KeyValueRow>
            <KeyValueRow label="识别类型">{seg.type}</KeyValueRow>
            <KeyValueRow label="置信度">
              <span
                className={
                  seg.confidence >= 0.9
                    ? 'text-status-green'
                    : seg.confidence >= 0.5
                      ? 'text-status-yellow'
                      : 'text-status-red'
                }
              >
                {(seg.confidence * 100).toFixed(0)}%
              </span>
            </KeyValueRow>
            <KeyValueRow label="归入槽位">
              {seg.status === 'ok' ? '1-立案材料' : '待人工指定'}
            </KeyValueRow>
          </dl>

          <InsetBlock className="bg-secondary/25">
            <div className="text-[10px] text-muted-foreground">识别依据</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">{seg.note}</p>
          </InsetBlock>

          <InsetBlock>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-muted-foreground">第 1 页预览</span>
              <Pill>{seg.pages}</Pill>
            </div>
            <div className="mt-2 grid aspect-[3/4] place-items-center rounded-[4px] border border-border-light bg-secondary/40">
              <span className="text-[10.5px] text-muted-foreground">（扫描件预览）</span>
            </div>
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}
