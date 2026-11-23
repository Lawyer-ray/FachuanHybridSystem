/**
 * ① 收案 —— 客户发来一整包扫描件，系统自动拆成单份材料
 *
 * 这一阶段回答一个问题：**客户到底给了什么、系统认出了几份、哪几份认不准。**
 * 所以版面是「拆分结果表 + 逐份状态」，不是统计报表。
 *
 * 每一处结论都点得开：
 *   · 行 → 抽屉：扫描件可翻页、识别框虚线标出、「为什么是 98%」展开成 4 个因子
 *   · 源文件行 → 行内下载/剔除（剔掉的源文件不再算页数）
 *   · 顶部「追加材料」→ 客户链接 / 本地上传 / 邮箱拉取 三种入口
 */


import { DEMO_INTAKE_SEGMENTS, DEMO_INTAKE_SOURCES } from '../demo-data'
import { useState } from 'react'
import { StageActionCard } from './StageActionCard'
import { AppendMaterialDrawer } from './AppendMaterialDrawer'
import { IntakeSourceCard } from './IntakeSourceCard'
import { IntakeEventFlow, IntakeSourceSummaryCard, SegmentResultTable } from './intake/IntakeTables'
import { IntakeRail } from './intake/IntakeRail'
import { MaterialDrawer } from './MaterialDrawer'
import { useStageAction } from './use-stage-action'
import { StatCell, StatStrip } from '../ui'

export function IntakePanel() {
  /** 点开的那一份材料（null = 抽屉关闭） */
  const [picked, setPicked] = useState<number | null>(null)
  /** 已排除的材料 seq（演示：把「手写便签」排除掉） */
  const [excluded, setExcluded] = useState<Set<number>>(new Set())
  /** 已从整包里剔除的源文件 */
  const [dropped, setDropped] = useState<Set<string>>(new Set())
  /** 追加材料弹窗 */
  const [appendOpen, setAppendOpen] = useState(false)

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
  /** 页数 = 剩下源文件的页数之和（剔除源文件会实时反映到这里） */
  const pages = DEMO_INTAKE_SOURCES.filter((f) => !dropped.has(f.name)).reduce((n, f) => n + f.pages, 0)

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
        <StatCell label={dropped.size > 0 ? `总页数（已剔 ${dropped.size} 个源文件）` : '总页数'} value={`${pages}`} />
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
          <IntakeSourceSummaryCard />

          {/* 源文件清单：每行都能单独下载 / 剔除 */}
          <IntakeSourceCard
            dropped={dropped}
            pages={pages}
            onToggle={(name) =>
              setDropped((prev) => {
                const next = new Set(prev)
                if (next.has(name)) next.delete(name)
                else next.add(name)
                return next
              })
            }
          />

          <IntakeEventFlow />

          <SegmentResultTable
            segmentCount={total}
            excludedSeqs={excluded}
            onPick={setPicked}
            onAppend={() => setAppendOpen(true)}
          />
        </div>

        <IntakeRail droppedCount={dropped.size} />
      </div>

      {/* 材料详情抽屉：常驻挂载，key 取当前材料，换一份就从第 1 页、折叠态重来 */}
      <MaterialDrawer
        key={picked ?? 'none'}
        seq={picked}
        onClose={() => setPicked(null)}
        excluded={excluded}
        onExclude={(seq) => {
          setExcluded((prev) => new Set(prev).add(seq))
          setPicked(null)
        }}
      />

      <AppendMaterialDrawer open={appendOpen} onClose={() => setAppendOpen(false)} />
    </div>
  )
}
