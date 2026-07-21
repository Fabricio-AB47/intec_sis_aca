import { AuthShell } from './AuthShell'
import type { UserProfile, UserSession } from '../../types/app'

type ProfileSelectionViewProps = {
  session: UserSession
  loading: boolean
  error: string
  onSelect: (role: string) => void
  onLogout: () => void
}

const administrativeRoles = new Set([
  'ADMINISTRADOR',
  'FINANCIERO',
  'BIENESTAR',
  'ACADEMICO',
  'ADMISIONES',
  'RECTOR',
  'VICERRECTOR',
  'SOPORTE',
  'INVITADO_SOP',
  'SECRETARIA',
])

function destination(profile: UserProfile) {
  if (profile.rol === 'ESTUDIANTE') {
    return { order: 1, initial: 'E', title: 'Estudiante', detail: 'Portal académico, notas y servicios estudiantiles' }
  }
  if (profile.rol === 'DOCENTE') {
    return { order: 2, initial: 'D', title: 'Docente', detail: 'Cursos, calificaciones e informes docentes' }
  }
  if (administrativeRoles.has(profile.rol)) {
    return { order: 3, initial: 'A', title: 'Administrativo', detail: `Gestión institucional · ${profile.rol.replaceAll('_', ' ')}` }
  }
  return { order: 4, initial: 'P', title: profile.rol, detail: 'Acceso institucional' }
}

export function ProfileSelectionView({
  session,
  loading,
  error,
  onSelect,
  onLogout,
}: Readonly<ProfileSelectionViewProps>) {
  const profiles = (session.perfiles?.length ? session.perfiles : [session])
    .filter((profile, index, items) => items.findIndex((item) => item.rol === profile.rol) === index)
    .sort((left, right) => destination(left).order - destination(right).order)

  return (
    <AuthShell title="Seleccione su acceso" subtitle={`Hola, ${session.nombres || session.login}. ¿A dónde desea ingresar?`}>
      <div className="profile-selection" aria-label="Perfiles disponibles">
        {profiles.map((profile) => {
          const option = destination(profile)
          return (
            <button
              key={profile.rol}
              type="button"
              className="profile-option"
              onClick={() => onSelect(profile.rol)}
              disabled={loading}
            >
              <span className="profile-option__icon" aria-hidden="true">{option.initial}</span>
              <span className="profile-option__copy">
                <strong>{option.title}</strong>
                <small>{option.detail}</small>
              </span>
              <span className="profile-option__arrow" aria-hidden="true">›</span>
            </button>
          )
        })}

        {error ? <p className="error-banner" role="alert">{error}</p> : null}

        <button type="button" className="profile-logout" onClick={onLogout} disabled={loading}>
          Cerrar sesión
        </button>
      </div>
    </AuthShell>
  )
}
