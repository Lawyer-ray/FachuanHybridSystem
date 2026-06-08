import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../ThemeProvider'

vi.mock('next-themes', () => ({
  ThemeProvider: ({ children, ...props }: Record<string, unknown>) => (
    <div
      data-testid="next-themes-provider"
      data-attribute={props.attribute}
      data-default-theme={props.defaultTheme}
      data-enable-system={props.enableSystem}
      data-storage-key={props.storageKey}
    >
      {children}
    </div>
  ),
}))

describe('ThemeProvider', () => {
  it('renders children', () => {
    render(
      <ThemeProvider>
        <div data-testid="child">Hello</div>
      </ThemeProvider>,
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('passes correct attribute prop', () => {
    render(
      <ThemeProvider>
        <div>test</div>
      </ThemeProvider>,
    )
    const provider = screen.getByTestId('next-themes-provider')
    expect(provider.getAttribute('data-attribute')).toBe('class')
  })

  it('passes defaultTheme as light', () => {
    render(
      <ThemeProvider>
        <div>test</div>
      </ThemeProvider>,
    )
    const provider = screen.getByTestId('next-themes-provider')
    expect(provider.getAttribute('data-default-theme')).toBe('light')
  })

  it('disables system theme detection', () => {
    render(
      <ThemeProvider>
        <div>test</div>
      </ThemeProvider>,
    )
    const provider = screen.getByTestId('next-themes-provider')
    expect(provider.getAttribute('data-enable-system')).toBe('false')
  })

  it('uses correct storage key', () => {
    render(
      <ThemeProvider>
        <div>test</div>
      </ThemeProvider>,
    )
    const provider = screen.getByTestId('next-themes-provider')
    expect(provider.getAttribute('data-storage-key')).toBe('theme')
  })
})
