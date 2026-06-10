import { AuthShell } from './AuthShell'

type SessionStatusViewProps = {
  message: string
}

export function SessionStatusView({ message }: Readonly<SessionStatusViewProps>) {
  return (
    <AuthShell title="REPORTERIA" subtitle={message}>
      <p className="empty-block auth-status-copy">
        Espera un momento mientras validamos la sesion y configuramos el acceso.
      </p>
    </AuthShell>
  )
}
