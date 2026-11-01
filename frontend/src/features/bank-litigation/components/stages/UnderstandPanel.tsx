/**
 * ② 读懂 —— 每份材料自动转成 markdown，律师与 AI 读同一份正文
 *
 * 为什么这阶段单独成一页：后面所有判断（缺什么、能不能立案、条款说什么）
 * 都建立在「机器读到了字」之上。转不出来，后面全是猜。
 * 所以这里展示的是**转换质量**：用什么方法转的、转出多少字、摘录长什么样。
 */

import { FileText } from 'lucide-react'

import { useState } from 'react'

import { DEMO_UNDERSTAND_DOCS, DEMO_UNDERSTAND_FIELDS, DEMO_UNDERSTAND_ISSUES } from '../demo-data'
import { ActionButton, InsetBlock, KeyValueRow, Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { DetailDrawer } from './DetailDrawer'
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
  const totalChars = DEMO_UNDERSTAND_DOCS.reduce((n, d) => n + d.chars, 0)
  const highCount = DEMO_UNDERSTAND_DOCS.filter((d) => d.quality === 'high').length
  const medCount = DEMO_UNDERSTAND_DOCS.filter((d) => d.quality === 'medium').length

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
          {DEMO_UNDERSTAND_DOCS.map((d) => (
            <WorkCard key={d.fileName} padded={false}>
              <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
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
                      <ActionButton sm title="只重转这一份">
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

          {/* 关键字段抽取 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="抽取到的关键字段" hint="从 markdown 正文里抽，不靠文件名" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_UNDERSTAND_FIELDS.map((f) => (
                <li key={`${f.doc}-${f.field}`} className="flex items-center gap-3 px-5 py-2">
                  <span className="w-[84px] flex-none text-[10.5px] text-muted-foreground">{f.doc}</span>
                  <span className="w-[92px] flex-none text-[11.5px] text-secondary-foreground">{f.field}</span>
                  <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium" title={f.value}>{f.value}</span>
                  <span className="w-[120px] flex-none truncate text-[10px] text-muted-foreground" title={f.source}>{f.source}</span>
                  <span className="w-[44px] flex-none text-right text-[10.5px] tabular-nums"
                    style={{color: f.confidence >= 0.95 ? undefined : 'var(--status-yellow)'}}>
                    {(f.confidence * 100).toFixed(0)}%
                  </span>
                </li>
              ))}
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
    </div>
  )
}

/** markdown 全文抽屉：能看完整正文，也能换转换方法重转 */
function MarkdownDrawer({ fileName, onClose }: { fileName: string | null; onClose: () => void }) {
  const doc = fileName ? DEMO_UNDERSTAND_DOCS.find((d) => d.fileName === fileName) : null

  return (
    <DetailDrawer
      open={doc != null}
      onClose={onClose}
      width={640}
      title={doc?.fileName ?? ''}
      subtitle={doc ? `${doc.type} · ${doc.pages} 页 · ${doc.chars.toLocaleString()} 字` : undefined}
      badge={doc ? <Pill tone={doc.quality === 'high' ? 'green' : 'yellow'}>{doc.method}</Pill> : null}
      footer={
        doc ? (
          <>
            <ActionButton dark onClick={onClose}>
              确认无误
            </ActionButton>
            <ActionButton onClick={onClose}>换 OCR 重转</ActionButton>
            <ActionButton onClick={onClose}>下载 markdown</ActionButton>
          </>
        ) : null
      }
    >
      {doc ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="转换方法">{doc.method}</KeyValueRow>
            <KeyValueRow label="提取字数">{doc.chars.toLocaleString()} 字</KeyValueRow>
            <KeyValueRow label="质量评级">
              <span className={doc.quality === 'high' ? 'text-status-green' : 'text-status-yellow'}>
                {doc.quality === 'high' ? '高保真 · 可直接抽取' : '需复核 · 建议对照原图'}
              </span>
            </KeyValueRow>
          </dl>

          <div>
            <div className="mb-1.5 text-[10.5px] text-muted-foreground">markdown 正文</div>
            <InsetBlock className="bg-secondary/20">
              <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap font-mono text-[10.5px] leading-[1.75] text-secondary-foreground">
                {doc.excerpt}
              </pre>
            </InsetBlock>
          </div>

          <InsetBlock className="border-status-blue/40 bg-status-blue-bg/50">
            <div className="text-[10.5px] leading-[1.65] text-muted-foreground">
              后续「缺件检测」「委托合同生成」「起诉条件校验」都读这份正文，
              与律师看到的完全一致。
            </div>
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}
