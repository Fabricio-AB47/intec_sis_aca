import { useEffect, useMemo, useState } from 'react'

import { fetchCredentialCatalog, fetchCredentialRows, saveCredentialBulk } from '../../lib/api'
import type { CredentialCourse, CredentialRow } from '../../types/app'

type CredentialGeneratorViewProps = {
  displayName: string
}

const emptyRow = (): CredentialRow => ({
  primer_nombre: '',
  segundo_nombre: '',
  primer_apellido: '',
  segundo_apellido: '',
  cedula: '',
  correo_electronico: '',
  correo_enviado: false,
})

function valueOrDash(value: unknown) {
  const text = String(value ?? '').trim()
  return text || '-'
}

function splitLine(line: string) {
  return line
    .split(/\t|;/)
    .map((item) => item.trim())
}

function normalizeText(value: string) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

function manualCourseCode(courseName: string) {
  const slug = normalizeText(courseName)
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 35)
  return `MANUAL:${slug || 'curso'}`
}

function courseSourceLabel(course?: CredentialCourse) {
  if (!course) return 'Manual'
  if (course.source === 'PENSUM') return 'Pensum'
  if (course.source === 'EDUCACION_CONTINUA') return 'Educacion continua'
  return course.source || 'Catalogo'
}

function courseDetail(course: CredentialCourse) {
  return [
    courseSourceLabel(course),
    course.carrera,
    course.semestre ? `Nivel ${course.semestre}` : '',
    course.cod_materia || course.codigo_materia ? `Codigo ${course.cod_materia || course.codigo_materia}` : '',
  ]
    .filter(Boolean)
    .join(' · ')
}

export function CredentialGeneratorView({ displayName }: Readonly<CredentialGeneratorViewProps>) {
  const [courses, setCourses] = useState<CredentialCourse[]>([])
  const [selectedCourseCode, setSelectedCourseCode] = useState('')
  const [courseSearch, setCourseSearch] = useState('')
  const [messageTemplate, setMessageTemplate] = useState('')
  const [link, setLink] = useState('')
  const [graphDomain, setGraphDomain] = useState('')
  const [graphSender, setGraphSender] = useState('')
  const [rows, setRows] = useState<CredentialRow[]>([emptyRow()])
  const [savedRows, setSavedRows] = useState<CredentialRow[]>([])
  const [pasteText, setPasteText] = useState('')
  const [sendEmail, setSendEmail] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const selectedCourse = useMemo(
    () => courses.find((course) => course.cod_curso === selectedCourseCode),
    [courses, selectedCourseCode],
  )

  const effectiveCourse = useMemo(() => {
    if (selectedCourse) {
      return selectedCourse
    }
    const manualName = courseSearch.trim()
    if (!manualName) {
      return null
    }
    return {
      cod_curso: manualCourseCode(manualName),
      curso: manualName,
      source: 'MANUAL',
    } satisfies CredentialCourse
  }, [courseSearch, selectedCourse])

  const filteredCourses = useMemo(() => {
    const query = normalizeText(courseSearch.trim())
    if (!query) {
      return courses.slice(0, 12)
    }
    return courses
      .filter((course) =>
        normalizeText(
          [
            course.curso,
            course.cod_materia,
            course.codigo_materia,
            course.carrera,
            course.semestre,
            course.source,
          ]
            .filter(Boolean)
            .join(' '),
        ).includes(query),
      )
      .slice(0, 12)
  }, [courseSearch, courses])

  const validRows = useMemo(
    () =>
      rows.filter(
        (row) =>
          row.primer_nombre.trim() &&
          row.primer_apellido.trim() &&
          row.cedula.trim() &&
          row.correo_electronico.trim(),
      ),
    [rows],
  )

  async function loadCatalog() {
    setLoading(true)
    setError('')
    try {
      const payload = await fetchCredentialCatalog()
      setCourses(payload.courses || [])
      setMessageTemplate(payload.default_message || '')
      setLink(payload.default_link || '')
      setGraphDomain(payload.graph_user_domain || '')
      setGraphSender(payload.graph_mail_sender || '')
      setSelectedCourseCode('')
      setCourseSearch('')
      setSavedRows([])
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el modulo de credenciales')
    } finally {
      setLoading(false)
    }
  }

  async function loadSaved(nextCourseCode = selectedCourseCode) {
    if (!nextCourseCode) {
      setSavedRows([])
      return
    }
    setError('')
    try {
      const payload = await fetchCredentialRows(nextCourseCode)
      setSavedRows(payload.rows || [])
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar credenciales guardadas')
    }
  }

  useEffect(() => {
    void loadCatalog()
  }, [])

  function updateRow(index: number, field: keyof CredentialRow, value: string | boolean) {
    setRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)),
    )
  }

  function removeRow(index: number) {
    setRows((current) => (current.length === 1 ? [emptyRow()] : current.filter((_, rowIndex) => rowIndex !== index)))
  }

  function addRow() {
    setRows((current) => [...current, emptyRow()])
  }

  function updateCourseSearch(value: string) {
    setCourseSearch(value)
    setSelectedCourseCode('')
    setSavedRows([])
  }

  function selectCourse(course: CredentialCourse) {
    setSelectedCourseCode(course.cod_curso)
    setCourseSearch(course.curso)
    void loadSaved(course.cod_curso)
  }

  function importPasteRows() {
    const nextRows = pasteText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [primer_nombre, segundo_nombre, primer_apellido, segundo_apellido, cedula, correo_electronico] = splitLine(line)
        return {
          primer_nombre: primer_nombre || '',
          segundo_nombre: segundo_nombre || '',
          primer_apellido: primer_apellido || '',
          segundo_apellido: segundo_apellido || '',
          cedula: cedula || '',
          correo_electronico: correo_electronico || '',
          correo_enviado: false,
        }
      })

    if (!nextRows.length) {
      setError('Pega al menos una fila para importar.')
      return
    }
    setRows((current) => [...current.filter((row) => row.primer_nombre || row.cedula || row.correo_electronico), ...nextRows])
    setPasteText('')
    setError('')
    setMessage(`${nextRows.length} fila(s) agregada(s) a la lista.`)
  }

  async function saveRows() {
    setError('')
    setMessage('')
    if (!effectiveCourse) {
      setError('Busca una materia del pensum o escribe el nombre del curso que necesita el grupo.')
      return
    }
    if (!messageTemplate.trim()) {
      setError('Ingresa el mensaje que se enviara con las credenciales.')
      return
    }
    if (!link.trim()) {
      setError('Ingresa el enlace de induccion que debe incluirse en el mensaje.')
      return
    }
    if (!validRows.length) {
      setError('Agrega al menos un usuario con nombre, apellido, cedula y correo.')
      return
    }

    const invalidEmail = validRows.find((row) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(row.correo_electronico.trim()))
    if (invalidEmail) {
      setError(`Correo no valido para la cedula ${invalidEmail.cedula || '-'}.`)
      return
    }

    setSaving(true)
    try {
      const payload = await saveCredentialBulk({
        cod_curso: effectiveCourse.cod_curso,
        curso: effectiveCourse.curso,
        mensaje: messageTemplate,
        link,
        enviar_correo: sendEmail,
        usuarios: validRows,
      })
      const graphSummary = [
        payload.graph_created ? `${payload.graph_created} usuario(s) creados en Graph` : '',
        payload.graph_updated ? `${payload.graph_updated} usuario(s) actualizados en Graph` : '',
        payload.graph_failed ? `${payload.graph_failed} error(es) Graph` : '',
      ]
        .filter(Boolean)
        .join(' · ')
      setMessage(`${payload.message || 'Credenciales guardadas.'}${graphSummary ? ` ${graphSummary}.` : ''}`)
      setRows([emptyRow()])
      await loadSaved(effectiveCourse.cod_curso)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar credenciales')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Integraciones</p>
          <h1>Credenciales Office 365</h1>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Acceso administrador</span>
            </div>
          </div>
        </div>
      </header>

      <section className="credential-overview">
        <article>
          <span>Curso activo</span>
          <strong>{effectiveCourse ? effectiveCourse.curso : '-'}</strong>
          <small>{effectiveCourse ? courseSourceLabel(effectiveCourse) : 'Pendiente de seleccion'}</small>
        </article>
        <article>
          <span>Usuarios listos</span>
          <strong>{validRows.length}</strong>
          <small>Con nombre, cedula y correo</small>
        </article>
        <article>
          <span>Microsoft Graph</span>
          <strong>{graphDomain ? `@${graphDomain}` : '-'}</strong>
          <small>{graphSender || 'Remitente pendiente'}</small>
        </article>
      </section>

      <section className="credential-grid">
        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Curso y mensaje</h3>
            <span>{loading ? 'Cargando...' : `${courses.length} curso(s)`}</span>
          </div>

          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-success">{message}</p> : null}

          <div className="credential-setup-grid">
            <div className="credential-course-picker">
              <div className="credential-course-picker__head">
                <div>
                  <span>Curso que va a seguir</span>
                  <strong>{effectiveCourse ? effectiveCourse.curso : 'Seleccione o escriba un curso'}</strong>
                </div>
                <button
                  type="button"
                  className="ghost-button"
                  disabled={!effectiveCourse}
                  onClick={() => void loadSaved(effectiveCourse?.cod_curso || '')}
                >
                  Ver guardadas
                </button>
              </div>
              <label>
                <span>Buscar en pensum o escribir curso</span>
                <input
                  value={courseSearch}
                  onChange={(event) => updateCourseSearch(event.target.value)}
                  placeholder="Ej. Base de datos, seguridad, gastronomia..."
                />
              </label>
              <div className="credential-course-results">
                {filteredCourses.length > 0 ? (
                  filteredCourses.map((course) => (
                    <button
                      key={course.cod_curso}
                      type="button"
                      className={`credential-course-option${selectedCourseCode === course.cod_curso ? ' credential-course-option--active' : ''}`}
                      onClick={() => selectCourse(course)}
                    >
                      <span>{courseSourceLabel(course)}</span>
                      <strong>{course.curso}</strong>
                      <small>{courseDetail(course)}</small>
                    </button>
                  ))
                ) : (
                  <p className="credential-course-empty">No hay coincidencias en pensum. Se guardara como curso escrito manualmente.</p>
                )}
              </div>
              {effectiveCourse ? (
                <div className="credential-course-selected">
                  <span>{courseSourceLabel(effectiveCourse)}</span>
                  <strong>{effectiveCourse.curso}</strong>
                  <small>{selectedCourse ? courseDetail(selectedCourse) : effectiveCourse.cod_curso}</small>
                </div>
              ) : null}
            </div>

            <div className="matricula-acad-form credential-form">
            <label>
              <span>Link obligatorio en el mensaje</span>
              <input value={link} onChange={(event) => setLink(event.target.value)} />
            </label>
            <label className="credential-field--wide">
              <span>Mensaje editable</span>
              <textarea
                value={messageTemplate}
                rows={8}
                onChange={(event) => setMessageTemplate(event.target.value)}
              />
            </label>
            </div>
          </div>

          <div className="credential-help">
            <strong>Variables disponibles:</strong>
            <span>{'{primer_nombre}'}</span>
            <span>{'{segundo_nombre}'}</span>
            <span>{'{primer_apellido}'}</span>
            <span>{'{segundo_apellido}'}</span>
            <span>{'{cedula}'}</span>
            <span>{'{correo}'}</span>
            <span>{'{curso}'}</span>
            <span>{'{usuario}'}</span>
            <span>{'{clave}'}</span>
            <span>{'{link}'}</span>
          </div>

          <div className="credential-graph-panel">
            <div>
              <span>Consumo Microsoft Graph</span>
              <strong>{graphDomain ? `Usuarios @${graphDomain}` : 'Dominio no configurado'}</strong>
            </div>
            <div>
              <span>Cuenta remitente</span>
              <strong>{graphSender || 'GRAPH_MAIL_SENDER pendiente'}</strong>
            </div>
            <p>
              Al guardar se crea o actualiza cada usuario en Microsoft 365 con contraseña temporal. Si activas el envio,
              el correo sale por Microsoft Graph desde la cuenta remitente configurada.
            </p>
          </div>
        </article>

        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Lista de usuarios</h3>
            <span>{validRows.length} usuario(s) listos</span>
          </div>

          <div className="credential-paste">
            <label>
              <span>Pegar lista rapida</span>
              <textarea
                value={pasteText}
                rows={4}
                onChange={(event) => setPasteText(event.target.value)}
                placeholder="Primer nombre;Segundo nombre;Primer apellido;Segundo apellido;Cedula;Correo electronico"
              />
            </label>
            <button type="button" className="ghost-button" onClick={importPasteRows}>
              Agregar lista pegada
            </button>
          </div>

          <div className="portal-table-wrap credential-table-wrap">
            <table className="portal-record-table credential-table">
              <thead>
                <tr>
                  <th>Primer nombre</th>
                  <th>Segundo nombre</th>
                  <th>Primer apellido</th>
                  <th>Segundo apellido</th>
                  <th>Cedula</th>
                  <th>Correo electronico</th>
                  <th>Correo enviado</th>
                  <th>Accion</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`credential-row-${index}`}>
                    <td>
                      <input value={row.primer_nombre} onChange={(event) => updateRow(index, 'primer_nombre', event.target.value)} />
                    </td>
                    <td>
                      <input value={row.segundo_nombre || ''} onChange={(event) => updateRow(index, 'segundo_nombre', event.target.value)} />
                    </td>
                    <td>
                      <input value={row.primer_apellido} onChange={(event) => updateRow(index, 'primer_apellido', event.target.value)} />
                    </td>
                    <td>
                      <input value={row.segundo_apellido || ''} onChange={(event) => updateRow(index, 'segundo_apellido', event.target.value)} />
                    </td>
                    <td>
                      <input value={row.cedula} onChange={(event) => updateRow(index, 'cedula', event.target.value)} />
                    </td>
                    <td>
                      <input value={row.correo_electronico} onChange={(event) => updateRow(index, 'correo_electronico', event.target.value)} />
                    </td>
                    <td>
                      <label className="credential-check">
                        <input
                          type="checkbox"
                          checked={Boolean(row.correo_enviado)}
                          onChange={(event) => updateRow(index, 'correo_enviado', event.target.checked)}
                        />
                        <span>Si</span>
                      </label>
                    </td>
                    <td>
                      <button type="button" className="ghost-button" onClick={() => removeRow(index)}>
                        Quitar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="credential-actions">
            <button type="button" className="ghost-button" onClick={addRow}>
              Agregar usuario
            </button>
            <label className="credential-send-toggle">
              <input type="checkbox" checked={sendEmail} onChange={(event) => setSendEmail(event.target.checked)} />
              <span>Enviar correo por Microsoft Graph al guardar</span>
            </label>
            <button type="button" className="primary-action" onClick={() => void saveRows()} disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar credenciales'}
            </button>
          </div>
        </article>

        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Credenciales guardadas</h3>
            <span>{savedRows.length} registro(s)</span>
          </div>

          <div className="portal-table-wrap credential-table-wrap">
            <table className="portal-record-table">
              <thead>
                <tr>
                  <th>Estudiante</th>
                  <th>Cedula</th>
                  <th>Correo</th>
                  <th>Usuario Microsoft</th>
                  <th>Clave</th>
                  <th>Graph</th>
                  <th>Correo enviado</th>
                  <th>Estado correo</th>
                </tr>
              </thead>
              <tbody>
                {savedRows.length > 0 ? (
                  savedRows.map((row) => (
                    <tr key={row.id || `${row.cedula}-${row.cod_curso}`}>
                      <td>
                        <strong>
                          {valueOrDash(`${row.primer_nombre || ''} ${row.segundo_nombre || ''} ${row.primer_apellido || ''} ${row.segundo_apellido || ''}`)}
                        </strong>
                      </td>
                      <td>{valueOrDash(row.cedula)}</td>
                      <td>{valueOrDash(row.correo_electronico)}</td>
                      <td>{valueOrDash(row.graph_user_principal_name || row.usuario_generado)}</td>
                      <td>{valueOrDash(row.clave_temporal)}</td>
                      <td>
                        <span className={`credential-status credential-status--${String(row.estado_graph || 'pendiente_graph').toLowerCase()}`}>
                          {valueOrDash(row.estado_graph)}
                        </span>
                        {row.error_graph ? <small>{row.error_graph}</small> : null}
                      </td>
                      <td>{row.correo_enviado ? 'Si' : 'No'}</td>
                      <td>
                        <span className={`credential-status credential-status--${String(row.estado_envio || 'pendiente').toLowerCase()}`}>
                          {valueOrDash(row.estado_envio)}
                        </span>
                        {row.error_envio ? <small>{row.error_envio}</small> : null}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8}>No hay credenciales guardadas para el curso seleccionado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </>
  )
}
