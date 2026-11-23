/** 程序节点：实心点=已结、空心粗环=在办，同阶段聚合 ×N */
export function StageNode({ stage, n, live, first }: { stage: string; n: number; live: boolean; first: boolean }) {
  return (
    <div className="flex flex-none items-center gap-[7px]">
      {!first && <span className={'mx-[7px] h-0.5 w-6 flex-none rounded-sm ' + (live ? 'bg-border' : 'bg-foreground')} />}
      <span
        className={
          'size-[11px] flex-none rounded-full border-2 ' +
          (live ? 'border-foreground bg-card shadow-[0_0_0_3px_rgba(24,24,27,0.09)]' : 'border-foreground bg-foreground')
        }
      />
      <b className="text-xs font-[620]">{stage}</b>
      {n > 1 && <span className="-ml-1 text-[10px] font-semibold text-muted-foreground/70 tabular-nums">×{n}</span>}
      <span className={'text-[10.5px] ' + (live ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
        {live ? '在办' : '已结'}
      </span>
    </div>
  )
}
