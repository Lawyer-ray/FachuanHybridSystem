import { cn } from '@/lib/utils'

/**
 * 法穿 SI Copilot 品牌字标（全站唯一一处）。
 *
 * 为什么抽成组件：登录后的 navbar 与**免登录的客户上传页**都要露出品牌，
 * 而客户上传页（/u/:token）是律师发给外部客户看的门面——一个连产品名都没有的
 * 裸表单会让客户以为是钓鱼页面。抽成组件保证两处字标永远一致，改一次全站生效。
 *
 * 只出内容、不管容器与跳转：登录后由 navbar 用 <Link> 包（回首页），
 * 免登录页没有首页可回，直接裸用。
 */
export function BrandMark({ size = 'sm', className }: { size?: 'sm' | 'lg'; className?: string }) {
  return (
    <span
      className={cn(
        'flex flex-none items-center whitespace-nowrap tracking-[-0.01em]',
        size === 'sm' ? 'text-[14px]' : 'text-[16px]',
        className,
      )}
    >
      <span className="font-bold text-foreground">法穿</span>
      <span className={cn('ml-1 font-medium text-muted-foreground', size === 'sm' ? 'text-[12.5px]' : 'text-[13.5px]')}>
        SI Copilot
      </span>
    </span>
  )
}
