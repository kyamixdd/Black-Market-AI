import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './design-tokens.css'
import './App.css'
import App from './App.tsx'
import { DiagnosticErrorBoundary } from './components/DiagnosticErrorBoundary'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DiagnosticErrorBoundary>
      <App />
    </DiagnosticErrorBoundary>
  </StrictMode>,
)
