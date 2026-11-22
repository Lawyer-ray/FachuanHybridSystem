/**
 * 「综合结论」卡：把各栏答案收敛成一份可引用的合成稿。
 *
 * ## 必须交出去的三样东西
 *
 * - **参与栏**（`lanesUsed`）：这份稿子是在哪几份答案上合成的；
 * - **被丢弃的栏**（`dropped` + 原因）：空正文 / 本轮失败 / 超长被截。不显示它们，
 *   「少了一栏」看起来就像聚合者漏读了——那是要律师自己去追查的假象；
 * - **来源锚点**（`citations`：栏名 · 引文）与**未核验项**（`unverified`）。
 *   未核验 = 本轮检索**没核上**，不是「引用是错的」——文案必须说清这一层，否则律师
 *   会把「没查到」读成「伪造」。
 *
 * ## 空正文不出卡
 *
 * `text` 为空 = 这次合成什么也没产出。挂一张标题下的空卡等于让律师以为「综合结论
 * 就是没有结论」；调用方只在有合成记录时挂载本组件，这里再兜一次空正文。
 *
 * ## Markdown 渲染复用 assistant 正文那套
 *
 * 合成稿是 Markdown（标题/列表/引用），必须与气泡同一渲染器（`AssistantMarkdown`：
 * react-markdown + gfm + 代码高亮，且不执行原始 HTML）。自己写一套解析会在表格与
 * 代码块上先漂移。
 */

import { AssistantMarkdown } from '../AssistantMarkdown'
import type { SynthesisView } from '../../domain'

export function SynthesisCard({ synthesis }: { synthesis: SynthesisView }) {
  if (!synthesis.text.trim()) return null

  const { prompt = 0, completion = 0, total = prompt + completion } = synthesis.tokens
  return (
    <section
      data-testid="synthesis-card"
      aria-label="综合结论"
      className="min-w-0 rounded-[8px] border border-border bg-secondary/30 p-2 text-xs"
    >
      <header className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="flex-none font-medium">综合结论</span>
        {synthesis.model && (
          <span className="min-w-0 truncate text-[10px] text-muted-foreground" data-testid="synthesis-model" title={synthesis.model}>
            {synthesis.model}
          </span>
        )}
        {total > 0 && (
          <span className="flex-none text-[10px] text-muted-foreground tabular-nums" data-testid="synthesis-tokens">
            tokens {total}（提示 {prompt} / 完成 {completion}）
          </span>
        )}
      </header>

      <div data-copilot-selection-root className="copilot-md mt-1 break-words text-[13px] leading-relaxed">
        <AssistantMarkdown text={synthesis.text} streaming={false} />
      </div>

      <div className="mt-1.5 space-y-1 border-t border-border pt-1.5">
        {synthesis.lanesUsed.length > 0 && (
          <p className="text-[11px] text-muted-foreground" data-testid="synthesis-lanes">
            参与栏：{synthesis.lanesUsed.map((lane) => lane.label).join('、')}
          </p>
        )}

        {synthesis.dropped.length > 0 && (
          <p className="text-[11px] text-amber-600 dark:text-amber-500" data-testid="synthesis-dropped">
            未参与合成：
            {synthesis.dropped.map((dropped) => `${dropped.label}（${dropped.reason}）`).join('、')}
          </p>
        )}

        {synthesis.citations.length > 0 && (
          <div data-testid="synthesis-citations">
            <div className="text-[11px] font-medium text-muted-foreground">来源锚点（哪一栏引的，不是核验结果）</div>
            <ul className="mt-0.5 space-y-0.5">
              {synthesis.citations.map((citation, index) => (
                <li key={index} className="text-[11px]">
                  <span className="text-muted-foreground">{citation.label}</span> · {citation.quote}
                </li>
              ))}
            </ul>
          </div>
        )}

        {synthesis.unverified.length > 0 && (
          <div data-testid="synthesis-unverified">
            {/* 「没核上」≠「错」：这里只说本轮检索没兜住，不指控引用造假 */}
            <div className="text-[11px] font-medium text-muted-foreground">未核验（本轮检索没兜住，不等于引用有误）</div>
            <ul className="mt-0.5 space-y-0.5">
              {synthesis.unverified.map((item, index) => (
                <li key={index} className="text-[11px]">
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}
