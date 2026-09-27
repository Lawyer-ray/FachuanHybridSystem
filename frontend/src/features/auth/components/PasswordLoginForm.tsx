/**
 * 账号密码登录表单。
 *
 * 从 LoginPage 抽出：错误提示是表单自己的事，不该占用登录页的共享错误位
 * （否则切到扫码方式时会把上一次的密码错误带过去）。
 */
import { useState } from 'react'
import { Eye, EyeOff, Loader2, Lock, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '../store'

interface Props {
  /** 登录成功后的跳转由登录页决定 */
  onLoggedIn: () => void
}

export function PasswordLoginForm({ onLoggedIn }: Props) {
  const login = useAuth((s) => s.login)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) {
      setError('请输入用户名和密码')
      return
    }
    setLoading(true)
    setError('')
    const res = await login(username, password)
    setLoading(false)
    if (res.ok) {
      onLoggedIn()
    } else {
      setError(res.message || '登录失败')
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="relative">
        <User className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="用户名"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="pl-9"
        />
      </div>
      <div className="relative">
        <Lock className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type={show ? 'text' : 'password'}
          placeholder="密码"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="pl-9 pr-10"
        />
        <button
          type="button"
          tabIndex={-1}
          onClick={() => setShow((v) => !v)}
          className="absolute top-1/2 right-2 -translate-y-1/2 cursor-pointer rounded-md p-1 text-muted-foreground hover:text-foreground"
          aria-label={show ? '隐藏密码' : '显示密码'}
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Button type="submit" className="au-cta w-full" disabled={loading}>
        {loading && <Loader2 className="h-4 w-4 animate-spin" />}
        {loading ? '登录中…' : '登录'}
      </Button>
    </form>
  )
}
