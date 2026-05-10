import { Outlet } from 'react-router'
import { motion } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { ThemeToggle } from '@/features/auth/components/ThemeToggle'
import { CosmicBackground } from '@/features/auth/components/CosmicBackground'

interface AuthLayoutProps {
  children?: React.ReactNode
  title?: string
  description?: string
  icon?: React.ReactNode
}

export function AuthLayoutCard({ children, title, description, icon }: AuthLayoutProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 30 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="w-full max-w-md"
    >
      <Card className="cosmic-card-glow border backdrop-blur-xl shadow-xl bg-white/70 border-white/40 dark:bg-[rgba(15,10,40,0.6)] dark:border-[rgba(123,97,255,0.15)] dark:shadow-[0_0_40px_-10px_rgba(123,97,255,0.2)]">
        {(title || description || icon) && (
          <CardHeader className="space-y-2 pb-4">
            {icon && (
              <motion.div
                className="flex justify-center"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2, duration: 0.5, type: 'spring' }}
              >
                {icon}
              </motion.div>
            )}
            {title && (
              <CardTitle className="text-2xl font-semibold tracking-tight text-center dark:bg-gradient-to-r dark:from-violet-300 dark:via-white dark:to-cyan-300 dark:bg-clip-text dark:text-transparent">
                {title}
              </CardTitle>
            )}
            {description && (
              <CardDescription className="text-center text-muted-foreground">
                {description}
              </CardDescription>
            )}
          </CardHeader>
        )}
        <CardContent className={title || description || icon ? '' : 'pt-6'}>
          {children}
        </CardContent>
      </Card>
    </motion.div>
  )
}

export function AuthLayout() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4 sm:p-6 lg:p-8">
      <CosmicBackground />

      {/* Theme toggle */}
      <motion.div
        className="fixed top-4 right-4 z-50"
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2, duration: 0.3 }}
      >
        <ThemeToggle />
      </motion.div>

      {/* Content */}
      <div className="relative z-10 w-full flex items-center justify-center">
        <Outlet />
      </div>
    </div>
  )
}

export default AuthLayout
