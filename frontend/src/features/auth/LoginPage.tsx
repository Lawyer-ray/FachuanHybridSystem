import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
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
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2">
          <span className="text-lg font-semibold tracking-tight">
            法穿 <span className="font-medium text-foreground/70">AI Copilot</span>
          </span>
        </div>
        <div className="rounded-2xl border bg-card p-6 shadow-sm">
          <h1 className="text-base font-semibold">登录</h1>
          <p className="mt-1 text-xs text-muted-foreground">材料预处理前，先登录后端收件箱</p>
          <form onSubmit={submit} className="mt-5 space-y-3">
            <Input
              placeholder="用户名"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <div className="relative">
              <Input
                type={show ? 'text' : 'password'}
                placeholder="密码"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="pr-10"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShow((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
                aria-label={show ? '隐藏密码' : '显示密码'}
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {error && <p className="text-xs text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              登录
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}
