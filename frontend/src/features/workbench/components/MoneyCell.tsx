/** 金额四格之一：`hot` 只给「未收款」用（红字），其余保持中性底色 */
export function MoneyCell({ label, value, hot }: { label: string; value: string; hot?: boolean }) {
  return (
    <div className="min-w-0 rounded-[11px] bg-secondary px-[11px] pt-2 pb-[7px]">
      <div className="text-[10.5px] whitespace-nowrap text-muted-foreground">{label}</div>
      <div className={'mt-px text-[15px] font-bold tracking-[-0.01em] truncate tabular-nums ' + (hot ? 'text-status-red' : '')}>
        {value}
      </div>
    </div>
  )
}
