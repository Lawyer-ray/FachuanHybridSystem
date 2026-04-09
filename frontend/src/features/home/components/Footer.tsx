/**
 * Footer - 页脚组件
 * @module features/home/components/Footer
 *
 * 显示链接列表和版权信息
 * Requirements: 8.1, 8.2, 8.3
 */

import { motion } from 'framer-motion'
import { Github, Mail } from 'lucide-react'

import { cn } from '@/lib/utils'

// ============================================================================
// 类型定义
// ============================================================================

interface FooterProps {
  className?: string
}

// ============================================================================
// 链接数据
// ============================================================================

const FOOTER_LINKS = [
  {
    icon: Github,
    label: 'GitHub',
    href: 'https://github.com/your-repo/fachuanai',
    external: true,
  },
  {
    icon: Mail,
    label: '联系我们',
    href: 'mailto:contact[at]fachuanai.com',
    external: true,
  },
]

// ============================================================================
// 动画链接组件
// ============================================================================

interface AnimatedFooterLinkProps {
  icon: React.ElementType
  label: string
  href: string
  external?: boolean
}

function AnimatedFooterLink({ icon: Icon, label, href, external }: AnimatedFooterLinkProps) {
  return (
    <motion.a
      href={href}
      target={external ? '_blank' : undefined}
      rel={external ? 'noopener noreferrer' : undefined}
      className={cn(
        'group relative flex items-center gap-2 text-sm text-gray-400',
        'transition-colors duration-200',
        'hover:text-cyan-400'
      )}
      whileHover={{ y: -2 }}
      transition={{ type: 'spring', stiffness: 400, damping: 17 }}
    >
      <Icon className="h-4 w-4" />
      <span className="relative">
        {label}
        {/* 下划线动画 */}
        <motion.span
          className="absolute -bottom-0.5 left-0 h-[1.5px] w-full origin-left bg-cyan-400"
          initial={{ scaleX: 0 }}
          whileHover={{ scaleX: 1 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
        />
      </span>
    </motion.a>
  )
}

// ============================================================================
// 主组件
// ============================================================================

export function Footer({ className }: FooterProps) {
  const currentYear = new Date().getFullYear()

  return (
    <footer
      className={cn(
        'border-t border-gray-800 bg-gray-950 py-8',
        className
      )}
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px]">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className={cn(
            'flex flex-col items-center gap-6',
            // 桌面端：水平布局
            'md:flex-row md:justify-between'
          )}
        >
          {/* 链接列表 */}
          <nav className="flex flex-wrap items-center justify-center gap-6">
            {FOOTER_LINKS.map((link) => (
              <AnimatedFooterLink
                key={link.label}
                icon={link.icon}
                label={link.label}
                href={link.href}
                external={link.external}
              />
            ))}
          </nav>

          {/* 版权信息 */}
          <p className="text-center text-sm text-gray-500">
            © {currentYear} 法穿AI. All rights reserved.
          </p>
        </motion.div>
      </div>
    </footer>
  )
}
