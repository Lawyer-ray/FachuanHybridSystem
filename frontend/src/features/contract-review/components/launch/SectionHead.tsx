/**
 * 抽屉内的分节标题：序号圆点 + 标题 + 右侧徽标/注记。
 *
 * 三段（①立场 ②审查内容 ③特别交代）原来各抄一遍这段 8 行 JSX，序号一改要
 * 改三处；抽出来后「第几步」只在调用处写一次。
 */
export function SectionHead({
  index,
  title,
  badge,
  note,
}: {
  index: number
  title: string
  /** 右侧强调徽标（如「决定全部建议方向」） */
  badge?: string
  /** 右侧弱文案（如「选填」），与 badge 二选一 */
  note?: string
}) {
  return (
    <div className="mb-2.5 flex items-center gap-2">
      <span className="grid size-[17px] flex-none place-items-center rounded-full bg-secondary text-[10px] font-bold text-secondary-foreground">
        {index}
      </span>
      <span className="text-[12.5px] font-[650]">{title}</span>
      {badge && (
        <span className="ml-auto rounded-[5px] bg-status-yellow-bg px-1.5 py-0.5 text-[10px] font-[650] text-[#a16207]">
          {badge}
        </span>
      )}
      {note && <span className="ml-auto text-[11px] text-muted-foreground/70">{note}</span>}
    </div>
  )
}
