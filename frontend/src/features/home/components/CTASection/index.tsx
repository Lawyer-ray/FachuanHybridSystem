/**
 * CTASection - CTA 区域组件
 * @module features/home/components/CTASection
 *
 * 展示行动召唤区域，包含二维码、虚拟钱包打赏和 CTA 按钮
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
 */

import { motion } from 'framer-motion'
import { Github, Rocket, Copy, Check, Heart, Wallet, QrCode } from 'lucide-react'
import { useState, useCallback, useRef, useEffect } from 'react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { QR_CODES } from '../../constants'

// ============================================================================
// 类型定义
// ============================================================================

interface CTASectionProps {
  className?: string
}

interface WalletAddress {
  type: 'ethereum' | 'bitcoin'
  address: string
  label: string
  icon: string
}

// ============================================================================
// 常量
// ============================================================================

const WALLET_ADDRESSES: WalletAddress[] = [
  {
    type: 'ethereum',
    address: '0x97A219C06A682868BfC8E7b9Ef5c7A65140926432',
    label: 'Ethereum',
    icon: 'Ξ',
  },
  {
    type: 'bitcoin',
    address: 'bc1qm82nk0s5ukpk4e768tmaeclr8shdgw8a78qnyd',
    label: 'Bitcoin',
    icon: '₿',
  },
]

// ============================================================================
// 复制到剪贴板 Hook
// ============================================================================

function useCopyToClipboard(timeout: number = 2000) {
  const [copied, setCopied] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)

      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text)
        } else {
          const textArea = document.createElement('textarea')
          textArea.value = text
          textArea.style.position = 'fixed'
          textArea.style.left = '-999999px'
          document.body.appendChild(textArea)
          textArea.select()
          document.execCommand('copy')
          document.body.removeChild(textArea)
        }
        setCopied(true)
        timeoutRef.current = setTimeout(() => setCopied(false), timeout)
        return true
      } catch {
        return false
      }
    },
    [timeout]
  )

  return { copied, copy }
}

// ============================================================================
// 二维码卡片组件
// ============================================================================

interface QRCodeCardProps {
  src: string
  alt: string
  title: string
  description?: string
  index: number
}

function QRCodeCard({ src, alt, title, description, index }: QRCodeCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5, delay: 0.2 + index * 0.1 }}
      whileHover={{ scale: 1.05, y: -5 }}
      className={cn(
        'group rounded-2xl border border-gray-700/50 p-5',
        'bg-gray-900/50 backdrop-blur-sm',
        'transition-all duration-300',
        'hover:border-cyan-500/30 hover:shadow-lg hover:shadow-cyan-500/10'
      )}
    >
      {/* 标题 */}
      <div className="flex items-center justify-center gap-2 mb-3">
        <QrCode className="w-4 h-4 text-cyan-400" />
        <h4 className="text-sm font-medium text-white">{title}</h4>
      </div>

      {/* 二维码图片 */}
      <div className="relative mb-3 aspect-square w-36 mx-auto overflow-hidden rounded-xl bg-white p-2">
        <img
          src={src}
          alt={alt}
          className="h-full w-full object-contain"
          onError={(e) => {
            e.currentTarget.src =
              'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMjAwIiB2aWV3Qm94PSIwIDAgMjAwIDIwMCI+PHJlY3Qgd2lkdGg9IjIwMCIgaGVpZ2h0PSIyMDAiIGZpbGw9IiNmM2Y0ZjYiLz48dGV4dCB4PSI1MCUiIHk9IjUwJSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZmlsbD0iIzljYTNhZiIgZm9udC1zaXplPSIxNCI+5LqM57u056CBPC90ZXh0Pjwvc3ZnPg=='
          }}
        />
      </div>

      {/* 描述 */}
      {description && (
        <p className="text-center text-xs text-gray-500">{description}</p>
      )}
    </motion.div>
  )
}

// ============================================================================
// 钱包地址卡片组件
// ============================================================================

interface WalletCardProps {
  wallet: WalletAddress
  index: number
}

function WalletCard({ wallet, index }: WalletCardProps) {
  const { copied, copy } = useCopyToClipboard()
  const truncatedAddress = `${wallet.address.slice(0, 10)}...${wallet.address.slice(-8)}`

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5, delay: 0.3 + index * 0.1 }}
      className={cn(
        'relative group p-4 rounded-xl',
        'bg-gray-900/50 backdrop-blur-sm',
        'border border-gray-700/50',
        'transition-all duration-300',
        wallet.type === 'ethereum' ? 'hover:border-purple-500/40' : 'hover:border-amber-500/40'
      )}
    >
      <div className="flex items-center justify-between gap-3">
        {/* 左侧：图标和标签 */}
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'w-9 h-9 rounded-lg flex items-center justify-center text-lg font-bold',
              wallet.type === 'ethereum'
                ? 'bg-purple-500/20 text-purple-400'
                : 'bg-amber-500/20 text-amber-400'
            )}
          >
            {wallet.icon}
          </div>
          <div>
            <p className="text-sm font-medium text-white">{wallet.label}</p>
            <p className="text-xs text-gray-500 font-mono">{truncatedAddress}</p>
          </div>
        </div>

        {/* 右侧：复制按钮 */}
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          onClick={() => copy(wallet.address)}
          className={cn(
            'p-2 rounded-lg transition-all duration-200',
            copied
              ? 'bg-emerald-500/20 text-emerald-400'
              : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'
          )}
          title={copied ? '已复制' : '复制地址'}
        >
          {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
        </motion.button>
      </div>

      {/* 复制成功提示 */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: copied ? 1 : 0, y: copied ? 0 : -10 }}
        className="absolute -top-8 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 text-xs whitespace-nowrap"
      >
        已复制到剪贴板
      </motion.div>
    </motion.div>
  )
}

// ============================================================================
// 主组件
// ============================================================================

export function CTASection({ className }: CTASectionProps) {
  return (
    <section
      className={cn('relative overflow-hidden bg-gray-950 py-16 md:py-24', className)}
    >
      {/* 发光背景效果 */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-gray-950 to-transparent" />
        <div
          className={cn(
            'absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
            'h-[500px] w-[500px] rounded-full',
            'bg-gradient-radial from-cyan-500/15 via-blue-500/10 to-transparent',
            'blur-3xl'
          )}
        />
        <div className="absolute left-1/4 top-0 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute right-1/4 top-0 h-48 w-48 rounded-full bg-pink-500/10 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px]">
        {/* 标题 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="mb-12 text-center"
        >
          <div className="inline-flex items-center gap-2 mb-4">
            <Heart className="w-6 h-6 text-pink-400" />
            <h2 className="text-3xl font-bold text-white md:text-4xl">
              关注与
              <span className="bg-gradient-to-r from-cyan-400 to-purple-500 bg-clip-text text-transparent">
                支持
              </span>
            </h2>
          </div>
          <p className="mx-auto max-w-2xl text-base text-gray-400 md:text-lg">
            免费开源，持续更新。您的每一份支持都是对开源项目最大的鼓励
          </p>
        </motion.div>

        {/* 二维码区域 */}
        <div className="mb-10 flex flex-wrap justify-center gap-6">
          <QRCodeCard
            src="/images/qr-wechat-official.png"
            alt="法穿公众号二维码"
            title="关注公众号"
            description="扫码关注「法穿」获取最新动态"
            index={0}
          />
          <QRCodeCard
            src="/images/qr-donation.png"
            alt="赞赏支持二维码"
            title="赞赏支持"
            description="如果对您有帮助，欢迎赞赏"
            index={1}
          />
          {QR_CODES.map((qr, index) => (
            <QRCodeCard
              key={qr.title}
              src={qr.src}
              alt={qr.alt}
              title={qr.title}
              index={index + 2}
            />
          ))}
        </div>

        {/* 虚拟钱包打赏区域 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="max-w-xl mx-auto mb-10"
        >
          <div className="flex items-center justify-center gap-2 mb-4">
            <Wallet className="w-5 h-5 text-cyan-400" />
            <h3 className="text-base font-medium text-white">虚拟钱包打赏</h3>
          </div>
          <p className="text-center text-sm text-gray-500 mb-4">
            支持加密货币打赏，所有打赏将 100% 用于项目开发
          </p>

          <div className="space-y-3">
            {WALLET_ADDRESSES.map((wallet, index) => (
              <WalletCard key={wallet.type} wallet={wallet} index={index} />
            ))}
          </div>
        </motion.div>

        {/* CTA 按钮组 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="flex flex-col items-center justify-center gap-4 sm:flex-row"
        >
          <Button
            size="lg"
            className={cn(
              'relative overflow-hidden px-8',
              'bg-gradient-to-r from-cyan-500 to-blue-500',
              'hover:from-cyan-400 hover:to-blue-400',
              'shadow-lg shadow-cyan-500/25',
              'transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-cyan-500/30'
            )}
            asChild
          >
            <a href="/login">
              <Rocket className="mr-2 h-5 w-5" />
              立即体验
            </a>
          </Button>

          <Button
            size="lg"
            variant="outline"
            className={cn(
              'border-gray-700 bg-gray-800/50 px-8 text-white',
              'hover:border-gray-600 hover:bg-gray-700/50',
              'transition-all duration-300 hover:-translate-y-1'
            )}
            asChild
          >
            <a
              href="https://github.com/fachuan-ai/fachuan-ai"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Github className="mr-2 h-5 w-5" />
              GitHub
            </a>
          </Button>
        </motion.div>

        {/* 底部提示 */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.5 }}
          className="mt-10 text-center"
        >
          <p className="text-sm text-gray-500">
            💡 您的每一份支持都是对开源项目最大的鼓励 · 🚀 帮助我们持续改进功能、优化性能
          </p>
        </motion.div>
      </div>
    </section>
  )
}
