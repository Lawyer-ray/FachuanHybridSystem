import { Info } from 'lucide-react'

/**
 * 「分歧自动裁定未生效」的常驻提示条（阅读器顶部，跨段可见）。
 *
 * ## 为什么需要它
 *
 * 「分歧自动裁定」在设置菜单里**默认勾着**，而部署侧总闸（`OCR_JUDGE_ENABLED`）默认关着、
 * Key 默认空。于是律师看到的是：开关是勾的、分歧一条条全进人工、界面一个字都不解释——
 * 唯一的结论只能是「这功能坏了」。而后端从 v27.25.4 起就已经把原因（`reason`：
 * `gate_off` / `missing_key`）写进 summary 了，只是没人翻译成一句话。
 *
 * ## 为什么放在阅读器顶部，而不是分歧内联块里
 *
 * 分歧内联块按 `seg.refs` 过滤、没有分歧的段根本不渲染；而这件事是**卷级**的
 * （整卷一条都没判），写在段级组件里会出现「这一屏有、翻一段就没了」的自相矛盾。
 *
 * ## 为什么是灰底而不是琥珀
 *
 * 这是事实陈述，不是错误，也不是待办。琥珀留给「建议复核」那种**要动作**的提示
 * （与 `SegmentQualityHint` 的分色口径一致）。染黄会让真正的失败提示贬值。
 */
export function JudgeGateHint({ notice }: { notice: string | null }) {
  if (!notice) return null
  return (
    <div
      data-judge-gate-hint
      className="flex min-h-[30px] flex-none items-start gap-1.5 border-b border-border bg-secondary/40 px-4 py-1.5 text-[11.5px] leading-snug text-muted-foreground max-[760px]:px-3"
    >
      <Info className="mt-0.5 size-3.5 flex-none" aria-hidden />
      <span className="min-w-0">{notice}</span>
    </div>
  )
}
