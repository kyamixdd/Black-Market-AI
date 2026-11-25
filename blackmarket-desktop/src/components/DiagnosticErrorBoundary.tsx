import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { recordDiagnostic } from '../services/diagnosticLogger'

type Props = { children: ReactNode }
type State = { hasError: boolean; message: string }

export class DiagnosticErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || error.name || 'Unexpected rendering error' }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    recordDiagnostic('ERROR', 'frontend.react_render_error', {
      feature: 'render',
      function: 'ReactErrorBoundary',
      detail: `${error.name}: ${error.message}\n${info.componentStack ?? ''}`,
    })
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <main className="diagnostic-crash-screen" role="alert">
        <section>
          <p className="diagnostic-crash-kicker">RENDER FAILURE</p>
          <h1>BlackMarket AI encountered a UI error.</h1>
          <p>The error has been recorded in System Diagnostics. Restart the view to continue.</p>
          <pre>{this.state.message}</pre>
          <button type="button" onClick={() => window.location.reload()}>Reload application</button>
        </section>
      </main>
    )
  }
}
