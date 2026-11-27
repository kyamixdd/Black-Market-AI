import { Profiler, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './design-tokens.css'
import './App.css'
import App from './App.tsx'
import { recordFrontendDiagnostic } from './services/frontendDiagnostics'

function recordReactCommit(
  id: string,
  phase: string,
  actualDuration: number,
) {
  const slow = actualDuration >= 250
  recordFrontendDiagnostic({
    level: slow ? 'WARNING' : 'INFO',
    event: 'ui_render_committed',
    operation: `react.render.${id}`,
    status: slow ? 'WARNING' : 'SUCCESS',
    duration_ms: actualDuration,
    detail: `phase=${phase}`,
    recommendation: slow ? 'Inspect this component for expensive render work or excessive state updates.' : undefined,
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Profiler id="BlackMarketApp" onRender={recordReactCommit}>
      <App />
    </Profiler>
  </StrictMode>,
)
