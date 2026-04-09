/**
 * HeroButtons - Hero 区域 CTA 按钮组
 * @module features/home/components/HeroSection/HeroButtons
 *
 * 实现主按钮和次按钮，带 hover 上移、发光和涟漪效果
 * Requirements: 2.6, 2.7
 */

import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Github } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface HeroButtonsProps {
  className?: string
}

interface Ripple {
  id: number
  x: number
  y: number
}

/**
 * 涟漪效果 Hook
 */
function useRipple() {
  const [ripples, setRipples] = useState<Ripple[]>([])

  const createRipple = useCallback((e: React.MouseEvent<HTMLElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const id = Date.now()

    setRipples((prev) => [...prev, { id, x, y }])

    setTimeout(() => {
      setRipples((prev) => prev.filter((r) => r.id !== id))
    }, 600)
  }, [])

  return { ripples, createRipple }
}

export function HeroButtons({ className }: HeroButtonsProps) {
  const primaryRipple = useRipple()
  const secondaryRipple = useRipple()

  return (
    <div className={cn('flex flex-wrap items-center justify-center gap-4', className)}>
      {/* 主按钮 - 立即体验 */}
      <motion.div
        whileHover={{ y: -2, scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        transition={{ type: 'spring', stiffness: 400, damping: 17 }}
      >
        <Button
          size="lg"
          className={cn(
            'relative h-12 px-8 text-base font-semibold overflow-hidden',
            'bg-gradient-to-r from-home-primary to-home-accent',
            'hover:from-home-primary/90 hover:to-home-accent/90',
            'text-white shadow-lg',
            // 发光效果
            'hover:shadow-[0_0_30px_rgba(139,92,246,0.5)]',
            'transition-shadow duration-300'
          )}
          onClick={(e) => {
            primaryRipple.createRipple(e)
            window.location.href = '/admin/dashboard'
          }}
        >
          立即体验
          {/* 涟漪效果 */}
          <AnimatePresence>
            {primaryRipple.ripples.map((ripple) => (
              <motion.span
                key={ripple.id}
                className="pointer-events-none absolute rounded-full bg-white/30"
                style={{ left: ripple.x, top: ripple.y }}
                initial={{ width: 0, height: 0, x: 0, y: 0, opacity: 0.5 }}
                animate={{ width: 200, height: 200, x: -100, y: -100, opacity: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
              />
            ))}
          </AnimatePresence>
        </Button>
      </motion.div>

      {/* 次按钮 - GitHub */}
      <motion.div
        whileHover={{ y: -2, scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        transition={{ type: 'spring', stiffness: 400, damping: 17 }}
      >
        <Button
          variant="outline"
          size="lg"
          className={cn(
            'relative h-12 px-8 text-base font-semibold overflow-hidden',
            'border-home-border bg-transparent',
            'text-home-text-muted hover:text-home-text',
            'hover:border-home-primary/50 hover:bg-home-primary/10',
            // 发光效果
            'hover:shadow-[0_0_20px_rgba(139,92,246,0.3)]',
            'transition-all duration-300'
          )}
          onClick={(e) => {
            secondaryRipple.createRipple(e)
            window.open('https://github.com/your-repo/fachuanai', '_blank')
          }}
        >
          <Github className="mr-2 size-5" />
          GitHub
          {/* 涟漪效果 */}
          <AnimatePresence>
            {secondaryRipple.ripples.map((ripple) => (
              <motion.span
                key={ripple.id}
                className="pointer-events-none absolute rounded-full bg-purple-500/30"
                style={{ left: ripple.x, top: ripple.y }}
                initial={{ width: 0, height: 0, x: 0, y: 0, opacity: 0.5 }}
                animate={{ width: 200, height: 200, x: -100, y: -100, opacity: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
              />
            ))}
          </AnimatePresence>
        </Button>
      </motion.div>
    </div>
  )
}
