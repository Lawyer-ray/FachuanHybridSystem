/** 合同要素的一行「键 — 值」：值右对齐、可断行（长编号/地址不撑破两列栅格） */
export function MetaRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border-light py-[5px] text-xs last:border-b-0">
      <span className="flex-none text-[11px] text-muted-foreground">{k}</span>
      <span className="min-w-0 text-right font-[560] break-all tabular-nums">{v}</span>
    </div>
  )
}
