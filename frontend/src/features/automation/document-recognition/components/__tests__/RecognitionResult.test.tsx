/**
 * RecognitionResult Component Tests
 * 测试识别结果展示组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: any) => <div data-testid="card" {...props}>{children}</div>,
  CardContent: ({ children }: any) => <div>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, className }: any) => <span className={className}>{children}</span>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, ...props }: any) => <button onClick={onClick} {...props}>{children}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: any) => <input {...props} />,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children }: any) => <div>{children}</div>,
  FormControl: ({ children }: any) => <div>{children}</div>,
  FormField: ({ render }: any) => render({ field: { value: '', onChange: vi.fn() } }),
  FormItem: ({ children }: any) => <div>{children}</div>,
  FormLabel: ({ children }: any) => <label>{children}</label>,
  FormMessage: () => null,
}))

vi.mock('react-hook-form', () => ({
  useForm: () => ({
    control: {},
    handleSubmit: (fn: Function) => (e?: Event) => { e?.preventDefault?.(); fn({ document_type: '', key_time: '' }) },
    register: vi.fn(),
  }),
}))

vi.mock('@hookform/resolvers/zod', () => ({
  zodResolver: () => ({}),
}))

vi.mock('lucide-react', () => ({
  FileText: () => <svg data-testid="icon-file" />,
  Hash: () => <svg data-testid="icon-hash" />,
  Calendar: () => <svg data-testid="icon-calendar" />,
  Percent: () => <svg data-testid="icon-percent" />,
  Pencil: () => <svg data-testid="icon-pencil" />,
  Save: () => <svg data-testid="icon-save" />,
  X: () => <svg data-testid="icon-x" />,
}))

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RecognitionResult } from '../RecognitionResult'
import type { DocumentRecognitionTask } from '../../types'

const createTask = (overrides: Partial<DocumentRecognitionTask> = {}): DocumentRecognitionTask => ({
  id: 1,
  file_name: 'test.pdf',
  file_path: '/path/to/test.pdf',
  status: 'success',
  document_type: '判决书',
  case_number: '(2024)京0101民初12345号',
  key_time: '2024-01-15',
  confidence: 0.95,
  extraction_method: 'ocr',
  raw_text: null,
  binding_success: true,
  case_id: 1,
  case_name: 'Test Case',
  case_log_id: null,
  error_message: null,
  created_at: '2026-06-15T10:00:00Z',
  updated_at: '2026-06-15T10:00:00Z',
  ...overrides,
})

describe('RecognitionResult', () => {
  it('renders title', () => {
    render(<RecognitionResult task={createTask()} />)
    expect(screen.getByText('识别结果')).toBeInTheDocument()
  })

  it('renders document type in read-only mode', () => {
    render(<RecognitionResult task={createTask()} />)
    expect(screen.getByText('文书类型')).toBeInTheDocument()
    expect(screen.getByText('判决书')).toBeInTheDocument()
  })

  it('renders case number', () => {
    render(<RecognitionResult task={createTask()} />)
    expect(screen.getByText('案号')).toBeInTheDocument()
    expect(screen.getByText('(2024)京0101民初12345号')).toBeInTheDocument()
  })

  it('renders key time', () => {
    render(<RecognitionResult task={createTask()} />)
    expect(screen.getByText('关键时间')).toBeInTheDocument()
    expect(screen.getByText('2024-01-15')).toBeInTheDocument()
  })

  it('renders high confidence label', () => {
    render(<RecognitionResult task={createTask({ confidence: 0.95 })} />)
    expect(screen.getByText('95%')).toBeInTheDocument()
    expect(screen.getByText('高置信度')).toBeInTheDocument()
  })

  it('renders medium confidence label', () => {
    render(<RecognitionResult task={createTask({ confidence: 0.6 })} />)
    expect(screen.getByText('60%')).toBeInTheDocument()
    expect(screen.getByText('中置信度')).toBeInTheDocument()
  })

  it('renders low confidence label', () => {
    render(<RecognitionResult task={createTask({ confidence: 0.3 })} />)
    expect(screen.getByText('30%')).toBeInTheDocument()
    expect(screen.getByText('低置信度')).toBeInTheDocument()
  })

  it('renders placeholder for null document type', () => {
    render(<RecognitionResult task={createTask({ document_type: null })} />)
    expect(screen.getAllByText('未识别').length).toBeGreaterThanOrEqual(1)
  })

  it('shows edit button when onEdit is provided', () => {
    const onEdit = vi.fn()
    render(<RecognitionResult task={createTask()} onEdit={onEdit} />)
    expect(screen.getByText('编辑')).toBeInTheDocument()
  })

  it('calls onEdit when edit button is clicked', async () => {
    const onEdit = vi.fn()
    const user = userEvent.setup()
    render(<RecognitionResult task={createTask()} onEdit={onEdit} />)
    await user.click(screen.getByText('编辑'))
    expect(onEdit).toHaveBeenCalled()
  })

  it('does not show edit button in editing mode', () => {
    render(
      <RecognitionResult
        task={createTask()}
        isEditing={true}
        onSave={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.queryByText('编辑')).not.toBeInTheDocument()
  })

  it('does not show edit button without onEdit callback', () => {
    render(<RecognitionResult task={createTask()} />)
    expect(screen.queryByText('编辑')).not.toBeInTheDocument()
  })
})
