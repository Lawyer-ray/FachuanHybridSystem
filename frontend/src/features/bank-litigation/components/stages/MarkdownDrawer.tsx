/**
 * markdown 全文抽屉：三视图切换 + 换一种方法真重转
 *
 * 之前底部只有个「换 OCR 重转」按钮，点下去抽屉就关了 —— 律师看不到换方法之后
 * 到底改了什么，也就不会相信重转真的发生过。这里把方法做成可选项，
 * 选完当场地走一遍重转进度并给出结论，日志逐行出现。
 */

import { useState } from 'react'

import { DEMO_UNDERSTAND_DOCS, DEMO_X1_CONVERT_METHODS } from '../demo-data'
import { ActionButton, InsetBlock, KeyValueRow, Pill } from '../ui'
import type { ActionStep } from './use-stage-action'
import { cn } from '@/lib/utils'
import { DetailDrawer } from './DetailDrawer'
import { MarkdownDoc, type MarkdownView } from './MarkdownDoc'
import { useStageAction } from './use-stage-action'

/** 一份文档重转：把选中的方法写成剧本，走一遍与全量转换同样的进度 */
function reconvertSteps(doc: string, methodName: string, ms: number): ActionStep[] {
  return [
    { text: `锁定 ${doc} 的原始页`, ms: 400, parallel: ['读取源文件', '回读页码区间'] },
    { text: `切换转换方法为「${methodName}」`, ms: 500, fixed: true },
    {
      text: `${doc} · ${methodName} 重转中`,
      ms,
      retry: { times: 1, delay: 800, reason: '第 4 页表格线断裂，重新切分单元格' },
    },
    { text: '重建 markdown 段落与表格', ms: 700 },
    { text: '重抽关键字段并比对旧值', ms: 600, parallel: ['合同条款', '还款数据', '当事人信息'] },
  ]
}

export function MarkdownDrawer({ fileName, onClose }: { fileName: string | null; onClose: () => void }) {
  const doc = fileName ? DEMO_UNDERSTAND_DOCS.find((d) => d.fileName === fileName) : null
  const [view, setView] = useState<MarkdownView>('render')
  /** 当前用的转换方法（重转后可切到别的）；null = 还没选过，用这份原本的方法 */
  const [method, setMethod] = useState<string | null>(null)
  const defaultMethod = DEMO_X1_CONVERT_METHODS.find((m) => m.name === doc?.method) ?? DEMO_X1_CONVERT_METHODS[0]
  const activeMethod = DEMO_X1_CONVERT_METHODS.find((m) => m.key === method) ?? defaultMethod

  const reconvert = useStageAction({
    steps: doc
      ? reconvertSteps(doc.fileName, activeMethod?.name ?? doc.method, activeMethod?.ms ?? 900)
      : [{ text: '无文档', ms: 200, fixed: true }],
    // 演示不落盘：toSummary 只有 run() 返回非 undefined 时才被调到，借 run() 传出结论
    run: () => {
      if (!doc) return Promise.resolve(undefined)
      return Promise.resolve(`${doc.fileName} 已用「${activeMethod?.name ?? doc.method}」重转完成`)
    },
    toSummary: (text) => text ?? '',
  })

  const running = reconvert.phase === 'running' || reconvert.phase === 'awaiting'

  return (
    <DetailDrawer
      open={doc != null}
      onClose={onClose}
      width={640}
      title={doc?.fileName ?? ''}
      subtitle={doc ? `${doc.type} · ${doc.pages} 页 · ${doc.chars.toLocaleString()} 字` : undefined}
      badge={doc ? <Pill tone={doc.quality === 'high' ? 'green' : 'yellow'}>{activeMethod?.name ?? doc.method}</Pill> : null}
      footer={
        doc ? (
          <>
            <ActionButton dark onClick={onClose}>
              确认无误
            </ActionButton>
            <ActionButton dark={reconvert.phase === 'awaiting'} onClick={reconvert.confirm} disabled={!reconvert.confirmText}>
              确认并继续
            </ActionButton>
            <ActionButton onClick={onClose}>下载 markdown</ActionButton>
          </>
        ) : null
      }
    >
      {doc ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="转换方法">{activeMethod?.name ?? doc.method}</KeyValueRow>
            <KeyValueRow label="提取字数">{doc.chars.toLocaleString()} 字</KeyValueRow>
            <KeyValueRow label="质量评级">
              <span className={doc.quality === 'high' ? 'text-status-green' : 'text-status-yellow'}>
                {doc.quality === 'high' ? '高保真 · 可直接抽取' : '需复核 · 建议对照原图'}
              </span>
            </KeyValueRow>
          </dl>

          <MarkdownDoc fileName={doc.fileName} markdown={doc.excerpt} view={view} onViewChange={setView} />

          {/* 换转换方法重转：选方法 → 走一遍进度 → 出结论 */}
          <InsetBlock>
            <div className="flex items-center justify-between">
              <span className="text-[10.5px] font-medium">换一种方法重转</span>
              {reconvert.phase === 'done' ? <Pill tone="green">已重转</Pill> : null}
              {reconvert.phase === 'failed' ? <Pill tone="red">失败</Pill> : null}
            </div>

            <div className="mt-1.5 grid grid-cols-2 gap-1.5">
              {DEMO_X1_CONVERT_METHODS.map((m) => {
                const active = m.key === activeMethod?.key
                return (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => setMethod(m.key)}
                    aria-pressed={active}
                    className={cn(
                      'rounded-[7px] border px-2 py-1.5 text-left transition-colors',
                      active
                        ? 'border-foreground bg-secondary/60'
                        : 'border-border-light bg-card hover:border-input hover:bg-secondary/40',
                    )}
                  >
                    <div className="text-[11px] font-medium">{m.name}</div>
                    <div className="mt-0.5 text-[9.5px] leading-[1.5] text-muted-foreground">{m.desc}</div>
                  </button>
                )
              })}
            </div>

            <div className="mt-2 flex items-center gap-2">
              <ActionButton sm dark disabled={running} onClick={() => void reconvert.execute()}>
                {running ? `重转中 ${reconvert.percent}%` : '用这个方法重转'}
              </ActionButton>
              <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground">
                {running ? reconvert.progress || '等待确认' : (activeMethod?.best ?? '')}
              </span>
            </div>

            {reconvert.phase === 'running' ? (
              <div className="mt-1.5 h-[4px] overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-foreground transition-[width] duration-300"
                  style={{ width: `${reconvert.percent}%` }}
                />
              </div>
            ) : null}

            {reconvert.phase === 'awaiting' ? (
              <p className="mt-1.5 rounded-[6px] border border-status-yellow/50 bg-status-yellow-bg/60 px-2 py-1.5 text-[10px] leading-[1.6] text-muted-foreground">
                {reconvert.confirmText}
              </p>
            ) : null}

            {reconvert.phase === 'done' ? (
              <p className="mt-1.5 text-[10.5px] text-status-green">{reconvert.summary}</p>
            ) : null}

            {reconvert.log.length > 0 ? (
              <ul className="mt-1.5 flex max-h-[110px] flex-col gap-[2px] overflow-y-auto">
                {reconvert.log.map((l, i) => (
                  <li key={`${l.at}-${i}`} className="flex items-start gap-2 text-[9.5px] leading-[1.5]">
                    <span className="flex-none tabular-nums text-muted-foreground">{l.at}</span>
                    <span
                      className={cn(
                        'min-w-0 flex-1 break-words',
                        l.kind === 'ok'
                          ? 'text-status-green'
                          : l.kind === 'warn'
                            ? 'text-status-yellow'
                            : l.kind === 'error'
                              ? 'text-status-red'
                              : l.kind === 'sub'
                                ? 'text-muted-foreground'
                                : 'text-secondary-foreground',
                      )}
                    >
                      {l.text}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </InsetBlock>

          <InsetBlock className="border-status-blue/40 bg-status-blue-bg/50">
            <div className="text-[10.5px] leading-[1.65] text-muted-foreground">
              后续「缺件检测」「委托合同生成」「起诉条件校验」都读这份正文，与律师看到的完全一致。
            </div>
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}
