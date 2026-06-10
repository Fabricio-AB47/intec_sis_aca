import type { ExcelSqlCrossResponse } from '../../types/app'

type CruceDatosViewProps = {
  displayName: string
  loading: boolean
  downloadLoading: boolean
  error: string
  data: ExcelSqlCrossResponse | null
  onLoad: () => void
  onDownload: () => void
}

const statusLabels: Record<string, string> = {
  EN_TODOS: 'En todos',
  BALANCE_MOODLE: 'Registro + Moodle',
  BALANCE_TABLAS: 'Registro + tablas',
  MOODLE_TABLAS: 'Moodle + tablas',
  SOLO_BALANCE: 'No cruzada',
  SOLO_MOODLE: 'No cruzada',
  SOLO_TABLAS: 'No cruzada',
}

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function valueOrDash(value?: string): string {
  return value?.trim() || '-'
}

function statusLabel(value?: string): string {
  if (!value) return 'Pendiente'
  return statusLabels[value] || value
}

function rowStatusLabel(estado?: string, resultado?: string, origen?: string): string {
  if (resultado === 'NO_CRUZADA') {
    return origen ? `No cruzada: ${origen}` : 'No cruzada'
  }
  return statusLabel(estado)
}

function statusClass(value?: string): string {
  return `cruce-status cruce-status--${(value || 'pendiente').toLowerCase().replaceAll('_', '-')}`
}

export function CruceDatosView({
  displayName,
  loading,
  downloadLoading,
  error,
  data,
  onLoad,
  onDownload,
}: Readonly<CruceDatosViewProps>) {
  const summary = data?.summary
  const rows = data?.rows || []
  const warnings = data?.warnings || []

  const stepItems = [
    {
      label: 'Paso 1',
      title: 'DATOS_ESTUD',
      value: formatNumber(summary?.total_tablas),
      detail: data?.sql_tables?.join(' + ') || 'DATOS_ESTUD + CARRERAXESTUD + PENSUM',
    },
    {
      label: 'Paso 2',
      title: 'Usuarios Moodle',
      value: formatNumber(summary?.total_moodle),
      detail: data?.files?.data_moodle || 'data_moodle.xlsx',
    },
    {
      label: 'Paso 3',
      title: 'Registro',
      value: formatNumber(summary?.total_registro),
      detail: data?.files?.registro || 'registro.xlsx',
    },
  ]

  const statItems = [
    ['Total SQL', summary?.total_sql_activos],
    ['Total DATOS_ESTUD', summary?.datos_estud_activos],
    ['Cruzadas', summary?.cruzadas],
    ['No cruzadas', summary?.no_cruzadas],
    ['En todos', summary?.en_todos],
    ['Registro + DATOS_ESTUD', summary?.balance_tablas],
    ['Moodle + DATOS_ESTUD', summary?.moodle_tablas],
    ['Solo DATOS_ESTUD', summary?.solo_tablas],
    ['Con ultima matricula', summary?.total_con_carreraxestud],
    ['Sin matricula', summary?.total_sin_carreraxestud],
    ['Con nivel PENSUM', summary?.total_con_pensum],
    ['Sin nivel PENSUM', summary?.total_sin_pensum],
    ['Duplicados cedula', summary?.duplicados_cedula_sql],
  ] as const

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Cruce de informacion</p>
          <h1>Excel, Moodle y tablas SQL</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Cruce datos</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid cruce-steps-grid">
        {stepItems.map((item) => (
          <article key={item.label} className="student-card cruce-step-card">
            <span>{item.label}</span>
            <strong>{item.title}</strong>
            <h2>{item.value}</h2>
            <small>{item.detail}</small>
          </article>
        ))}
      </section>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        {statItems.map(([label, value]) => (
          <article key={label} className="student-card student-card--stat matricula-stat-card">
            <p>{label}</p>
            <h2>{formatNumber(value)}</h2>
            <small>Nombres normalizados</small>
          </article>
        ))}
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide cruce-results-card">
          <div className="card-head">
            <h3>Detalle completo del cruce</h3>
            <span>{loading ? 'Procesando...' : `${formatNumber(rows.length)} filas`}</span>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={onLoad} disabled={loading}>
              {loading ? 'Procesando...' : 'Procesar todo'}
            </button>
            <button type="button" onClick={onDownload} disabled={loading || downloadLoading || rows.length === 0}>
              {downloadLoading ? 'Generando Excel...' : 'Descargar Excel'}
            </button>
          </div>

          {error ? <p className="teams-error">{error}</p> : null}
          {warnings.length > 0 ? (
            <div className="cruce-warning-list">
              {warnings.map((warning) => (
                <p key={warning} className="teams-message">
                  {warning}
                </p>
              ))}
            </div>
          ) : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table cruce-table">
              <thead>
                <tr>
                  <th>Estudiante</th>
                  <th>ESTADO</th>
                  <th>Nivel</th>
                  <th>Ultima matricula</th>
                  <th>Resultado</th>
                  <th>Codigo / Cedula</th>
                  <th>Correo Intec</th>
                  <th>Moodle</th>
                  <th>Registro</th>
                  <th>Registros</th>
                </tr>
              </thead>
              <tbody>
                {rows.length > 0 ? (
                  rows.map((row, index) => (
                    <tr key={`${row.estado_cruce}-${row.clave_normalizada}-${row.moodle?.email || row.tablas?.codigo_estud}-${index}`}>
                      <td>
                        <div className="cruce-source-stack">
                          <strong>{valueOrDash(row.tablas?.nombre || row.nombre_validado)}</strong>
                          <small>{valueOrDash(row.clave_normalizada)}</small>
                        </div>
                      </td>
                      <td>
                        <div className="cruce-source-stack">
                          <span>{valueOrDash(row.tablas?.estado_nombre)}</span>
                          <small>{valueOrDash(row.tablas?.estado)}</small>
                        </div>
                      </td>
                      <td>
                        <div className="cruce-source-stack">
                          <span>{valueOrDash(row.tablas?.nivel_semestre)}</span>
                          <small>{valueOrDash(row.tablas?.pensum_nomb_materia)}</small>
                        </div>
                      </td>
                      <td>
                        <div className="cruce-source-stack">
                          <span>{valueOrDash(row.tablas?.fecha_matricula || row.tablas?.codigo_periodo)}</span>
                          <small>
                            {valueOrDash(
                              [
                                row.tablas?.cod_anio_basica,
                                row.tablas?.codigo_materia,
                                row.tablas?.num_matricula,
                              ]
                                .filter(Boolean)
                                .join(' / ')
                            )}
                          </small>
                        </div>
                      </td>
                      <td>
                        <span className={statusClass(row.estado_cruce)}>
                          {rowStatusLabel(row.estado_cruce, row.resultado_cruce, row.origen_no_cruzado)}
                        </span>
                      </td>
                      <td>
                        <div className="cruce-source-stack">
                          <span>{valueOrDash(row.tablas?.codigo_estud)}</span>
                          <small>{valueOrDash(row.tablas?.cedula)}</small>
                        </div>
                      </td>
                      <td>{valueOrDash(row.tablas?.correointec_final || row.tablas?.correointec || row.tablas?.correo)}</td>
                      <td>
                        <div className="cruce-source-stack">
                          <span>{valueOrDash(row.moodle?.email)}</span>
                          <small>{valueOrDash(row.moodle?.nombre || row.moodle?.username)}</small>
                        </div>
                      </td>
                      <td>
                        <div className="cruce-source-stack cruce-source-stack--compact">
                          <span>{valueOrDash(row.balance?.identificacion)}</span>
                          <small>{valueOrDash(row.balance?.razon_social)}</small>
                        </div>
                      </td>
                      <td>
                        R{row.balance?.registros ?? 0} / M{row.moodle?.registros ?? 0} / T{row.tablas?.registros ?? 0}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={10}>Sin informacion procesada.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="student-card cruce-criteria-card">
          <div className="card-head">
            <h3>Validacion</h3>
            <span>{summary?.total_tablas ? `Base ${formatNumber(summary.total_tablas)}` : 'Base SQL'}</span>
          </div>
          <p className="empty-block">
            {data?.criteria?.validacion ||
              'DATOS_ESTUD es la unica fuente SQL para el total antes de cruzar contra Registro y Moodle.'}
          </p>
        </article>
      </section>
    </>
  )
}
