/**
 * 提问人头像：优先律师上传的头像（Lawyer.avatar_url），加载失败或未设置
 * 回退「名字首字」圆形字标（真名优先，其次用户名）。
 */

import { useState } from 'react'

import { cn } from '@/lib/utils'

import type { User } from '@/features/auth'

export function UserAvatar({ user, className }: { user: User | null; className?: string }) {
  const [broken, setBroken] = useState(false)
  if (!user) return null
  const name = (user.real_name || user.username || '').trim()
  if (user.avatar_url && !broken) {
    return (
      <img
        src={user.avatar_url}
        alt={name || '我'}
        title={name || undefined}
        onError={() => setBroken(true)}
        className={cn('flex-none rounded-full object-cover', className)}
      />
    )
  }
  return (
    <span
      aria-hidden
      title={name || undefined}
      className={cn(
        'flex flex-none items-center justify-center rounded-full bg-secondary text-[11px] font-semibold text-secondary-foreground',
        className,
      )}
    >
      {name.slice(0, 1).toUpperCase() || '?'}
    </span>
  )
}
