/**
 * 「AI 实际读到的内容」预览：`POST agent/skills/validate` 回传的 `preview` 原文。
 *
 * 为什么要给这一块：律师写的是「正文」，AI 读的是后端渲染出的 SKILL.md
 * （frontmatter + 固定 preamble + 正文）。不把渲染结果摊给作者看，他就无法
 * 判断自己写的东西会不会被当成别的指令——预览是「所见即所读」的唯一证据。
 */

export function SkillPreview({ preview }: { preview: string }) {
  if (!preview) return null
  return (
    <div className="mt-3">
      <p className="mb-1 text-[11px] text-muted-foreground">AI 实际读到的内容</p>
      <pre className="max-h-56 overflow-auto rounded-[8px] border border-border bg-secondary/40 p-2.5 font-mono text-[11px] leading-relaxed break-all whitespace-pre-wrap text-foreground">
        {preview}
      </pre>
    </div>
  )
}
