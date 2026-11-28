/**
 * 抽屉头部：标题 + 一段「技能是什么、它会怎样被 AI 看到」的说明。
 *
 * 文案必须与现状逐条对齐（旧版写「描述会在启用索引后进入系统提示」，把计划当成了
 * 承诺）。现在是：点名走 `/skill:` 展开、描述进系统提示的技能索引（只有 prompt /
 * native 后端注入）、正文由 AI 按需读取（CONTRACT §9）。
 */

import { Sparkles } from 'lucide-react'

import { SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

export function SkillDrawerHeader() {
  return (
    <SheetHeader>
      <SheetTitle className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 opacity-70" />
        技能
      </SheetTitle>
      <SheetDescription className="mt-1 text-[12px] leading-relaxed">
        技能是交给 AI 执行的做法说明，用 <code className="font-mono text-[11px]">/skill:名字</code> 点名使用；描述会作为技能索引进入系统提示（取决于所选后端），正文由 AI 按需读取。它
        <strong className="font-medium text-foreground">不会</strong>改变审批等级，启停从下一轮对话生效。
      </SheetDescription>
    </SheetHeader>
  )
}
