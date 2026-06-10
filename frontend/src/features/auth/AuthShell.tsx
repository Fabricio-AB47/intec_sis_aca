import type { ReactNode } from 'react'

type AuthShellProps = {
  title: ReactNode
  subtitle?: string
  children?: ReactNode
}

export function AuthShell({ title, subtitle, children }: Readonly<AuthShellProps>) {
  return (
    <main className="app app--auth">
      <section className="auth-scene">
        <div className="star-layer" aria-hidden="true" />
        <div className="shooting shooting--one" aria-hidden="true" />
        <div className="shooting shooting--two" aria-hidden="true" />
        <div className="planet planet--main" aria-hidden="true" />
        <div className="planet planet--small" aria-hidden="true" />
        <div className="planet planet--tiny" aria-hidden="true" />

        <div className="auth-frame">
          <div className="auth-layout">
            <section className="showcase-panel">
              <div className="brand-row">
                <div className="brand-logo">IN</div>
                <div>
                  <strong>INTEC</strong>
                  <span className="eyebrow">REPORTERIA</span>
                </div>
              </div>

              <div className="showcase-copy">
                <h1>
                  Acceso al <span>sistema</span>
                </h1>
              </div>
            </section>

            <section className="login-panel">
              <div className="login-panel__inner">
                <h2>{title}</h2>
                {subtitle ? <p className="login-copy">{subtitle}</p> : null}
                {children}
              </div>
            </section>
          </div>
        </div>
      </section>
    </main>
  )
}
