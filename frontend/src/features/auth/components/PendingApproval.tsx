import { Link } from 'react-router'
import { Clock } from 'lucide-react'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/button'

export function PendingApproval() {
  return (
    <div className="text-center space-y-4">
      <motion.div
        className="flex justify-center"
        animate={{ scale: [1, 1.05, 1] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
      >
        <Clock className="h-16 w-16 text-muted-foreground dark:text-violet-400" />
      </motion.div>
      <h2 className="text-xl font-semibold dark:bg-gradient-to-r dark:from-violet-300 dark:via-white dark:to-cyan-300 dark:bg-clip-text dark:text-transparent">
        注册成功
      </h2>
      <p className="text-muted-foreground">
        您的账号正在等待管理员审批，审批通过后即可登录使用。
      </p>
      <Button asChild variant="outline" className="dark:border-[rgba(123,97,255,0.3)] dark:hover:bg-[rgba(123,97,255,0.1)]">
        <Link to="/login">返回登录</Link>
      </Button>
    </div>
  )
}
