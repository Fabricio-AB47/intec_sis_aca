import { useMemo, useState } from 'react'

import {
  fetchSenescytStudentData,
  searchSenescytStudentData,
  updateSenescytStudentData,
} from '../../lib/api'
import type {
  SenescytStudentDataDetailResponse,
  SenescytStudentDataSearchItem,
} from '../../types/app'

type ActualizarDatosEstudianteViewProps = {
  displayName: string
}

const FIELD_GROUPS: Array<{ title: string; fields: string[] }> = [
  {
    title: 'Identificacion',
    fields: ['tipoDocumentoId', 'numeroIdentificacion', 'primerApellido', 'segundoApellido', 'primerNombre', 'segundoNombre'],
  },
  {
    title: 'Datos personales',
    fields: [
      'sexoId',
      'generoId',
      'estadocivilId',
      'etniaId',
      'pueblonacionalidadId',
      'tipoSangre',
      'discapacidad',
      'porcentajeDiscapacidad',
      'numCarnetConadis',
      'tipoDiscapacidad',
      'fechaNacimiento',
    ],
  },
  {
    title: 'Residencia',
    fields: [
      'paisNacionalidadId',
      'provinciaNacimientoId',
      'cantonNacimientoId',
      'paisResidenciaId',
      'provinciaResidenciaId',
      'cantonResidenciaId',
    ],
  },
  {
    title: 'Carrera y matricula',
    fields: [
      'tipoColegioId',
      'modalidadCarrera',
      'jornadaCarrera',
      'fechaInicioCarrera',
      'fechaMatricula',
      'tipoMatriculaId',
      'nivelAcademicoQueCursa',
      'duracionPeriodoAcademico',
      'haRepetidoAlMenosUnaMateria',
      'paraleloId',
      'haPerdidoLaGratuidad',
      'recibePensionDiferenciada',
    ],
  },
  {
    title: 'Practicas, becas y vinculacion',
    fields: [
      'estudianteocupacionId',
      'ingresosestudianteId',
      'bonodesarrolloId',
      'haRealizadoPracticasPreprofesionales',
      'nroHorasPracticasPreprofesionalesPorPeriodo',
      'entornoInstitucionalPracticasProfesionales',
      'sectorEconomicoPracticaProfesional',
      'tipoBecaId',
      'primeraRazonBecaId',
      'segundaRazonBecaId',
      'terceraRazonBecaId',
      'cuartaRazonBecaId',
      'quintaRazonBecaId',
      'sextaRazonBecaId',
      'montoBeca',
      'porcientoBecaCoberturaArancel',
      'porcientoBecaCoberturaManuntencion',
      'financiamientoBeca',
      'montoAyudaEconomica',
      'montoCreditoEducativo',
      'participaEnProyectoVinculacionSociedad',
      'tipoAlcanceProyectoVinculacionId',
    ],
  },
  {
    title: 'Contacto y hogar',
    fields: [
      'correoElectronico',
      'numeroCelular',
      'nivelFormacionPadre',
      'nivelFormacionMadre',
      'ingresoTotalHogar',
      'cantidadMiembrosHogar',
    ],
  },
]

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function formatPercent(value?: number): string {
  return `${new Intl.NumberFormat('es-EC', { maximumFractionDigits: 2 }).format(value ?? 0)}%`
}

function handleError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function valueText(value: string | number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value)
}

function buildChangedFields(
  current: Record<string, string | number | null>,
  original: Record<string, string | number | null>,
): Record<string, string | number | null> {
  return Object.fromEntries(
    Object.entries(current).filter(([key, value]) => valueText(value) !== valueText(original[key])),
  )
}

function groupedColumns(columns: string[]): Array<{ title: string; fields: string[] }> {
  const known = new Set(FIELD_GROUPS.flatMap((group) => group.fields))
  const groups = FIELD_GROUPS.map((group) => ({
    title: group.title,
    fields: group.fields.filter((field) => columns.includes(field)),
  })).filter((group) => group.fields.length > 0)
  const rest = columns.filter((field) => !known.has(field))
  return rest.length ? [...groups, { title: 'Otros campos SENESCYT', fields: rest }] : groups
}

export function ActualizarDatosEstudianteView({ displayName }: Readonly<ActualizarDatosEstudianteViewProps>) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SenescytStudentDataSearchItem[]>([])
  const [selected, setSelected] = useState<SenescytStudentDataSearchItem | null>(null)
  const [detail, setDetail] = useState<SenescytStudentDataDetailResponse | null>(null)
  const [formFields, setFormFields] = useState<Record<string, string | number | null>>({})
  const [originalFields, setOriginalFields] = useState<Record<string, string | number | null>>({})
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const columns = detail?.report_columns || []
  const fieldGroups = useMemo(() => groupedColumns(columns), [columns])
  const changedFields = useMemo(() => buildChangedFields(formFields, originalFields), [formFields, originalFields])
  const changedCount = Object.keys(changedFields).length

  async function runSearch() {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await searchSenescytStudentData(query)
      setResults(payload.rows || [])
    } catch (requestError) {
      setError(handleError(requestError, 'Error buscando estudiantes.'))
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  async function loadStudent(student: SenescytStudentDataSearchItem) {
    setSelected(student)
    setDetailLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await fetchSenescytStudentData(student.codigo_estud)
      const fields = payload.fields || {}
      setDetail(payload)
      setFormFields(fields)
      setOriginalFields(fields)
    } catch (requestError) {
      setError(handleError(requestError, 'Error cargando datos del estudiante.'))
      setDetail(null)
      setFormFields({})
      setOriginalFields({})
    } finally {
      setDetailLoading(false)
    }
  }

  async function saveChanges() {
    if (!selected || changedCount === 0) {
      setMessage('No hay cambios para guardar.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const payload = await updateSenescytStudentData(selected.codigo_estud, changedFields)
      const fields = payload.fields || {}
      setDetail(payload)
      setFormFields(fields)
      setOriginalFields(fields)
      setSelected(payload.student || selected)
      setResults((items) => items.map((item) => (item.codigo_estud === selected.codigo_estud ? payload.student || item : item)))
      setMessage(payload.message || 'Datos actualizados.')
    } catch (requestError) {
      setError(handleError(requestError, 'Error actualizando datos del estudiante.'))
    } finally {
      setSaving(false)
    }
  }

  function updateField(field: string, value: string) {
    setFormFields((current) => ({ ...current, [field]: value }))
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">DATOS_ESTUD</p>
          <h1>Actualizar datos estudiante</h1>
          <p className="report-description">
            Edita los campos utilizados para el reporte Datos SENESCYT de estudiantes.
          </p>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Actualización SENESCYT</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--content senescyt-update-grid">
        <article className="student-card senescyt-update-search">
          <div className="card-head">
            <h3>Buscar estudiante</h3>
            <span>{formatNumber(results.length)} resultado(s)</span>
          </div>

          <form
            className="senescyt-update-search-form"
            onSubmit={(event) => {
              event.preventDefault()
              void runSearch()
            }}
          >
            <label>
              Cedula, codigo o nombre
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar estudiante" />
            </label>
            <button type="submit" disabled={loading}>{loading ? 'Buscando...' : 'Buscar'}</button>
          </form>

          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-success">{message}</p> : null}

          <div className="senescyt-student-list">
            {results.map((student) => (
              <button
                key={student.codigo_estud}
                type="button"
                className={`senescyt-student-option ${selected?.codigo_estud === student.codigo_estud ? 'senescyt-student-option--active' : ''}`}
                onClick={() => void loadStudent(student)}
              >
                <strong>{student.estudiante}</strong>
                <span>{student.numero_identificacion} - {student.nombre_carrera}</span>
                <small>{formatNumber(student.campos_pendientes)} pendiente(s) - {formatPercent(student.porcentaje_lleno)}</small>
              </button>
            ))}
            {results.length === 0 ? <p className="form-success">Busca y selecciona un estudiante para editar.</p> : null}
          </div>
        </article>

        <article className="student-card student-card--wide senescyt-update-form-card">
          <div className="card-head">
            <h3>{selected ? selected.estudiante : 'Datos SENESCYT'}</h3>
            <span>{detailLoading ? 'Cargando...' : `${formatNumber(changedCount)} cambio(s)`}</span>
          </div>

          {detail?.student ? (
            <div className="matricula-acad-preview senescyt-update-summary">
              <div>
                <span>Cedula</span>
                <strong>{detail.student.numero_identificacion}</strong>
              </div>
              <div>
                <span>Carrera</span>
                <strong>{detail.student.nombre_carrera}</strong>
              </div>
              <div>
                <span>Campos pendientes</span>
                <strong>{formatNumber(detail.student.campos_pendientes)}</strong>
              </div>
              <div>
                <span>% lleno</span>
                <strong>{formatPercent(detail.student.porcentaje_lleno)}</strong>
              </div>
            </div>
          ) : null}

          {selected && columns.length > 0 ? (
            <>
              <div className="senescyt-update-actions">
                <button type="button" onClick={() => void saveChanges()} disabled={saving || changedCount === 0}>
                  {saving ? 'Guardando...' : 'Guardar cambios'}
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => setFormFields(originalFields)}
                  disabled={saving || changedCount === 0}
                >
                  Restaurar
                </button>
              </div>

              <div className="senescyt-update-groups">
                {fieldGroups.map((group) => (
                  <section key={group.title} className="senescyt-update-group">
                    <h3>{group.title}</h3>
                    <div className="senescyt-update-fields">
                      {group.fields.map((field) => (
                        <label key={field}>
                          <span>{field}</span>
                          <input
                            value={valueText(formFields[field])}
                            onChange={(event) => updateField(field, event.target.value)}
                          />
                        </label>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </>
          ) : (
            <p className="form-success">Selecciona un estudiante para cargar los campos del reporte SENESCYT.</p>
          )}
        </article>
      </section>
    </>
  )
}
