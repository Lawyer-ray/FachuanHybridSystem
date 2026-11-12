/**
 * 非诉线 B · 跨境合同审查工作台：逐条审查 + 外国法条核验。
 *
 * 从 `nonlit-workbench.tsx` 按「一屏一个工作台」拆出，只搬移不改行为。
 * 法条核验的「三道规则闸 + 判断层」脚本仍是本屏自己的编排；四块真正的律师
 * 工作面（双语正文 / 法条依据 / 维度筛选 / 逐条采纳）在
 * nonlit/crossborder/CrossBorderViews，它们共享「当前选中修订」。
 */

import { cn } from '@/lib/utils'

import {
  DEMO_LAW_GATES,
  DEMO_TH_CONTRACT_REVISIONS,
  DEMO_VERIFY_LOG,
} from './demo-nonlit'
import { NonLitActionCard } from './nonlit-action-card'
import { Inset } from './nonlit/special/special-bits'
import { SectionHead, StatCell, StatStrip } from './nonlit/special/special-stat'
import { ForeignLawVerifyCard } from './nonlit/crossborder/ForeignLawVerifyCard'
import { CrossBorderViews } from './nonlit/crossborder/CrossBorderViews'
import { useNonLitAction } from './use-nonlit-action'
import { Card } from './ui'

export function CrossBorderWorkbench() {
  /** 逐条审查整份合同 */
  const review = useNonLitAction(
    [
      { text: '读取合同全文（3 语版本，9 条）', ms: 600, parallel: ['英文版', '中文版', '泰文版'] },
      { text: '识别我方立场：承租方（Lessee）', ms: 700 },
      {
        text: '逐条比对风险点',
        ms: 1400,
        retry: { times: 1, delay: 1000, reason: '泰文版排版异常，重新解析' },
      },
      { text: '检出 5 处需修订条款', ms: 700 },
      {
        text: '给每处挂法条依据',
        ms: 800,
        confirm: '5 处修订中 4 处有泰国法条支持，第 5 处「泰文优先」无外国法依据。是否保留为「需律师判断」？',
      },
      { text: '审查完成', ms: 400 },
    ],
    '检出 5 处风险：2 高 2 中 1 低，其中 4 处已挂泰国法条',
  )

  /** 法条核验：三道规则闸 + 判断层 */
  const verify = useNonLitAction(
    DEMO_LAW_GATES.map((g) => ({
      text: `规则闸 ${g.n} · ${g.name}（${g.ms} ms）`,
      ms: g.ms,
      ...(g.n === '02' ? { retry: { times: 1, delay: 900, reason: 'BARLC 接口超时' } } : {}),
    })),
    '4 道闸全部通过：法存在、有正文、条款号在范围内、条文支持该主张',
  )

  const highCount = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'high').length
  const midCount = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'mid').length
  const lowCount = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'low').length
  const verifiedCount = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.verified).length

  return (
    /* 这一张是**容器卡**，里面还要塞 7 张子卡：容器自己再画边框就成了三层同心矩形，
       所以这里按「无边框区段」处理（只用标题分隔），子卡各自是独立的卡。 */
    <Card className="border-0 bg-transparent px-0 py-0 shadow-none">
      <SectionHead title="跨境合同审查" hint="逐条审 + 外国法核验" />
      <StatStrip className="mt-2.5 grid-cols-2 sm:grid-cols-4">
        <StatCell label="风险条款" value={`${DEMO_TH_CONTRACT_REVISIONS.length}`} />
        <StatCell label="高 / 中 / 低" value={`${highCount}/${midCount}/${lowCount}`} />
        <StatCell label="已挂法条" value={`${verifiedCount}`} tone="green" />
        <StatCell label="核验闸" value={`${DEMO_LAW_GATES.length} 道`} tone="blue" />
      </StatStrip>

      <div className="mt-3.5 flex flex-col gap-2.5">
        <NonLitActionCard
          title="逐条审查合同"
          desc="按我方立场逐条比对风险点，每处修订都挂外国法依据。挂不上法条的不硬编，标成「需律师判断」。"
          actionLabel="开始审查"
          hint="9 条 · 约 4 秒"
          state={review}
        />
        <NonLitActionCard
          title="外国法条核验"
          desc="先过三道规则闸（法是否存在、有没有正文、条款号在不在范围内），才交给判断层比对语义。编造的法条在这三道闸上就死了。"
          actionLabel="核验法条"
          hint="4 道闸 · 约 5 秒"
          state={verify}
        />
      </div>

      {/* 核验日志 */}
      {verify.phase === 'done' ? (
        <div className="mt-3.5">
          <div className="mb-2 text-[11px] font-medium text-muted-foreground">核验日志</div>
          <Inset className="bg-secondary/25">
            <ul className="flex flex-col gap-[2px]">
              {DEMO_VERIFY_LOG.map((l) => (
                <li key={l.at} className="flex items-start gap-2 text-[10.5px] leading-[1.5]">
                  <span className="flex-none tabular-nums text-muted-foreground">{l.at}</span>
                  <span
                    className={cn(
                      'min-w-0 flex-1',
                      l.kind === 'ok' ? 'text-status-green' : l.kind === 'warn' ? 'text-status-yellow' : 'text-secondary-foreground',
                    )}
                  >
                    {l.text}
                  </span>
                </li>
              ))}
            </ul>
          </Inset>
        </div>
      ) : null}

      {/* 机器跑完之后律师真正要用的四块：双语正文 / 法条依据 / 维度筛选 / 逐条采纳。
          四块共享「当前选中修订」，见 nonlit/crossborder/CrossBorderViews。 */}
      <div className="mt-3.5">
        <ForeignLawVerifyCard />
      </div>

      <CrossBorderViews lawVerified={verify.phase !== 'idle'} />
    </Card>
  )
}
