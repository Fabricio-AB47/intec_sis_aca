import { AuthShell } from './AuthShell'

type SessionStatusViewProps = {
  message: string
  detail?: string
  onRetry?: () => void
  onLogout?: () => void
}

export function SessionStatusView({ message, detail, onRetry, onLogout }: Readonly<SessionStatusViewProps>) {
  return (
    <AuthShell title="REPORTERIA" subtitle={message}>
      <p className="empty-block auth-status-copy">
        {detail || 'Espera un momento mientras validamos la sesión y configuramos el acceso.'}
      </p>
      {onRetry || onLogout ? (
        <div className="auth-status-actions">
          {onRetry ? <button type="button" className="profile-logout" onClick={onRetry}>Reintentar</button> : null}
          {onLogout ? <button type="button" className="profile-logout" onClick={onLogout}>Cerrar sesión</button> : null}
        </div>
      ) : null}
    </AuthShell>
  )
}
