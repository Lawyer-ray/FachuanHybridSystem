/**
 * ② 读懂 —— 每份材料自动转成 markdown，律师与 AI 读同一份正文
 *
 * 为什么这阶段单独成一页：后面所有判断（缺什么、能不能立案、条款说什么）
 * 都建立在「机器读到了字」之上。转不出来，后面全是猜。
 * 所以这里展示的是**转换质量**：用什么方法转的、转出多少字、摘录长什么样。
 *
 * 每一处都能再往里点一层：
 *   · 抽屉里 [渲染视图][源码][原文对照] 三个视图，对照视图把机器读到的字与原件对齐
 *   · 关键字段行 → 弹窗：原文 3 行上下文 + 置信度 + 可手工改正
 *   · 抽屉里的转换方法可真正切换并重走一遍进度（不是只有个「换 OCR 重转」字样）
 *   · 表格上方可全选/全不选，选中的文档一起批量重转
 */

import { FileText, Play } from 'lucide-react'

import { useState } from 'react'

import { DEMO_UNDERSTAND_DOCS, DEMO_UNDERSTAND_FIELDS, DEMO_UNDERSTAND_ISSUES } from '../demo-data'
import { ActionButton, InsetBlock, Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { FieldDrawer } from './FieldDrawer'
import { MarkdownDrawer } from './MarkdownDrawer'
import { StageActionCard } from './StageActionCard'
import { useStageAction } from './use-stage-action'


const METHOD_HINT: Record<string, string> = {
  原生PDF: '直接抽取文字层，保真度最高',
  OCR: '图片型扫描件，走 OCR 识别',
  表格还原: '识别表格结构，还原成 markdown 表',
}

export function UnderstandPanel() {
  /** 正在看全文的那份（null=关闭） */
  const [viewing, setViewing] = useState<string | null>(null)
  /** 正在校对的字段（doc+field） */
  const [editing, setEditing] = useState<{ doc: string; field: string } | null>(null)
  /** 已人工改正的字段值 */
  const [overrides, setOverrides] = useState<Record<string, string>>({})
  /** 批量操作：选中的文档 */
  const [checked, setChecked] = useState<Set<string>>(new Set())

  /* 全量转换：逐份转 markdown，带进度 */
  const convertAll = useStageAction({
    steps: [
      { text: '加载 PDF 解析器', ms: 500, parallel: ['pdf.js worker', 'OCR 引擎', '表格识别模块'] },
      { text: '个人购房借款担保合同 · 原生 PDF 抽取 12,480 字', ms: 900 },
      { text: '借款借据及放款凭证 · 原生 PDF 抽取 860 字', ms: 500 },
      {
        text: '还款明细表 · 表格结构还原',
        ms: 1100,
        retry: { times: 2, delay: 900, reason: '第 5 页跨页断行，表头对齐失败' },
      },
      { text: '催收记录汇总 · OCR 识别手写批注', ms: 1400 },
      { text: '借款人身份证 · OCR 正反面', ms: 700 },
      { text: '还款账户流水 · 跨页表格拼接', ms: 1000 },
      {
        text: '差额补足承诺函 · 落款被印章覆盖',
        ms: 600,
        confirm: '这份函件的落款日期被红色印章遮盖，OCR 无法确认签署日期。要保留原图并标记「需人工核对」，还是跳过这份？',
      },
      { text: '从正文抽取关键字段', ms: 800, parallel: ['合同条款 8 项', '还款数据 4 项', '当事人信息 3 项'] },
      { text: '校验字段一致性', ms: 400 },
    ],
    toSummary: () => '6 份全量转换完成，2 份标记需复核（落款遮盖 / 手写批注）',
  })

  /* 批量重转：选中的文档一起转 */
  const batchDocs = DEMO_UNDERSTAND_DOCS.filter((d) => checked.has(d.fileName))
  const batchRun = useStageAction({
    steps:
      batchDocs.length === 0
        ? [{ text: '未选中任何文档', ms: 200, fixed: true }]
        : [
            { text: `锁定 ${batchDocs.length} 份文档与各自页码`, ms: 400 },
            ...batchDocs.map((d) => ({ text: `${d.fileName} · 重转中`, ms: 450 })),
            { text: '重抽关键字段并比对旧值', ms: 600, parallel: ['合同条款', '还款数据'] },
          ],
    // 演示不落盘：toSummary 只有 run() 有返回值时才被调到，所以借 run() 传出份数
    run: () => Promise.resolve(batchDocs.length),
    toSummary: (n) => `${n} 份已按当前方法重转，关键字段已重新比对`,
  })

  const totalChars = DEMO_UNDERSTAND_DOCS.reduce((n, d) => n + d.chars, 0)
  const highCount = DEMO_UNDERSTAND_DOCS.filter((d) => d.quality === 'high').length
  const medCount = DEMO_UNDERSTAND_DOCS.filter((d) => d.quality === 'medium').length
  const allChecked = checked.size === DEMO_UNDERSTAND_DOCS.length
  const toggle = (name: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })

  return (
    <div className="flex flex-col gap-3.5">
      <StageActionCard
        title="把这批材料转成可读正文"
        desc="律师看的、AI 读的、后续抽字段用的，必须是同一份正文。否则会出现「AI 说合同写 5%、律师看是 6%」这种扯不清的事。"
        actionLabel="全部转换"
        hint="4 份材料 · 约 5 秒"
        state={convertAll}
        execute={() => void convertAll.execute()}
        reset={convertAll.reset}
        confirm={convertAll.confirm}
      />

      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="已转换" value={`${DEMO_UNDERSTAND_DOCS.length} 份`} tone="green" />
        <StatCell label="总字数" value={totalChars.toLocaleString()} />
        <StatCell label="高保真" value={`${highCount} 份`} tone="green" />
        <StatCell label="需复核" value={`${medCount} 份`} tone={medCount ? 'yellow' : 'green'} />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 批量操作条 */}
          <WorkCard className="flex flex-wrap items-center gap-2 py-2.5">
            <ActionButton
              sm
              onClick={() =>
                setChecked(allChecked ? new Set() : new Set(DEMO_UNDERSTAND_DOCS.map((d) => d.fileName)))
              }
            >
              {allChecked ? '全不选' : '全选'}
            </ActionButton>
            <span className="text-[11px] text-muted-foreground">
              已选 {checked.size} / {DEMO_UNDERSTAND_DOCS.length} 份
            </span>
            <span className="ml-auto flex items-center gap-2">
              {batchRun.phase === 'running' ? (
                <span className="text-[10.5px] tabular-nums text-muted-foreground">
                  {batchRun.percent}% · {batchRun.progress}
                </span>
              ) : batchRun.phase === 'done' ? (
                <span className="text-[10.5px] text-status-green">{batchRun.summary}</span>
              ) : null}
              <ActionButton
                sm
                dark
                disabled={checked.size === 0 || batchRun.phase === 'running'}
                onClick={() => void batchRun.execute()}
              >
                <Play className="size-3" /> 批量重转{checked.size ? ` ${checked.size} 份` : ''}
              </ActionButton>
            </span>
          </WorkCard>

          {DEMO_UNDERSTAND_DOCS.map((d) => (
            <WorkCard key={d.fileName} padded={false}>
              <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
                <input
                  type="checkbox"
                  aria-label={`选中 ${d.fileName}`}
                  checked={checked.has(d.fileName)}
                  onChange={() => toggle(d.fileName)}
                  className="size-3.5 flex-none accent-foreground"
                />
                <FileText className="size-3.5 flex-none text-muted-foreground" />
                <SectionTitle title={d.fileName} hint={d.type} className="w-full" />
                <div className="flex flex-none items-center gap-1.5">
                  <Pill tone="blue">{d.method}</Pill>
                  <Pill tone={d.quality === 'high' ? 'green' : 'yellow'}>
                    {d.quality === 'high' ? '高保真' : '需复核'}
                  </Pill>
                  <ActionButton sm onClick={() => setViewing(d.fileName)}>
                    查看全文
                  </ActionButton>
                </div>
              </div>

              <div className="px-5 py-3">
                <div className="mb-2 flex items-center gap-3 text-[10.5px] text-muted-foreground">
                  <span>{d.pages} 页</span>
                  <span className="text-border">·</span>
                  <span>{d.chars.toLocaleString()} 字</span>
                  <span className="text-border">·</span>
                  <span>{METHOD_HINT[d.method]}</span>
                </div>

                {/* markdown 原文预览：等宽、保留 markdown 标记 */}
                <InsetBlock className="bg-secondary/20">
                  <pre className="max-h-[180px] overflow-auto whitespace-pre-wrap font-mono text-[10.5px] leading-[1.7] text-secondary-foreground">
                    {d.excerpt}
                  </pre>
                </InsetBlock>
              </div>
            </WorkCard>
          ))}
          {/* 转换问题 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="转换时发现的问题" hint="已标记，律师可对照原图核" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_UNDERSTAND_ISSUES.map((i) => (
                <li key={i.doc + i.issue} className="px-5 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium">{i.doc}</span>
                    <Pill tone="yellow">需复核</Pill>
                    <span className="ml-auto flex items-center gap-2">
                      <span className="text-[10.5px] text-status-green">{i.action}</span>
                      <ActionButton sm title="只重转这一份" onClick={() => setViewing(findDocName(i.doc))}>
                        重转
                      </ActionButton>
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10.5px] text-muted-foreground">{i.issue}</div>
                  <div className="mt-0.5 text-[10.5px] text-muted-foreground">影响：{i.impact}</div>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 关键字段抽取：每行点开可校对 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle
                title="抽取到的关键字段"
                hint="从 markdown 正文里抽，不靠文件名 · 点任意一行校对"
                className="w-full"
              />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_UNDERSTAND_FIELDS.map((f) => {
                const key = `${f.doc}-${f.field}`
                const fixed = overrides[key]
                return (
                  <li
                    key={key}
                    onClick={() => setEditing({ doc: f.doc, field: f.field })}
                    className="flex cursor-pointer items-center gap-3 px-5 py-2 transition-colors hover:bg-secondary/40"
                  >
                    <span className="w-[84px] flex-none text-[10.5px] text-muted-foreground">{f.doc}</span>
                    <span className="w-[92px] flex-none text-[11.5px] text-secondary-foreground">{f.field}</span>
                    <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium" title={fixed ?? f.value}>
                      {fixed ?? f.value}
                    </span>
                    {fixed ? <Pill tone="green">已改</Pill> : null}
                    <span className="w-[120px] flex-none truncate text-[10px] text-muted-foreground" title={f.source}>
                      {f.source}
                    </span>
                    <span
                      className="w-[44px] flex-none text-right text-[10.5px] tabular-nums"
                      style={{ color: f.confidence >= 0.95 ? undefined : 'var(--status-yellow)' }}
                    >
                      {(f.confidence * 100).toFixed(0)}%
                    </span>
                  </li>
                )
              })}
            </ul>
          </WorkCard>
        </div>

        <WorkCard padded={false}>
          <RailSection title="为什么先转 markdown">
            <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
              律师看的、AI 读的、后续抽字段用的，必须是**同一份正文**。
              如果三处各读各的，就会出现「AI 说合同写了 5%，律师看是 6%」这种扯不清的事。
            </p>
          </RailSection>

          <RailSection title="转换方法">
            <div className="flex flex-col gap-2">
              {Object.entries(METHOD_HINT).map(([k, v]) => (
                <div key={k}>
                  <div className="text-[11.5px] font-medium">{k}</div>
                  <div className="mt-0.5 text-[10.5px] leading-[1.55] text-muted-foreground">{v}</div>
                </div>
              ))}
            </div>
          </RailSection>

          <RailSection title="质量标记">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <Pill tone="green">高保真</Pill>
                <span className="text-[10.5px] text-muted-foreground">可直接用于抽取</span>
              </div>
              <div className="flex items-center gap-2">
                <Pill tone="yellow">需复核</Pill>
                <span className="text-[10.5px] text-muted-foreground">表格错行/字迹模糊</span>
              </div>
            </div>
          </RailSection>

          <RailSection title="与后续阶段的关系">
            <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>→ 缺件检测：拿正文里的类型与日期判断</div>
              <div>→ 委托合同生成：抽当事人/标的/管辖填模板</div>
              <div>→ 起诉条件：核合同条款、利率、逾期天数</div>
            </div>
          </RailSection>
        </WorkCard>
      </div>

      <MarkdownDrawer fileName={viewing} onClose={() => setViewing(null)} />

      <FieldDrawer
        picked={editing}
        onClose={() => setEditing(null)}
        overrides={overrides}
        onSave={(key, value) => setOverrides((prev) => ({ ...prev, [key]: value }))}
      />
    </div>
  )
}

/** 「转换问题」里的短文件名 → 正式文档名（找不到就原样传，抽屉里会显示无样本） */
function findDocName(short: string): string {
  return DEMO_UNDERSTAND_DOCS.find((d) => d.fileName.startsWith(short))?.fileName ?? short
}
