/**
 * ② 读懂的左列展示块：逐份文档卡 / 转换时发现的问题 / 抽取到的关键字段。
 *
 * 三块都是只读呈现 + 向上回调（开全文抽屉、开字段校对），
 * 抽出来后 `UnderstandPanel` 只剩「动作卡 → 统计 → 左侧组件 + 右栏 → 两个抽屉」。
 */

import { FileText } from 'lucide-react'

import { ClickableRow } from '../../ClickableRow'
import { DEMO_UNDERSTAND_DOCS, DEMO_UNDERSTAND_FIELDS, DEMO_UNDERSTAND_ISSUES } from '../../demo-data'
import { ActionButton, InsetBlock, Pill, SectionTitle, WorkCard } from '../../ui'
import { METHOD_HINT } from './convert-methods'

/** 逐份文档卡：转换方法、质量标记、markdown 预览（点「查看全文」开抽屉） */
export function DocConversionList({
  checkedNames,
  onToggle,
  onOpen,
}: {
  /** 已勾选的文件名（批量重转用） */
  checkedNames: Set<string>
  onToggle: (fileName: string) => void
  onOpen: (fileName: string) => void
}) {
  return (
    <>
      {DEMO_UNDERSTAND_DOCS.map((d) => (
        <WorkCard key={d.fileName} padded={false}>
          <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
            <input
              type="checkbox"
              aria-label={`选中 ${d.fileName}`}
              checked={checkedNames.has(d.fileName)}
              onChange={() => onToggle(d.fileName)}
              className="size-3.5 flex-none accent-foreground"
            />
            <FileText className="size-3.5 flex-none text-muted-foreground" />
            <SectionTitle title={d.fileName} hint={d.type} className="w-full" />
            <div className="flex flex-none items-center gap-1.5">
              <Pill tone="blue">{d.method}</Pill>
              <Pill tone={d.quality === 'high' ? 'green' : 'yellow'}>
                {d.quality === 'high' ? '高保真' : '需复核'}
              </Pill>
              <ActionButton sm onClick={() => onOpen(d.fileName)}>
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
    </>
  )
}

/** 转换时发现的问题：每条给出影响与可执行的动作 */
export function ConvertIssuesTable({ onOpen }: { onOpen: (fileName: string) => void }) {
  return (
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
                  <ActionButton sm title="只重转这一份" onClick={() => onOpen(findDocName(i.doc))}>
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
  )
}

/** 抽取到的关键字段：每行点开可校对，改过的打「已改」 */
export function ExtractedFieldTable({
  overrides,
  onEdit,
}: {
  /** 已人工改正的字段值，键是 `${doc}-${field}` */
  overrides: Record<string, string>
  onEdit: (picked: { doc: string; field: string }) => void
}) {
  return (
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
              <ClickableRow
                key={key}
                onClick={() => onEdit({ doc: f.doc, field: f.field })}
                className="flex items-center gap-3 px-5 py-2"
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
              </ClickableRow>
            )
          })}
        </ul>
      </WorkCard>
  )
}

/** 「转换问题」里的短文件名 → 正式文档名（找不到就原样传，抽屉里会显示无样本） */
function findDocName(short: string): string {
  return DEMO_UNDERSTAND_DOCS.find((d) => d.fileName.startsWith(short))?.fileName ?? short
}
