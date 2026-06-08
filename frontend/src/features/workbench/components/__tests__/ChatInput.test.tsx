/**
 * ChatInput Component Tests
 * 测试对话输入框组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, className, ...props }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string} {...props}>
      {children}
    </button>
  ),
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: React.forwardRef(({ value, onChange, onKeyDown, disabled, placeholder, className, ...props }: Record<string, unknown>, ref: React.Ref<HTMLTextAreaElement>) => (
    <textarea
      ref={ref}
      data-testid="chat-textarea"
      value={value as string}
      onChange={onChange as React.ChangeEventHandler}
      onKeyDown={onKeyDown as React.KeyboardEventHandler}
      disabled={disabled as boolean}
      placeholder={placeholder as string}
      className={className as string}
      {...props}
    />
  )),
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, onClick, variant, className, ...props }: Record<string, unknown>) => (
    <span onClick={onClick as React.MouseEventHandler} className={className as string} data-variant={variant} {...props}>
      {children}
    </span>
  ),
}))

vi.mock('@/hooks/use-speech-recognition', () => ({
  useSpeechRecognition: () => ({
    isSupported: false,
    isListening: false,
    interimTranscript: '',
    finalTranscript: '',
    error: null,
    start: vi.fn(),
    stop: vi.fn(),
    reset: vi.fn(),
  }),
}))

vi.mock('../VoiceButton', () => ({
  VoiceButton: () => <div data-testid="voice-button" />,
}))

vi.mock('../ContextAttachments', () => ({
  ContextAttachments: () => <div data-testid="context-attachments" />,
}))

const mockAbortStream = vi.fn()
const mockSetSelectedAgent = vi.fn()
const mockSetQuotedContent = vi.fn()

vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: (s: Record<string, unknown>) => unknown) => {
    const state: Record<string, unknown> = {
      isStreaming: false,
      selectedAgent: 'triage',
      setSelectedAgent: mockSetSelectedAgent,
      abortStream: mockAbortStream,
      quotedContent: null,
      setQuotedContent: mockSetQuotedContent,
    }
    return selector(state)
  }),
}))

import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatInput } from '../ChatInput'

describe('ChatInput', () => {
  const defaultProps = {
    onSend: vi.fn(),
    disabled: false,
  }

  it('renders textarea and send button', () => {
    render(<ChatInput {...defaultProps} />)
    expect(screen.getByTestId('chat-textarea')).toBeInTheDocument()
    expect(screen.getByTestId('context-attachments')).toBeInTheDocument()
  })

  it('renders agent selector options', () => {
    render(<ChatInput {...defaultProps} />)
    expect(screen.getByText('助手:')).toBeInTheDocument()
    expect(screen.getByText('分诊助手')).toBeInTheDocument()
    expect(screen.getByText('案件管理')).toBeInTheDocument()
    expect(screen.getByText('合同管理')).toBeInTheDocument()
    expect(screen.getByText('法律检索')).toBeInTheDocument()
  })

  it('sends message on Enter key', () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    const textarea = screen.getByTestId('chat-textarea')
    fireEvent.change(textarea, { target: { value: 'Hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('Hello')
  })

  it('does not send on Shift+Enter', () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    const textarea = screen.getByTestId('chat-textarea')
    fireEvent.change(textarea, { target: { value: 'Hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })
    expect(onSend).not.toHaveBeenCalled()
  })

  it('does not send empty message', () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    const textarea = screen.getByTestId('chat-textarea')
    fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
  })

  it('renders voice button', () => {
    render(<ChatInput {...defaultProps} />)
    expect(screen.getByTestId('voice-button')).toBeInTheDocument()
  })
})
