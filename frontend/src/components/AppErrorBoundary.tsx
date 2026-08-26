import { Component, type ErrorInfo, type ReactNode } from 'react'
import { clearStoredPage } from '../lib/storage'
import './AppErrorBoundary.css'

type AppErrorBoundaryProps = {
  children: ReactNode
}

type AppErrorBoundaryState = {
  hasError: boolean
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('La pantalla no pudo renderizarse.', error, errorInfo)
  }

  private retry = (): void => {
    globalThis.location.reload()
  }

  private returnHome = (): void => {
    clearStoredPage()
    globalThis.location.assign('/')
  }

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <main className="app-error-boundary" role="alert">
        <section className="app-error-boundary__panel">
          <p className="app-error-boundary__eyebrow">RECUPERACIÓN DE PANTALLA</p>
          <h1>No se pudo mostrar este apartado</h1>
          <p>
            La sesión permanece activa. Puede intentar cargar nuevamente la
            pantalla o volver al inicio para seleccionar otro apartado.
          </p>
          <div className="app-error-boundary__actions">
            <button type="button" onClick={this.retry}>
              Reintentar
            </button>
            <button
              className="app-error-boundary__secondary"
              type="button"
              onClick={this.returnHome}
            >
              Volver al inicio
            </button>
          </div>
        </section>
      </main>
    )
  }
}
