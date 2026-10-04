import { COUNT_PILL } from '../ui'

/** 右栏卡片的头部：标题 + 计数小丸（今日卡 / 收件箱共用） */
export function CardHead({ title, count }: { title: string; count: string }) {
  return (
    <div className="flex items-center gap-2.5 px-4 pt-[15px] pb-1">
      <b className="text-[13.5px] font-semibold">{title}</b>
      <span className={COUNT_PILL}>{count}</span>
    </div>
  )
}
