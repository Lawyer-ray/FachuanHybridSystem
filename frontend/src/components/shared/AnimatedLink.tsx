/**
 * AnimatedLink - 带下划线动画的链接组件
 * @module components/shared/AnimatedLink
 */

import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface AnimatedLinkProps {
  href?: string
  onClick?: () => void
  children: React.ReactNode
  className?: string
  /** 下划线颜色 */
  underlineColor?: string
  /** 是否外部链接 */
  external?: boolean
}

export function AnimatedLink({
  href,
  onClick,
  children,
  className,
  underlineColor = 'currentColor',
  external = false,
}: AnimatedLinkProps) {
  const Component = href ? 'a' : 'button'

  return (
    <Component
      href={href}
      onClick={onClick}
      target={external ? '_blank' : undefined}
      rel={external ? 'noopener noreferrer' : undefined}
      className={cn(
        'group relative inline-flex items-center gap-1',
        'transition-colors duration-200',
        className
      )}
    >
      {children}
      {/* 下划线动画 */}
      <motion.span
        className="absolute -bottom-0.5 left-0 h-[2px] w-full origin-left"
        style={{ backgroundColor: underlineColor }}
        initial={{ scaleX: 0 }}
        whileHover={{ scaleX: 1 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      />
    </Component>
  )
}
