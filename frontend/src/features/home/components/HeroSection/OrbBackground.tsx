/**
 * OrbBackground - 动态光斑背景组件
 * @module features/home/components/HeroSection/OrbBackground
 *
 * 实现三个动态光斑，使用 Framer Motion 漂浮动画
 * Requirements: 2.2
 */

import { motion } from 'framer-motion'

import { orbAnimation } from '../../constants'

interface OrbConfig {
  /** 光斑颜色 CSS 变量 */
  color: string
  /** 光斑大小 */
  size: string
  /** 初始位置 */
  position: { top?: string; left?: string; right?: string; bottom?: string }
  /** 动画延迟因子 */
  delay: number
  /** 模糊程度 */
  blur: string
  /** 透明度 */
  opacity: number
}

const orbs: OrbConfig[] = [
  {
    color: 'var(--home-orb-purple)',
    size: '500px',
    position: { top: '10%', left: '15%' },
    delay: 0,
    blur: '120px',
    opacity: 0.6,
  },
  {
    color: 'var(--home-orb-cyan)',
    size: '400px',
    position: { top: '30%', right: '10%' },
    delay: 1,
    blur: '100px',
    opacity: 0.5,
  },
  {
    color: 'var(--home-orb-pink)',
    size: '350px',
    position: { bottom: '15%', left: '30%' },
    delay: 2,
    blur: '90px',
    opacity: 0.5,
  },
]

export function OrbBackground() {
  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden="true"
    >
      {orbs.map((orb, index) => {
        const animation = orbAnimation(orb.delay)
        return (
          <motion.div
            key={index}
            className="absolute rounded-full"
            style={{
              width: orb.size,
              height: orb.size,
              background: `radial-gradient(circle, ${orb.color} 0%, transparent 70%)`,
              filter: `blur(${orb.blur})`,
              opacity: orb.opacity,
              ...orb.position,
            }}
            animate={animation.animate}
            transition={animation.transition}
          />
        )
      })}
    </div>
  )
}
