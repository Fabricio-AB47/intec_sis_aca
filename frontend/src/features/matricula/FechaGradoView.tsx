import { useEffect, useMemo, useState } from 'react'
import {
  downloadFechaGradoTemplate,
  fetchFechaGradoCatalog,
  fetchFechaGradoStudents,
  importFechaGradoExcel,
  saveFechaGrado,
} from '../../lib/api'
import type { FechaGradoCatalogResponse, FechaGradoStudent } from '../../types/app'

type FechaGradoViewProps = {
  displayName: string
}

function valueOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text || '-'
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function FechaGradoView({ displayName }: Readonly<FechaGradoViewProps>) {
  const [catalog, setCatalog] = useState<FechaGradoCatalogResponse>({})
  const [periodo, setPeriodo] = useState('')
  const [carrera, setCarrera] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [students, setStudents] = useState<FechaGradoStudent[]>([])
  const [dates, setDates] = useState<Record<string, string>>({})
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [importing, setImporting] = useState(false)
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const dirtyItems = useMemo(
    () => students.filter((student) => (dates[student.codigo_estud] || '') !== (student.fecha_grado || '')),
    [dates, students],
  )
  const studentsWithDate = useMemo(
    () => students.filter((student) => dates[student.codigo_estud] || student.fecha_grado).length,
    [dates, students],
  )
  const selectedPeriod = useMemo(
    () => catalog.periodos?.find((item) => item.codigo_periodo === periodo),
    [catalog.periodos, periodo],
  )
  const selectedCareer = useMemo(
    () => catalog.carreras?.find((item) => item.codigo_carrera === carrera),
    [catalog.carreras, carrera],
  )

  async function loadCatalog(selectedPeriod = periodo) {
    setCatalogLoading(true)
    setError('')
    try {
      const payload = await fetchFechaGradoCatalog(selectedPeriod)
      setCatalog(payload)
      if (!selectedPeriod && payload.periodos?.[0]?.codigo_periodo) {
        setPeriodo(payload.periodos[0].codigo_periodo)
        void loadCatalog(payload.periodos[0].codigo_periodo)
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el catalogo de fecha de grado')
    } finally {
      setCatalogLoading(false)
    }
  }

  async function loadStudents() {
    if (!periodo) {
      setError('Selecciona un periodo para consultar estudiantes.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await fetchFechaGradoStudents({ periodo, carrera, busqueda, limit: 5000 })
      const items = payload.items || []
      setStudents(items)
      setDates(Object.fromEntries(items.map((item) => [item.codigo_estud, item.fecha_grado || ''])))
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar estudiantes')
    } finally {
      setLoading(false)
    }
  }

  async function saveChanges() {
    if (dirtyItems.length === 0) {
      setMessage('No hay fechas pendientes por guardar.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const uniqueDirtyItems = Array.from(
        new Map(dirtyItems.map((student) => [student.codigo_estud, student])).values(),
      )
      const payload = {
        items: uniqueDirtyItems.map((student) => ({
          codigo_estud: student.codigo_estud,
          fecha_grado: dates[student.codigo_estud] || null,
        })),
      }
      const response = await saveFechaGrado(payload)
      setStudents((current) =>
        current.map((student) => ({
          ...student,
          fecha_grado: dates[student.codigo_estud] || '',
        })),
      )
      setMessage(`Fechas guardadas: ${response.actualizados}`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron guardar las fechas')
    } finally {
      setSaving(false)
    }
  }

  async function downloadTemplate() {
    if (!periodo) {
      setError('Selecciona un periodo para descargar la plantilla.')
      return
    }
    setError('')
    setMessage('')
    try {
      const blob = await downloadFechaGradoTemplate({ periodo, carrera, busqueda })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `plantilla-fecha-grado-${periodo}.xlsx`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar la plantilla Excel')
    }
  }

  async function uploadExcel() {
    if (!periodo) {
      setError('Selecciona un periodo antes de importar.')
      return
    }
    if (!excelFile) {
      setError('Selecciona un archivo Excel para importar.')
      return
    }
    setImporting(true)
    setError('')
    setMessage('')
    try {
      const response = await importFechaGradoExcel(excelFile, { periodo, carrera })
      if (!response.ok) {
        const details = response.errores?.slice(0, 5).map((item) => `Fila ${item.fila}: ${item.error}`).join(' | ')
        setError(details || 'El Excel contiene errores de validación.')
        return
      }
      setMessage(`Excel importado. Fechas actualizadas: ${response.actualizados}`)
      setExcelFile(null)
      await loadStudents()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo importar el Excel')
    } finally {
      setImporting(false)
    }
  }

  function applyDateToEmpty() {
    const date = todayIso()
    setDates((current) => {
      const next = { ...current }
      for (const student of students) {
        if (!next[student.codigo_estud]) {
          next[student.codigo_estud] = date
        }
      }
      return next
    })
  }

  useEffect(() => {
    void loadCatalog('')
  }, [])

  useEffect(() => {
    if (periodo) {
      setCarrera('')
      setStudents([])
      setDates({})
      void loadCatalog(periodo)
    }
  }, [periodo])

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Matricula</p>
          <h1>Fecha de grado</h1>
          <span>Ingreso y revisión por periodo académico y carrera</span>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>{students.length} estudiante(s)</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--stats fecha-grado-stats">
        <article className="student-card student-card--stat matricula-stat-card">
          <p>Periodo</p>
          <h2>{valueOrDash(selectedPeriod?.codigo_periodo || periodo)}</h2>
          <small>{valueOrDash(selectedPeriod?.detalle_periodo)}</small>
        </article>
        <article className="student-card student-card--stat matricula-stat-card">
          <p>Carrera</p>
          <h2>{selectedCareer ? selectedCareer.total_estudiantes || students.length : students.length}</h2>
          <small>{selectedCareer?.nombre_carrera || 'Todas las carreras'}</small>
        </article>
        <article className="student-card student-card--stat matricula-stat-card">
          <p>Con fecha</p>
          <h2>{studentsWithDate}</h2>
          <small>{students.length ? `${students.length - studentsWithDate} pendiente(s)` : 'Sin consulta'}</small>
        </article>
        <article className="student-card student-card--stat matricula-stat-card">
          <p>Cambios</p>
          <h2>{dirtyItems.length}</h2>
          <small>{dirtyItems.length ? 'Pendientes de guardar' : 'Sin cambios'}</small>
        </article>
      </section>

      <section className="student-grid student-grid--content fecha-grado-grid">
        <article className="student-card student-card--wide fecha-grado-panel">
          <div className="card-head">
            <h3>Filtros</h3>
            <span>{catalogLoading ? 'Cargando...' : `${catalog.periodos?.length || 0} periodo(s)`}</span>
          </div>

          <div className="fecha-grado-filter-row">
            <div className="matricula-acad-form fecha-grado-form">
              <label className="fecha-grado-field--career">
                <span>Carrera</span>
                <select value={carrera} onChange={(event) => setCarrera(event.target.value)} disabled={!periodo}>
                  <option value="">Todas las carreras</option>
                  {(catalog.carreras || []).map((item) => (
                    <option key={item.codigo_carrera || item.nombre_carrera} value={item.codigo_carrera}>
                      {item.nombre_carrera} ({item.total_estudiantes || 0})
                    </option>
                  ))}
                </select>
              </label>
              <label className="fecha-grado-field--period">
                <span>Periodo</span>
                <select value={periodo} onChange={(event) => setPeriodo(event.target.value)}>
                  <option value="">Selecciona periodo</option>
                  {(catalog.periodos || []).map((item) => (
                    <option key={item.codigo_periodo} value={item.codigo_periodo}>
                      {item.codigo_periodo} - {item.detalle_periodo || item.codigo_periodo}
                    </option>
                  ))}
                </select>
              </label>
              <label className="fecha-grado-field--search">
                <span>Buscar nombre</span>
                <input
                  value={busqueda}
                  onChange={(event) => setBusqueda(event.target.value)}
                  placeholder="Nombre, cédula, código o carrera"
                />
              </label>
            </div>

            <div className="teams-actions fecha-grado-actions">
              <button type="button" onClick={() => void loadStudents()} disabled={loading || !periodo}>
                {loading ? 'Consultando...' : 'Ver lista de estudiantes'}
              </button>
              <button type="button" onClick={() => void downloadTemplate()} disabled={!periodo}>
                Descargar plantilla Excel
              </button>
              <button type="button" onClick={applyDateToEmpty} disabled={students.length === 0}>
                Fecha de hoy en vacíos
              </button>
              <button type="button" onClick={() => void saveChanges()} disabled={saving || dirtyItems.length === 0}>
                {saving ? 'Guardando...' : `Guardar cambios (${dirtyItems.length})`}
              </button>
            </div>
            <div className="fecha-grado-import-row">
              <label>
                <span>Importar por cédula</span>
                <input
                  type="file"
                  accept=".xlsx,.xlsm"
                  onChange={(event) => setExcelFile(event.target.files?.[0] || null)}
                />
              </label>
              <button type="button" className="ghost-button" onClick={() => void uploadExcel()} disabled={importing || !excelFile || !periodo}>
                {importing ? 'Validando...' : 'Cargar Excel'}
              </button>
              <small>Excel validado por cedula y fecha_grado. Formato de fecha: AAAA-MM-DD.</small>
            </div>
          </div>

          {message ? <p className="form-success">{message}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
        </article>

        <article className="student-card student-card--wide fecha-grado-panel">
          <div className="card-head">
            <h3>Estudiantes</h3>
            <span>{loading ? 'Actualizando...' : `${students.length} registro(s)`}</span>
          </div>

          <div className="matricula-table-wrap fecha-grado-table-wrap">
            <table className="matricula-table fecha-grado-table">
              <colgroup>
                <col className="fecha-grado-col-name" />
                <col className="fecha-grado-col-id" />
                <col className="fecha-grado-col-career" />
                <col className="fecha-grado-col-date" />
              </colgroup>
              <thead>
                <tr>
                  <th>Nombres</th>
                  <th>Cédula</th>
                  <th>Carrera</th>
                  <th>Fecha</th>
                </tr>
              </thead>
              <tbody>
                {students.map((student) => (
                  <tr key={`${student.codigo_estud}-${student.codigo_carrera || 'carrera'}`}>
                    <td>
                      <div className="fecha-grado-student-cell">
                        <strong>{valueOrDash(student.nombres)}</strong>
                        <small>Código {valueOrDash(student.codigo_estud)}</small>
                      </div>
                    </td>
                    <td>{valueOrDash(student.cedula)}</td>
                    <td>
                      <div className="fecha-grado-career-cell">
                        <span>{valueOrDash(student.carrera)}</span>
                        <small>Carrera {valueOrDash(student.codigo_carrera)}</small>
                      </div>
                    </td>
                    <td>
                      <input
                        type="date"
                        value={dates[student.codigo_estud] || ''}
                        onChange={(event) =>
                          setDates((current) => ({
                            ...current,
                            [student.codigo_estud]: event.target.value,
                          }))
                        }
                      />
                    </td>
                  </tr>
                ))}
                {students.length === 0 ? (
                  <tr>
                    <td colSpan={4}>Selecciona un periodo y consulta la lista de estudiantes.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </>
  )
}
