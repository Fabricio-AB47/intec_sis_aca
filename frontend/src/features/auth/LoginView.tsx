import type { FormEventHandler } from 'react'

import { AuthShell } from './AuthShell'

type LoginViewProps = {
  login: string
  password: string
  showPassword: boolean
  loading: boolean
  error: string
  onLoginChange: (value: string) => void
  onPasswordChange: (value: string) => void
  onTogglePassword: () => void
  onSubmit: FormEventHandler<HTMLFormElement>
  onOpenTeacherEvaluation?: () => void
}

export function LoginView({
  login,
  password,
  showPassword,
  loading,
  error,
  onLoginChange,
  onPasswordChange,
  onTogglePassword,
  onSubmit,
  onOpenTeacherEvaluation,
}: Readonly<LoginViewProps>) {
  return (
    <AuthShell title="Acceso" subtitle="Ingrese con su cuenta institucional">
      <form className="login-form" onSubmit={onSubmit}>
        <label className="field">
          <span>Usuario o correo</span>
          <input
            value={login}
            onChange={(event) => onLoginChange(event.target.value)}
            placeholder="usuario o usuario@intec.edu.ec"
            autoComplete="username"
            required
          />
        </label>

        <label className="field">
          <span>Contrasena</span>
          <div className="password-shell">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              placeholder="Contrasena"
              autoComplete="current-password"
              required
            />
            <button
              type="button"
              className="password-toggle"
              onClick={onTogglePassword}
              aria-label={showPassword ? 'Ocultar contrasena' : 'Mostrar contrasena'}
            >
              {showPassword ? 'Ocultar' : 'Mostrar'}
            </button>
          </div>
        </label>

        <button className="submit-button" type="submit" disabled={loading}>
          {loading ? 'Validando...' : 'Iniciar sesion'}
        </button>

        {onOpenTeacherEvaluation ? (
          <button type="button" className="public-evaluation-button" onClick={onOpenTeacherEvaluation}>
            Evaluacion docente sin iniciar sesion
          </button>
        ) : null}

        {error ? (
          <p className="error-banner" role="alert" aria-live="polite">
            {error}
          </p>
        ) : null}
      </form>
    </AuthShell>
  )
}
