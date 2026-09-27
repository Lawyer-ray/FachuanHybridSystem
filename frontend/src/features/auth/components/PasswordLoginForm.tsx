/**
 * 账号密码登录表单。
 *
 * 从 LoginPage 抽出：错误提示是表单自己的事，不该占用登录页的共享错误位
 * （否则切到扫码方式时会把上一次的密码错误带过去）。
 *
 * 这里用原生 input / button 而非 ui/ 里的 Input、Button：登录页是独立视觉面
 * （只有一条底线的字段、直角黄铜按钮），套用基础组件的圆角边框反而要层层覆盖。
 */
import { useState } from 'react'
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
    <form className="fc-fields" onSubmit={submit}>
      <div className="fc-field">
        <label className="fc-field__label" htmlFor="fc-username">
          用户名 / Username
        </label>
        <div className="fc-field__row">
          <input
            id="fc-username"
            className="fc-input"
            placeholder="请输入用户名"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
      </div>

      <div className="fc-field">
        <label className="fc-field__label" htmlFor="fc-password">
          密码 / Password
        </label>
        <div className="fc-field__row">
          <input
            id="fc-password"
            type={show ? 'text' : 'password'}
            className="fc-input"
            placeholder="请输入密码"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            type="button"
            tabIndex={-1}
            onClick={() => setShow((v) => !v)}
            className="fc-field__toggle"
            aria-label={show ? '隐藏密码' : '显示密码'}
          >
            {show ? '隐藏' : '显示'}
          </button>
        </div>
      </div>

      {error && <p className="fc-error">{error}</p>}

      <button type="submit" className="fc-btn" disabled={loading}>
        {loading ? '登录中…' : '登录'}
      </button>
    </form>
  )
}
