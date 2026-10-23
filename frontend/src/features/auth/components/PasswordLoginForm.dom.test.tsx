// @vitest-environment jsdom
/**
 * PasswordLoginForm 测试（jsdom）。
 *
 * 账密登录表单：校验空字段、提交中禁用、成功回调、失败展示后端文案。
 * 错误提示挂在表单自己身上（不占用登录页共享错误位），这里一并锁定。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const loginMock = vi.hoisted(() => vi.fn())
vi.mock('../store', () => ({
  useAuth: (sel: (s: { login: typeof loginMock }) => unknown) => sel({ login: loginMock }),
}))

import { PasswordLoginForm } from './PasswordLoginForm'

function fill(username: string, password: string) {
  fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: username } })
  fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: password } })
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: /登录/ }))
}

beforeEach(() => {
  vi.clearAllMocks()
  loginMock.mockResolvedValue({ ok: true })
})

describe('PasswordLoginForm：字段渲染', () => {
  it('渲染用户名与密码输入框及标签', () => {
    const { container } = render(<PasswordLoginForm onLoggedIn={vi.fn()} />)
    expect(screen.getByLabelText(/用户名/)).toBeTruthy()
    expect(screen.getByLabelText(/密码/)).toBeTruthy()
    // 密码框必须是 password 类型
    expect((screen.getByPlaceholderText('请输入密码') as HTMLInputElement).type).toBe('password')
    container.remove()
  })

  it('自动填充属性正确（密码管理器依赖它）', () => {
    const { container } = render(<PasswordLoginForm onLoggedIn={vi.fn()} />)
    expect((screen.getByPlaceholderText('请输入用户名') as HTMLInputElement).autocomplete).toBe('username')
    expect((screen.getByPlaceholderText('请输入密码') as HTMLInputElement).autocomplete).toBe('current-password')
    container.remove()
  })
})

describe('PasswordLoginForm：校验', () => {
  it('用户名为空时提示且不调登录', async () => {
    const { container } = render(<PasswordLoginForm onLoggedIn={vi.fn()} />)
    fill('', 'pwd')
    submit()

    await waitFor(() => expect(screen.getByText('请输入用户名和密码')).toBeTruthy())
    expect(loginMock).not.toHaveBeenCalled()
    container.remove()
  })

  it('密码为空时同样提示', async () => {
    const { container } = render(<PasswordLoginForm onLoggedIn={vi.fn()} />)
    fill('user', '')
    submit()

    await waitFor(() => expect(screen.getByText('请输入用户名和密码')).toBeTruthy())
    expect(loginMock).not.toHaveBeenCalled()
    container.remove()
  })
})

describe('PasswordLoginForm：提交', () => {
  it('成功：调用 login 并触发 onLoggedIn', async () => {
    const onLoggedIn = vi.fn()
    const { container } = render(<PasswordLoginForm onLoggedIn={onLoggedIn} />)
    fill('user', 'pwd')
    submit()

    await waitFor(() => expect(loginMock).toHaveBeenCalledWith('user', 'pwd'))
    await waitFor(() => expect(onLoggedIn).toHaveBeenCalled())
    expect(screen.queryByText('请输入用户名和密码')).toBeNull()
    container.remove()
  })

  it('失败：展示后端文案且不回调', async () => {
    loginMock.mockResolvedValue({ ok: false, message: '用户名或密码错误' })
    const onLoggedIn = vi.fn()
    const { container } = render(<PasswordLoginForm onLoggedIn={onLoggedIn} />)
    fill('user', 'bad')
    submit()

    await waitFor(() => expect(screen.getByText('用户名或密码错误')).toBeTruthy())
    expect(onLoggedIn).not.toHaveBeenCalled()
    container.remove()
  })

  it('失败且无 message 时用「登录失败」兜底', async () => {
    loginMock.mockResolvedValue({ ok: false })
    const { container } = render(<PasswordLoginForm onLoggedIn={vi.fn()} />)
    fill('user', 'bad')
    submit()

    await waitFor(() => expect(screen.getByText('登录失败')).toBeTruthy())
    container.remove()
  })

  it('提交中按钮禁用并显示「登录中…」', async () => {
    let resolveLogin: (v: { ok: boolean }) => void = () => {}
    loginMock.mockReturnValue(
      new Promise<{ ok: boolean }>((r) => {
        resolveLogin = r
      }),
    )
    const { container } = render(<PasswordLoginForm onLoggedIn={vi.fn()} />)
    fill('user', 'pwd')
    submit()

    const btn = await waitFor(() => screen.getByRole('button', { name: /登录中/ }) as HTMLButtonElement)
    expect(btn.disabled).toBe(true)

    resolveLogin({ ok: true })
    await waitFor(() => expect(screen.getByRole('button', { name: '登录' })).toBeTruthy())
    container.remove()
  })

  it('重新提交会清掉上一次错误提示', async () => {
    loginMock.mockResolvedValueOnce({ ok: false, message: '密码错误' })
    const { container } = render(<PasswordLoginForm onLoggedIn={vi.fn()} />)
    fill('user', 'bad')
    submit()
    await waitFor(() => expect(screen.getByText('密码错误')).toBeTruthy())

    loginMock.mockResolvedValueOnce({ ok: true })
    submit()
    await waitFor(() => expect(screen.queryByText('密码错误')).toBeNull())
    container.remove()
  })
})
