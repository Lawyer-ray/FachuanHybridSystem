'use client'

import { Link } from 'react-router'
import { Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * PendingApproval - 等待审批提示组件
 *
 * 当后续用户（非首位用户）注册成功后显示此组件
 * 提示用户账号正在等待管理员审批
 *
 * 功能说明:
 * - 显示时钟图标表示等待状态
 * - 显示注册成功和等待审批的提示信息
 * - 提供返回登录页面的链接按钮
 *
 * @validates Requirements 6.5 - WHEN 后续用户注册成功 THEN THE Register_Page SHALL 显示"等待审批"提示页面
 */
export function PendingApproval() {
  return (
    <div className="text-center space-y-4">
      <div className="flex justify-center">
        <Clock className="h-16 w-16 text-muted-foreground" />
      </div>
      <h2 className="text-xl font-semibold">注册成功</h2>
      <p className="text-muted-foreground">
        您的账号正在等待管理员审批，审批通过后即可登录使用。
      </p>
      <Button asChild variant="outline">
        <Link to="/login">返回登录</Link>
      </Button>
    </div>
  )
}
