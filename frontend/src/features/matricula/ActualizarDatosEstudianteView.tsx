import { useMemo, useState } from 'react'

import {
  fetchLegacyDataUpdateRecord,
  searchLegacyDataUpdate,
  updateLegacyDataUpdateRecord,
} from '../../lib/api'
import type {
  LegacyDataUpdateDetailResponse,
  LegacyDataUpdatePerson,
  LegacyDataUpdateTarget,
} from '../../types/app'

type ActualizarDatosEstudianteViewProps = {
  displayName: string
}

const FIELD_GROUPS: Array<{ title: string; fields: string[] }> = [
  {
    title: 'Identificacion',
    fields: ['tipodocumento', 'tipoDocumentoId', 'Cedula_Est', 'Apellidos_nombre', 'numeroIdentificacion', 'primerApellido', 'segundoApellido', 'primerNombre', 'segundoNombre'],
  },
  {
    title: 'Datos personales',
    fields: [
      'Sexo',
      'generoId',
      'estadocivilId',
      'EstadoCivil',
      'etniaId',
      'Etnia',
      'pueblonacionalidadId',
      'tipoSangre',
      'tiposangre',
      'discapacidad',
      'porcentajeDiscapacidad',
      'Porce_Capacidad',
      'numCarnetConadis',
      'No_Carnet',
      'tipoDiscapacidad',
      'Tipo_Capacidad',
      'fechaNacimiento',
      'Fecha_Nac',
    ],
  },
  {
    title: 'Residencia',
    fields: [
      'paisNacionalidadId',
      'provinciaNacimeintoId',
      'cantonNacimeintoId',
      'provinciaNacimientoId',
      'cantonNacimientoId',
      'paisResidenciaId',
      'codprov',
      'Canton',
      'provinciaResidenciaId',
      'cantonResidenciaId',
      'ciudad',
      'calle_principal',
      'referencia',
      'NumHogar',
    ],
  },
  {
    title: 'Carrera y matricula',
    fields: [
      'tipoColegioId',
      'ModalidadEstudio',
      'modalidadCarrera',
      'Jornada',
      'jornadaCarrera',
      'Fecha_Ingreso',
      'fechaInicioCarrera',
      'fechaMatricula',
      'tipoMatriculaId',
      'nivelAcademicoQueCursa',
      'duracionPeriodoAcademico',
      'haRepetidoAlMenosUnaMateria',
      'Paralelo',
      'paraleloId',
      'haPerdidoLaGratuidad',
      'recibePensionDiferenciada',
    ],
  },
  {
    title: 'Practicas, becas y vinculacion',
    fields: [
      'Ocupacion',
      'estudianteocupacionId',
      'ingresoEstudianteId',
      'ingresosestudianteId',
      'bonoDesarrolloId',
      'bonodesarrolloId',
      'haRealizadoPracticasPreprofesionales',
      'nroHorasPracticasPreprofesionales',
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
      'correo',
      'correoElectronico',
      'movil',
      'numeroCelular',
      'nivelFormacionPadre',
      'nivelFormacionMadre',
      'IngresoHogar',
      'ingresoTotalHogar',
      'Numpersonasvive',
      'cantidadMiembrosHogar',
      'correointec',
    ],
  },
]

const TEACHER_FIELD_GROUPS: Array<{ title: string; fields: string[] }> = [
  {
    title: 'Identificacion',
    fields: ['tipoDocumentoId', 'cedula_doc', 'apellidos_nombre', 'sexo', 'generoId', 'estado_civil', 'etniaId', 'nacionalidad'],
  },
  {
    title: 'Contacto y residencia',
    fields: ['Direccion', 'provinciaSufragio', 'movil', 'correop', 'correo', 'numDomicilio', 'fecha_nac', 'paisNacionalidadId', 'tiposangre'],
  },
  {
    title: 'Discapacidad y salud',
    fields: ['discapacidad', 'porcen_discapa', 'tipo_discapa', 'carnet_conadis', 'tipoEnfermedadCatastrofica'],
  },
  {
    title: 'Relacion institucional',
    fields: [
      'nivelFormacion',
      'fechaIngresoIES',
      'fechaSalidaIES',
      'relacionLaboralIESId',
      'ingresoConCursoMeritos',
      'escalafonDocenteId',
      'cargoDirectivoId',
      'tiempoDedicacionId',
      'nombreUnidadAcademica',
    ],
  },
  {
    title: 'Carga docente',
    fields: [
      'nroasignaturasdocente',
      'nroHorasLaborablesSemanaEnCarreraPrograma',
      'nroHorasClaseSemanaCarreraPrograma',
      'nroHorasInvestigacionSemanaCarreraPrograma',
      'nroHorasAdministrativasSemanaCarreraPrograma',
      'nroHorasOtrasActividadesSemanaCarreraPrograma',
      'nroHorasVinculacionSociedad',
      'salarioMensual',
    ],
  },
  {
    title: 'Docencia, estudios y beca',
    fields: [
      'docenciaTecnicoSuperior',
      'docenciaTecnologico',
      'docenciaTecnologicoUniversitario',
      'docenciaEspecializacionTecnologica',
      'docenciaMaestriaTecnologica',
      'estaEnPeriodoSabatico',
      'fechaInicioPeriodoSabatico',
      'estaCursandoEstudiosId',
      'institucionDOndeCursaEstudios',
      'paisEstudiosId',
      'tituloAObtener',
      'poseeBecaId',
      'tipoBecaId',
      'montoBeca',
      'financiamientoBecaId',
    ],
  },
  {
    title: 'Investigacion',
    fields: ['pubRevistasCienInIndexadasId', 'numPubRevistasCientifIndexadas'],
  },
]

const STUDENT_HIDDEN_SYSTEM_FIELDS = new Set([
  'ModalidadEstudio',
  'Jornada',
  'Fecha_Ingreso',
  'fechaMatricula',
  'tipoMatriculaId',
  'nivelAcademicoQueCursa',
  'duracionPeriodoAcademico',
  'primeraRazonBecaId',
  'segundaRazonBecaId',
  'terceraRazonBecaId',
  'cuartaRazonBecaId',
  'quintaRazonBecaId',
  'sextaRazonBecaId',
  'porcientoBecaCoberturaArancel',
  'porcientoBecaCoberturaManuntencion',
  'tipoBecaId',
  'financiamientoBeca',
  'generoId',
  'Paralelo',
  'NumHogar',
  'montoBeca',
])

const STUDENT_READONLY_FIELDS = new Set(['Cedula_Est', 'correointec'])

const STUDENT_FIELD_LABELS: Record<string, string> = {
  tipodocumento: 'Tipo de documento',
  Cedula_Est: 'Numero de documento de identificacion',
  Apellidos_nombre: 'Apellidos y nombres',
  Sexo: 'Sexo',
  generoId: 'Genero',
  EstadoCivil: 'Estado civil',
  Etnia: 'Etnia',
  Nacionalidad: 'Pueblo y nacionalidad',
  tiposangre: 'Tipo de sangre',
  discapacidad: 'Discapacidad',
  Porce_Capacidad: 'Porcentaje de discapacidad',
  No_Carnet: 'Numero de carnet',
  Tipo_Capacidad: 'Tipo de discapacidad',
  Fecha_Nac: 'Fecha de nacimiento',
  paisNacionalidadId: 'Pais de nacionalidad',
  provinciaNacimeintoId: 'Provincia de nacimiento',
  cantonNacimeintoId: 'Canton de nacimiento',
  paisResidenciaId: 'Pais de residencia',
  codprov: 'Provincia de residencia',
  Canton: 'Canton de residencia',
  tipoColegioId: 'Tipo de colegio',
  ModalidadEstudio: 'Modalidad de estudio',
  Jornada: 'Jornada',
  Fecha_Ingreso: 'Fecha de ingreso',
  fechaMatricula: 'Fecha de matricula',
  tipoMatriculaId: 'Tipo de matricula',
  nivelAcademicoQueCursa: 'Nivel academico que cursa',
  duracionPeriodoAcademico: 'Duracion del periodo academico',
  haRepetidoAlMenosUnaMateria: 'Ha repetido al menos una materia',
  Paralelo: 'Paralelo',
  haPerdidoLaGratuidad: 'Ha perdido la gratuidad',
  recibePensionDiferenciada: 'Posee pension diferenciada',
  Ocupacion: 'Ocupacion',
  ingresoEstudianteId: 'Uso de ingresos del estudiante',
  bonoDesarrolloId: 'Recibe bono de desarrollo humano',
  haRealizadoPracticasPreprofesionales: 'Ha realizado practicas preprofesionales',
  nroHorasPracticasPreprofesionales: 'Horas de practicas preprofesionales',
  entornoInstitucionalPracticasProfesionales: 'Tipo de institucion de practicas',
  sectorEconomicoPracticaProfesional: 'Sector economico de practicas',
  tipoBecaId: 'Tipo de beca',
  montoBeca: 'Monto de beca',
  montoAyudaEconomica: 'Monto de ayuda economica',
  montoCreditoEducativo: 'Monto de credito educativo',
  participaEnProyectoVinculacionSociedad: 'Participa en proyecto de vinculacion',
  tipoAlcanceProyectoVinculacionId: 'Alcance del proyecto de vinculacion',
  correo: 'Correo personal',
  movil: 'Celular',
  nivelFormacionPadre: 'Nivel de formacion del padre',
  nivelFormacionMadre: 'Nivel de formacion de la madre',
  IngresoHogar: 'Ingreso del hogar',
  Numpersonasvive: 'Personas que viven en el hogar',
  ciudad: 'Ciudad de residencia',
  calle_principal: 'Calle principal',
  referencia: 'Referencia de domicilio',
  NumHogar: 'Telefono del hogar',
  correointec: 'Correo institucional',
}

const FALLBACK_FIELD_CATALOGS: Record<string, Array<{ value: string; label: string }>> = {
  tiposangre: [
    { value: '1', label: 'A +' },
    { value: '2', label: 'A -' },
    { value: '3', label: 'B +' },
    { value: '4', label: 'B -' },
    { value: '5', label: 'AB +' },
    { value: '6', label: 'AB -' },
    { value: '7', label: 'O +' },
    { value: '8', label: 'O -' },
  ],
}

const DATE_FIELDS = new Set(['Fecha_Nac', 'Fecha_Ingreso', 'fechaMatricula', 'fecha_nac', 'fechaIngresoIES', 'fechaSalidaIES', 'fechaInicioPeriodoSabatico'])
const NUMERIC_FIELDS = new Set([
  'Cedula_Est',
  'cedula_doc',
  'No_Carnet',
  'NumHogar',
  'Numpersonasvive',
  'IngresoHogar',
  'movil',
  'montoBeca',
  'montoAyudaEconomica',
  'montoCreditoEducativo',
  'salarioMensual',
  'numPubRevistasCientifIndexadas',
  'nroasignaturasdocente',
  'numDomicilio',
  'carnet_conadis',
  'nroHorasLaborablesSemanaEnCarreraPrograma',
  'nroHorasClaseSemanaCarreraPrograma',
  'nroHorasInvestigacionSemanaCarreraPrograma',
  'nroHorasAdministrativasSemanaCarreraPrograma',
  'nroHorasOtrasActividadesSemanaCarreraPrograma',
  'nroHorasVinculacionSociedad',
])

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

function fieldLabel(field: string, target: LegacyDataUpdateTarget): string {
  if (target === 'estudiantes' && STUDENT_FIELD_LABELS[field]) {
    return STUDENT_FIELD_LABELS[field]
  }
  return field
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim()
}

function inputTypeForField(field: string): string {
  if (DATE_FIELDS.has(field)) return 'date'
  if (NUMERIC_FIELDS.has(field)) return 'text'
  if (field.toLowerCase().includes('correo')) return 'email'
  return 'text'
}

function optionsWithCurrentValue(
  options: Array<{ value: string; label: string }> | undefined,
  currentValue: string | number | null | undefined,
): Array<{ value: string; label: string }> {
  const current = valueText(currentValue).trim()
  const baseOptions = options || []
  if (!current || baseOptions.some((option) => valueText(option.value).trim() === current)) {
    return baseOptions
  }
  return [{ value: current, label: `${current} (valor actual)` }, ...baseOptions]
}

function normalizeDocument(value: string | number | null | undefined): string {
  return valueText(value).replace(/\D/g, '')
}

function pickLegacyMatch(
  rows: LegacyDataUpdatePerson[] | undefined,
  query: string,
): LegacyDataUpdatePerson | null {
  const normalizedQuery = normalizeDocument(query)
  const source = rows || []
  if (!source.length) return null
  if (!normalizedQuery) return source[0]
  return source.find((person) => normalizeDocument(person.cedula) === normalizedQuery) || source[0]
}

function buildChangedFields(
  current: Record<string, string | number | null>,
  original: Record<string, string | number | null>,
): Record<string, string | number | null> {
  return Object.fromEntries(
    Object.entries(current).filter(([key, value]) => valueText(value) !== valueText(original[key])),
  )
}

function applyStudentDerivedValues(fields: Record<string, string | number | null>): Record<string, string | number | null> {
  const next = { ...fields }
  const sexo = valueText(next.Sexo)
  if (sexo === '1' || sexo === '2') next.generoId = sexo

  if (valueText(next.Etnia) !== '1') next.Nacionalidad = '34'

  if (valueText(next.haRealizadoPracticasPreprofesionales) === '2') {
    next.nroHorasPracticasPreprofesionales = 'NA'
    next.entornoInstitucionalPracticasProfesionales = '5'
    next.sectorEconomicoPracticaProfesional = '22'
  }

  if (valueText(next.discapacidad) === '2') {
    next.Porce_Capacidad = '0'
    next.No_Carnet = 'NA'
    next.Tipo_Capacidad = '7'
  }

  if (valueText(next.participaEnProyectoVinculacionSociedad) !== '1') {
    next.tipoAlcanceProyectoVinculacionId = '5'
  }

  if (!valueText(next.NumHogar)) next.NumHogar = '0'
  if (!valueText(next.porcientoBecaCoberturaManuntencion) || valueText(next.porcientoBecaCoberturaManuntencion) === '0') {
    next.porcientoBecaCoberturaManuntencion = 'NA'
  }
  ;(['montoAyudaEconomica', 'montoCreditoEducativo'] as const).forEach((field) => {
    const value = valueText(next[field])
    if (!value || value === 'NA') next[field] = '0'
  })

  const becaDefaults: Record<string, string> = {
    tipoBecaId: '3',
    primeraRazonBecaId: '2',
    segundaRazonBecaId: '2',
    terceraRazonBecaId: '2',
    cuartaRazonBecaId: '2',
    quintaRazonBecaId: '2',
    sextaRazonBecaId: '2',
    montoBeca: '0',
    porcientoBecaCoberturaArancel: 'NA',
    financiamientoBeca: '4',
  }
  Object.entries(becaDefaults).forEach(([field, defaultValue]) => {
    if (!valueText(next[field])) next[field] = defaultValue
  })

  return next
}

function shouldShowStudentField(field: string, fields: Record<string, string | number | null>): boolean {
  if (STUDENT_HIDDEN_SYSTEM_FIELDS.has(field)) return false
  if (field === 'Nacionalidad' && valueText(fields.Etnia) !== '1') return false
  if (
    ['nroHorasPracticasPreprofesionales', 'entornoInstitucionalPracticasProfesionales', 'sectorEconomicoPracticaProfesional'].includes(field)
    && valueText(fields.haRealizadoPracticasPreprofesionales) !== '1'
  ) {
    return false
  }
  if (['Porce_Capacidad', 'No_Carnet', 'Tipo_Capacidad'].includes(field) && valueText(fields.discapacidad) === '2') {
    return false
  }
  if (field === 'tipoAlcanceProyectoVinculacionId' && valueText(fields.participaEnProyectoVinculacionSociedad) !== '1') {
    return false
  }
  return true
}

function groupedColumns(columns: string[], target: LegacyDataUpdateTarget): Array<{ title: string; fields: string[] }> {
  const sourceGroups = target === 'docentes' ? TEACHER_FIELD_GROUPS : FIELD_GROUPS
  const known = new Set(sourceGroups.flatMap((group) => group.fields))
  const groups = sourceGroups.map((group) => ({
    title: group.title,
    fields: group.fields.filter((field) => columns.includes(field)),
  })).filter((group) => group.fields.length > 0)
  const rest = columns.filter((field) => !known.has(field))
  return rest.length ? [...groups, { title: target === 'docentes' ? 'Otros campos docente' : 'Otros campos estudiante', fields: rest }] : groups
}

export function ActualizarDatosEstudianteView({ displayName }: Readonly<ActualizarDatosEstudianteViewProps>) {
  const [target, setTarget] = useState<LegacyDataUpdateTarget>('estudiantes')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<LegacyDataUpdatePerson | null>(null)
  const [detail, setDetail] = useState<LegacyDataUpdateDetailResponse | null>(null)
  const [formFields, setFormFields] = useState<Record<string, string | number | null>>({})
  const [originalFields, setOriginalFields] = useState<Record<string, string | number | null>>({})
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const columns = detail?.columns || []
  const catalogs = detail?.catalogs || {}
  const visibleColumns = useMemo(
    () => target === 'estudiantes' ? columns.filter((field) => shouldShowStudentField(field, formFields)) : columns,
    [columns, formFields, target],
  )
  const fieldGroups = useMemo(() => groupedColumns(visibleColumns, target), [visibleColumns, target])
  const preparedFormFields = useMemo(
    () => target === 'estudiantes' ? applyStudentDerivedValues(formFields) : formFields,
    [formFields, target],
  )
  const changedFields = useMemo(() => buildChangedFields(preparedFormFields, originalFields), [originalFields, preparedFormFields])
  const changedCount = Object.keys(changedFields).length

  async function runSearch() {
    const cleanQuery = query.trim()
    if (!cleanQuery) {
      setError('Ingrese el numero de cedula o pasaporte.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    setSelected(null)
    setDetail(null)
    setFormFields({})
    setOriginalFields({})
    try {
      const studentPayload = await searchLegacyDataUpdate('estudiantes', cleanQuery)
      const student = pickLegacyMatch(studentPayload.rows, cleanQuery)
      if (student) {
        setTarget('estudiantes')
        await loadPerson(student, 'estudiantes')
        return
      }

      const teacherPayload = await searchLegacyDataUpdate('docentes', cleanQuery)
      const teacher = pickLegacyMatch(teacherPayload.rows, cleanQuery)
      if (teacher) {
        setTarget('docentes')
        await loadPerson(teacher, 'docentes')
        return
      }

      setError('No se encontro estudiante o docente con la cedula ingresada.')
    } catch (requestError) {
      setError(handleError(requestError, 'Error buscando estudiante o docente.'))
    } finally {
      setLoading(false)
    }
  }

  async function loadPerson(person: LegacyDataUpdatePerson, nextTarget: LegacyDataUpdateTarget = target) {
    setSelected(person)
    setDetailLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await fetchLegacyDataUpdateRecord(nextTarget, person.id)
      const fields = payload.fields || {}
      const normalizedFields = nextTarget === 'estudiantes' ? applyStudentDerivedValues(fields) : fields
      setDetail(payload)
      setFormFields(normalizedFields)
      setOriginalFields(fields)
    } catch (requestError) {
      setError(handleError(requestError, 'Error cargando datos para actualizacion.'))
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
      const payload = await updateLegacyDataUpdateRecord(target, selected.id, changedFields)
      const fields = payload.fields || {}
      const normalizedFields = target === 'estudiantes' ? applyStudentDerivedValues(fields) : fields
      setDetail(payload)
      setFormFields(normalizedFields)
      setOriginalFields(fields)
      setSelected(payload.person || selected)
      setMessage(payload.message || 'Datos actualizados.')
    } catch (requestError) {
      setError(handleError(requestError, 'Error actualizando datos.'))
    } finally {
      setSaving(false)
    }
  }

  function updateField(field: string, value: string) {
    setFormFields((current) => {
      const next = { ...current, [field]: value }
      return target === 'estudiantes' ? applyStudentDerivedValues(next) : next
    })
  }

  function closeSubscreen() {
    setSelected(null)
    setDetail(null)
    setFormFields({})
    setOriginalFields({})
    setMessage('')
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Actualizar_Datos legacy</p>
          <h1>Actualización de datos</h1>
          <p className="report-description">
            Edita solo la información que debe completar la persona. Los datos de matrícula, jornada, becas y campos repetitivos se toman del sistema.
          </p>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Estudiante y docente</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--content senescyt-update-grid">
        <article className="student-card senescyt-update-search">
          <div className="card-head">
            <h3>Ingrese su numero de cedula o pasaporte</h3>
            <span>{selected ? `${selected.tipo === 'docente' ? 'Docente' : 'Estudiante'} encontrado` : 'Busqueda unica'}</span>
          </div>

          <form
            className="senescyt-update-search-form"
            onSubmit={(event) => {
              event.preventDefault()
              void runSearch()
            }}
          >
            <label>
              Numero de cedula o pasaporte
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cedula o pasaporte" />
            </label>
            <button type="submit" className="senescyt-update-search-icon" disabled={loading} aria-label="Buscar por cedula o pasaporte" title="Buscar">
              {loading ? (
                <span>...</span>
              ) : (
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path d="M10.8 4.2a6.6 6.6 0 1 1 0 13.2 6.6 6.6 0 0 1 0-13.2Zm0 2a4.6 4.6 0 1 0 0 9.2 4.6 4.6 0 0 0 0-9.2Zm5.2 9.1 4 4-1.4 1.4-4-4 1.4-1.4Z" />
                </svg>
              )}
            </button>
          </form>

          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-success">{message}</p> : null}

          {!selected && !error ? <p className="form-success">Ingrese el documento y presione buscar para abrir el formulario correspondiente.</p> : null}
        </article>

      </section>

      {selected ? (
        <div className="senescyt-update-subscreen-backdrop" role="presentation">
          <section className="senescyt-update-subscreen" role="dialog" aria-modal="true" aria-label="Subpantalla de actualización de datos">
            <div className="senescyt-update-subscreen__head">
              <div>
                <span>{target === 'docentes' ? 'Actualizar docente' : 'Actualizar estudiante'}</span>
                <h2>{selected.nombre}</h2>
              </div>
              <div className="senescyt-update-subscreen__actions">
                <span>{detailLoading ? 'Cargando...' : `${formatNumber(changedCount)} cambio(s)`}</span>
                <button type="button" onClick={closeSubscreen}>Cerrar</button>
              </div>
            </div>

            {detail?.person ? (
              <div className="matricula-acad-preview senescyt-update-summary">
                <div>
                  <span>Cedula</span>
                  <strong>{detail.person.cedula}</strong>
                </div>
                <div>
                  <span>{target === 'docentes' ? 'Unidad / correo' : 'Carrera'}</span>
                  <strong>{detail.person.carrera || detail.person.correo || '-'}</strong>
                </div>
                <div>
                  <span>Campos pendientes</span>
                  <strong>{formatNumber(detail.person.campos_pendientes)}</strong>
                </div>
                <div>
                  <span>% lleno</span>
                  <strong>{formatPercent(detail.person.porcentaje_lleno)}</strong>
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
                        {group.fields.map((field) => {
                          const catalogOptions = catalogs[field]?.length ? catalogs[field] : FALLBACK_FIELD_CATALOGS[field]
                          const fieldOptions = optionsWithCurrentValue(catalogOptions, formFields[field])
                          const isReadonly = target === 'estudiantes' && STUDENT_READONLY_FIELDS.has(field)
                          const helpText = target === 'estudiantes' && field === 'correointec'
                            ? 'Correo institucional consultado desde el sistema.'
                            : ''
                          return (
                          <label key={field}>
                            <span>{fieldLabel(field, target)}</span>
                            {fieldOptions.length ? (
                              <select
                                value={valueText(formFields[field])}
                                onChange={(event) => updateField(field, event.target.value)}
                                disabled={isReadonly}
                              >
                                <option value="">Seleccione</option>
                                {fieldOptions.map((option) => (
                                  <option key={`${field}-${option.value}`} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <input
                                type={inputTypeForField(field)}
                                inputMode={NUMERIC_FIELDS.has(field) ? 'numeric' : undefined}
                                value={valueText(formFields[field])}
                                onChange={(event) => updateField(field, event.target.value)}
                                readOnly={isReadonly}
                              />
                            )}
                            {helpText ? <small>{helpText}</small> : null}
                          </label>
                          )
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              </>
            ) : (
              <p className="form-success">Cargando campos editables...</p>
            )}
          </section>
        </div>
      ) : null}
    </>
  )
}
