import { cn } from '@/lib/utils'

/**
 * 视图 tab：文字 + 下划线，**不用盒子**。
 *
 * 一排「选中项带边框、未选中透明边框」的按钮是这一栏看起来乱的主要原因——两个盒子
 * 并排时，人眼会先去读边框而不是文字。下划线只占 1.5px，而且只有一项有。
 */
export function ViewTab({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'flex-none border-b-[1.5px] px-1.5 pb-1 text-[11px] transition-colors',
        active
          ? 'border-foreground font-medium text-foreground'
          : 'border-transparent text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}
