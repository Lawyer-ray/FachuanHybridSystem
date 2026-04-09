/**
 * 价格页面
 * 展示产品定价方案
 */

import { motion } from 'framer-motion'
import { Check, Sparkles, Zap, Building2 } from 'lucide-react'
import { lazy, Suspense } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Navigation } from '@/features/home/components/Navigation'

// 懒加载 Footer
const Footer = lazy(() =>
  import('@/features/home/components/Footer').then((m) => ({ default: m.Footer }))
)

// 动画配置
const springConfig = {
  type: 'spring' as const,
  stiffness: 100,
  damping: 15,
}

// 定价方案数据
const PRICING_PLANS = [
  {
    id: 'free',
    name: '开源版',
    description: '适合不想花钱的律师',
    price: '免费',
    priceNote: '永久免费',
    icon: Sparkles,
    colorScheme: 'purple',
    features: [
      '完整源代码访问',
      '案件管理基础功能',
      '合同管理基础功能',
      '客户管理',
      '文档模板系统',
      'AI 文书生成（需自备 API Key）',
      '社区支持',
      'GitHub Issues 反馈',
    ],
    cta: '立即部署',
    ctaLink: 'https://github.com/fachuan-ai/fachuan-ai',
    popular: false,
  },
  {
    id: 'pro',
    name: '专业版',
    description: '适合相信法穿的同学们',
    price: '¥888',
    priceNote: '/用户',
    icon: Zap,
    colorScheme: 'cyan',
    features: [
      '开源版全部功能',
      '专业版皮肤主题',
      '领先开源版获取新功能',
      '高级数据统计报表',
      '单独开发代码对接律所OA（1次/用户）',
      '优先技术支持',
      '专属用户社群',
      '一对一部署指导',
    ],
    cta: '联系我们',
    ctaLink: '#contact',
    popular: true,
  },
  {
    id: 'enterprise',
    name: '企业版',
    description: '适合≥10人以上律师团队/律所',
    price: '定制',
    priceNote: '按需报价',
    icon: Building2,
    colorScheme: 'pink',
    features: [
      '专业版全部功能',
      '私有化部署',
      '定制开发',
      '专属客户经理',
      'SLA 服务保障',
      '7×24 技术支持',
      '培训与上门服务',
      '数据迁移支持',
    ],
    cta: '预约演示',
    ctaLink: '#contact',
    popular: false,
  },
]

// FAQ 数据
const FAQ_DATA = [
  {
    question: '开源版和付费版有什么区别？',
    answer:
      '开源版包含完整的案件、合同、客户管理功能，适合有技术能力自行部署的团队。付费版增加了自动化功能（短信处理、文书下载等）和专业技术支持。',
  },
  {
    question: '可以先试用再决定吗？',
    answer:
      '当然可以！开源版永久免费，您可以先部署体验。专业版我们提供 14 天免费试用，企业版可以预约演示。',
  },
  {
    question: '数据安全如何保障？',
    answer:
      '所有版本都支持私有化部署，数据完全存储在您自己的服务器上。我们不会访问或存储您的任何业务数据。',
  },
  {
    question: '如何获取技术支持？',
    answer:
      '开源版通过 GitHub Issues 获取社区支持。付费版享有优先技术支持，企业版配备专属客户经理和 7×24 小时响应。',
  },
]

/**
 * 加载骨架组件
 */
function SectionSkeleton() {
  return (
    <div className="flex min-h-[200px] items-center justify-center bg-gray-950">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
    </div>
  )
}

/**
 * 定价卡片组件
 */
function PricingCard({
  plan,
  index,
}: {
  plan: (typeof PRICING_PLANS)[0]
  index: number
}) {
  const Icon = plan.icon

  const colorClasses = {
    purple: {
      gradient: 'from-purple-500 to-pink-500',
      border: 'border-purple-500/30',
      bg: 'bg-purple-500/10',
      text: 'text-purple-400',
      shadow: 'shadow-purple-500/20',
    },
    cyan: {
      gradient: 'from-cyan-500 to-blue-500',
      border: 'border-cyan-500/30',
      bg: 'bg-cyan-500/10',
      text: 'text-cyan-400',
      shadow: 'shadow-cyan-500/20',
    },
    pink: {
      gradient: 'from-pink-500 to-rose-500',
      border: 'border-pink-500/30',
      bg: 'bg-pink-500/10',
      text: 'text-pink-400',
      shadow: 'shadow-pink-500/20',
    },
  }

  const colors = colorClasses[plan.colorScheme as keyof typeof colorClasses]

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ ...springConfig, delay: index * 0.1 }}
      className={cn(
        'relative flex flex-col rounded-2xl border p-6 lg:p-8',
        'bg-gray-900/50 backdrop-blur-sm',
        plan.popular
          ? `${colors.border} ${colors.shadow} shadow-lg`
          : 'border-gray-800'
      )}
    >
      {/* 热门标签 */}
      {plan.popular && (
        <div
          className={cn(
            'absolute -top-3 left-1/2 -translate-x-1/2',
            'rounded-full px-4 py-1',
            `bg-gradient-to-r ${colors.gradient}`,
            'text-xs font-medium text-white'
          )}
        >
          最受欢迎
        </div>
      )}

      {/* 图标和标题 */}
      <div className="mb-6">
        <div
          className={cn(
            'mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl',
            `bg-gradient-to-br ${colors.gradient}`
          )}
        >
          <Icon className="h-6 w-6 text-white" />
        </div>
        <h3 className="text-xl font-bold text-white">{plan.name}</h3>
        <p className="mt-1 text-sm text-gray-400">{plan.description}</p>
      </div>

      {/* 价格 */}
      <div className="mb-6">
        <span className="text-4xl font-bold text-white">{plan.price}</span>
        <span className="ml-2 text-gray-400">{plan.priceNote}</span>
      </div>

      {/* 功能列表 */}
      <ul className="mb-8 flex-1 space-y-3">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-3">
            <Check className={cn('mt-0.5 h-5 w-5 flex-shrink-0', colors.text)} />
            <span className="text-sm text-gray-300">{feature}</span>
          </li>
        ))}
      </ul>

      {/* CTA 按钮 */}
      <Button
        className={cn(
          'w-full',
          plan.popular
            ? `bg-gradient-to-r ${colors.gradient} text-white hover:opacity-90`
            : 'bg-gray-800 text-white hover:bg-gray-700'
        )}
        onClick={() => {
          if (plan.ctaLink.startsWith('http')) {
            window.open(plan.ctaLink, '_blank')
          } else {
            document.getElementById('contact')?.scrollIntoView({ behavior: 'smooth' })
          }
        }}
      >
        {plan.cta}
      </Button>
    </motion.div>
  )
}

/**
 * FAQ 项组件
 */
function FAQItem({
  item,
  index,
}: {
  item: (typeof FAQ_DATA)[0]
  index: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ ...springConfig, delay: index * 0.1 }}
      className="rounded-xl border border-gray-800 bg-gray-900/50 p-6"
    >
      <h3 className="mb-3 text-lg font-semibold text-white">{item.question}</h3>
      <p className="text-gray-400">{item.answer}</p>
    </motion.div>
  )
}

export function PricingPage() {
  return (
    <div className="min-h-screen bg-gray-950">
      {/* 导航栏 */}
      <Navigation />

      {/* Hero 区域 */}
      <section className="relative overflow-hidden pt-32 pb-16 md:pt-40 md:pb-20">
        {/* 背景装饰 */}
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute left-1/4 top-1/4 h-[500px] w-[500px] rounded-full bg-purple-600/10 blur-[120px]" />
          <div className="absolute right-1/4 bottom-1/4 h-[400px] w-[400px] rounded-full bg-cyan-500/10 blur-[100px]" />
        </div>

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px]">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={springConfig}
            className="text-center"
          >
            {/* 徽章 */}
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ ...springConfig, delay: 0.1 }}
              className="mb-6 inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-4 py-1.5 text-sm font-medium text-cyan-300"
            >
              <Sparkles className="h-4 w-4" />
              <span>灵活定价</span>
            </motion.div>

            {/* 标题 */}
            <h1 className="mb-6 text-4xl font-bold tracking-tight text-white sm:text-5xl md:text-6xl">
              选择适合您的
              <span className="bg-gradient-to-r from-cyan-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
                定价方案
              </span>
            </h1>

            {/* 描述 */}
            <p className="mx-auto max-w-2xl text-lg text-gray-400 md:text-xl">
              从免费开源版到企业定制版，满足不同规模团队的需求
              <br className="hidden sm:block" />
              所有版本都支持私有化部署，数据安全有保障
            </p>
          </motion.div>
        </div>
      </section>

      {/* 定价卡片区域 */}
      <section className="relative py-16 md:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px]">
          <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
            {PRICING_PLANS.map((plan, index) => (
              <PricingCard key={plan.id} plan={plan} index={index} />
            ))}
          </div>
        </div>
      </section>

      {/* FAQ 区域 */}
      <section className="relative py-16 md:py-20">
        {/* 顶部渐变 */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-gray-950 to-transparent" />

        <div className="relative mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={springConfig}
            className="mb-12 text-center"
          >
            <h2 className="mb-4 text-3xl font-bold text-white md:text-4xl">
              常见问题
            </h2>
            <p className="text-gray-400">
              关于定价和服务的常见问题解答
            </p>
          </motion.div>

          <div className="grid gap-4 md:grid-cols-2">
            {FAQ_DATA.map((item, index) => (
              <FAQItem key={item.question} item={item} index={index} />
            ))}
          </div>
        </div>
      </section>

      {/* 联系区域 */}
      <section id="contact" className="relative py-16 md:py-20">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 text-center">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={springConfig}
            className="rounded-2xl border border-gray-800 bg-gray-900/50 p-8 md:p-12"
          >
            <h2 className="mb-4 text-2xl font-bold text-white md:text-3xl">
              还有疑问？
            </h2>
            <p className="mb-8 text-gray-400">
              我们的团队随时为您解答，帮助您选择最适合的方案
            </p>
            <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Button
                size="lg"
                className="bg-gradient-to-r from-cyan-500 to-blue-500 text-white hover:opacity-90"
                onClick={() => window.open('https://github.com/fachuan-ai/fachuan-ai/issues', '_blank')}
              >
                GitHub 讨论
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="border-gray-700 text-gray-300 hover:bg-gray-800"
              >
                发送邮件
              </Button>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <Suspense fallback={<SectionSkeleton />}>
        <Footer />
      </Suspense>
    </div>
  )
}
