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

import { useState } from 'react'

import { DEMO_UNDERSTAND_DOCS } from '../demo-data'
import { StatCell, StatStrip } from '../ui'
import { FieldDrawer } from './FieldDrawer'
import { MarkdownDrawer } from './MarkdownDrawer'
import { StageActionCard } from './StageActionCard'
import { BatchBar } from './understand/BatchBar'
import { UnderstandRail } from './understand/UnderstandRail'
import { ConvertIssuesTable, DocConversionList, ExtractedFieldTable } from './understand/UnderstandTables'
import { useStageAction } from './use-stage-action'

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

          <BatchBar
            checkedCount={checked.size}
            total={DEMO_UNDERSTAND_DOCS.length}
            allChecked={allChecked}
            onToggleAll={() =>
              setChecked(allChecked ? new Set() : new Set(DEMO_UNDERSTAND_DOCS.map((d) => d.fileName)))
            }
            batch={batchRun}
            onRun={() => void batchRun.execute()}
          />

          <DocConversionList checkedNames={checked} onToggle={toggle} onOpen={setViewing} />

          <ConvertIssuesTable onOpen={setViewing} />

          <ExtractedFieldTable overrides={overrides} onEdit={setEditing} />
        </div>

        <UnderstandRail />
      </div>

      {/* 两个抽屉都常驻挂载：key 取当前条目，换一份 / 换一个字段就是换实例，
          上一份的视图与方法选择、上一行的改正草稿都不会跟过来 */}
      <MarkdownDrawer key={viewing ?? 'none'} fileName={viewing} onClose={() => setViewing(null)} />

      <FieldDrawer
        key={editing ? `${editing.doc}-${editing.field}` : 'none'}
        picked={editing}
        onClose={() => setEditing(null)}
        overrides={overrides}
        onSave={(key, value) => setOverrides((prev) => ({ ...prev, [key]: value }))}
      />
    </div>
  )
}
