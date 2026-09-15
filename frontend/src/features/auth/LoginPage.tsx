import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Eye, EyeOff, Loader2, Lock, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from './store'

export function LoginPage() {
  const { login, init } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    init()
  }, [init])

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
      navigate('/', { replace: true })
    } else {
      setError(res.message || '登录失败')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-[360px]">
        <div className="mb-8 flex flex-col items-center gap-4">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-foreground text-lg font-bold text-background shadow-sm">
            法
          </span>
          <div className="text-center">
            <h1 className="text-[17px] font-semibold tracking-tight">法穿 AI Copilot</h1>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground">律师的材料预处理工作台</p>
          </div>
        </div>

        <div className="rounded-2xl border bg-card p-6 shadow-sm">
          <form onSubmit={submit} className="space-y-3">
            <div className="relative">
              <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="用户名"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="pl-9"
              />
            </div>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
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
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:text-foreground"
                aria-label={show ? '隐藏密码' : '显示密码'}
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {error && <p className="text-xs text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? '登录中…' : '登录'}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-center text-[11.5px] text-muted-foreground">
          材料预处理前，先登录后端收件箱
        </p>
      </div>
    </div>
  )
}
