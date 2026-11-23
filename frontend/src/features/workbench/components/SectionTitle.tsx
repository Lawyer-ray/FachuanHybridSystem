/** 抽屉内的节标题（小字大写字距）：只在有内容时才渲染，空节连标题一起不出现 */
export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-6 pt-4 pb-2 text-[11px] font-[650] tracking-[0.09em] text-muted-foreground uppercase">
      {children}
    </div>
  )
}
