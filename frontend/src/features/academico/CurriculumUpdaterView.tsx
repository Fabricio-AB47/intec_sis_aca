import { useMemo, useState, type ChangeEvent } from 'react'

import { analyzeCurriculumWorkbook, generateCurriculumWorkbook } from '../../lib/api'
import type {
  CurriculumAnalysisResponse,
  CurriculumAnalysisRow,
  CurriculumGenerateUpdate,
  CurriculumPeaDocument,
  CurriculumProposal,
} from '../../types/app'
import './CurriculumUpdaterView.css'


type CurriculumUpdaterViewProps = {
  displayName: string
}

type EditableCurriculumRow = CurriculumAnalysisRow & {
  selected: boolean
}

const STATUS_LABELS: Record<string, string> = {
  LISTO: 'Listo para aplicar',
  REQUIERE_REVISION: 'Requiere revisión',
  DATOS_EXISTENTES: 'Información existente',
  SIN_PEA: 'Sin PEA o sílabo relacionado',
  REVISION_MANUAL: 'Asignación manual',
}

function fileSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(2)} MB`
  return `${Math.max(1, Math.round(size / 1024))} KB`
}

function normalizedFilename(value: string): string {
  return value.trim().toLocaleLowerCase('es-EC')
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status.replaceAll('_', ' ').toLocaleLowerCase('es-EC')
}

function statusClass(status: string): string {
  return `curriculum-status curriculum-status--${status.toLocaleLowerCase('es-EC').replaceAll('_', '-')}`
}

function methodLabel(document?: CurriculumPeaDocument): string {
  if (!document) return 'Documento PDF'
  const documentType = document.document_type === 'SILABO' ? 'Sílabo' : 'PEA'
  if (document.method === 'TEXTO+OCR') return `${documentType} · Texto + OCR`
  if (document.method === 'TEXTO') return `${documentType} · Texto PDF`
  return `${documentType} · ${document.method}`
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function generatedFilename(file: File): string {
  const stem = file.name.replace(/\.xlsx$/i, '')
  return `${stem}-actualizada.xlsx`
}

function proposalFromDocument(
  document: CurriculumPeaDocument,
  current: CurriculumProposal,
): CurriculumProposal {
  return {
    field: document.field || current.field,
    learning_outcomes: document.learning_outcomes || current.learning_outcomes,
    minimum_contents: document.minimum_contents || current.minimum_contents,
  }
}

export function CurriculumUpdaterView({ displayName }: Readonly<CurriculumUpdaterViewProps>) {
  const [workbookFile, setWorkbookFile] = useState<File | null>(null)
  const [academicFiles, setAcademicFiles] = useState<File[]>([])
  const [careerName, setCareerName] = useState('')
  const [analysis, setAnalysis] = useState<CurriculumAnalysisResponse | null>(null)
  const [rows, setRows] = useState<EditableCurriculumRow[]>([])
  const [filter, setFilter] = useState('')
  const [editingRowNumber, setEditingRowNumber] = useState<number | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const editingRow = rows.find((row) => row.row_number === editingRowNumber) || null
  const visibleRows = useMemo(() => {
    const query = filter.trim().toLocaleLowerCase('es-EC')
    if (!query) return rows
    return rows.filter((row) => [
      row.subject_name,
      row.period,
      row.curricular_unit,
      row.source_file,
      statusLabel(row.status),
    ].join(' ').toLocaleLowerCase('es-EC').includes(query))
  }, [filter, rows])
  const selectedCount = rows.filter((row) => row.selected).length
  const allVisibleSelected = visibleRows.length > 0 && visibleRows.every((row) => row.selected)

  function resetResult() {
    setAnalysis(null)
    setRows([])
    setEditingRowNumber(null)
    setFilter('')
    setError('')
    setMessage('')
  }

  function selectWorkbook(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null
    setWorkbookFile(file)
    resetResult()
  }

  function selectAcademicFiles(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files || [])
    setAcademicFiles((current) => {
      const known = new Set(current.map((file) => `${normalizedFilename(file.name)}:${file.size}`))
      return [
        ...current,
        ...incoming.filter((file) => !known.has(`${normalizedFilename(file.name)}:${file.size}`)),
      ]
    })
    resetResult()
    event.currentTarget.value = ''
  }

  function removeAcademicFile(index: number) {
    setAcademicFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))
    resetResult()
  }

  async function analyze() {
    setError('')
    setMessage('')
    if (!workbookFile) {
      setError('Seleccione el archivo Excel de la malla.')
      return
    }

    setAnalyzing(true)
    try {
      const result = await analyzeCurriculumWorkbook(workbookFile, academicFiles, careerName)
      setAnalysis(result)
      setRows(result.rows.map((row) => ({ ...row, selected: row.apply_recommended })))
      if (!careerName.trim()) setCareerName(result.workbook.career_name)
      setMessage(
        academicFiles.length
          ? `${result.summary.documents} documento(s) PEA/sílabo analizado(s) para ${result.workbook.career_name}.`
          : `Estructura de ${result.workbook.career_name} analizada sin documentos académicos.`,
      )
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'No se pudo analizar la malla.')
      setAnalysis(null)
      setRows([])
    } finally {
      setAnalyzing(false)
    }
  }

  function updateRow(rowNumber: number, updater: (row: EditableCurriculumRow) => EditableCurriculumRow) {
    setRows((current) => current.map((row) => row.row_number === rowNumber ? updater(row) : row))
  }

  function assignDocument(rowNumber: number, documentIndex: number | null) {
    updateRow(rowNumber, (row) => {
      if (documentIndex === null) {
        return {
          ...row,
          document_index: null,
          document_indices: [],
          source_file: '',
          source_files: [],
          match_score: 0,
          match_type: 'SIN_PEA',
          status: Object.values(row.current).some(Boolean) ? 'DATOS_EXISTENTES' : 'SIN_PEA',
          selected: false,
          proposal: { ...row.current },
          warnings: [],
        }
      }
      const document = analysis?.documents.find((item) => item.index === documentIndex)
      if (!document) return row
      return {
        ...row,
        document_index: document.index,
        document_indices: [document.index],
        source_file: document.filename,
        source_files: [document.filename],
        match_score: 100,
        match_type: 'ASIGNACION_MANUAL',
        status: 'REVISION_MANUAL',
        selected: Boolean(document.learning_outcomes || document.minimum_contents),
        proposal: proposalFromDocument(document, row.current),
        warnings: document.warnings,
      }
    })
  }

  function updateProposal(rowNumber: number, field: keyof CurriculumProposal, value: string) {
    updateRow(rowNumber, (row) => ({
      ...row,
      proposal: { ...row.proposal, [field]: value },
    }))
  }

  function toggleVisibleRows() {
    const visibleNumbers = new Set(visibleRows.map((row) => row.row_number))
    setRows((current) => current.map((row) => (
      visibleNumbers.has(row.row_number) ? { ...row, selected: !allVisibleSelected } : row
    )))
  }

  async function generate() {
    setError('')
    setMessage('')
    if (!workbookFile || !analysis) {
      setError('Analice primero la malla que desea actualizar.')
      return
    }

    const updates: CurriculumGenerateUpdate[] = rows.map((row) => ({
      row_number: row.row_number,
      subject_name: row.subject_name,
      period: row.period,
      apply: row.selected,
      status: row.status,
      source_file: row.source_file,
      proposal: row.proposal,
    }))
    setGenerating(true)
    try {
      const blob = await generateCurriculumWorkbook(workbookFile, careerName || analysis.workbook.career_name, updates)
      downloadBlob(blob, generatedFilename(workbookFile))
      setMessage(
        `${analysis.workbook.target_sheet}: Excel generado con ${selectedCount} asignatura(s) seleccionada(s).`,
      )
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'No se pudo generar el Excel actualizado.')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="curriculum-updater-page">
      <header className="student-topbar curriculum-updater-hero">
        <div>
          <p className="eyebrow">OCR académico</p>
          <h1>Actualizar malla por carrera</h1>
          <p className="report-description">Resultados de aprendizaje y contenidos mínimos desde PEA y sílabos.</p>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Gestión académica</span>
            </div>
          </div>
        </div>
      </header>

      <nav className="curriculum-steps" aria-label="Etapas de actualización">
        <span className="curriculum-step curriculum-step--active"><b>1</b> Archivos</span>
        <span className={`curriculum-step${analysis ? ' curriculum-step--active' : ''}`}><b>2</b> Análisis</span>
        <span className={`curriculum-step${analysis ? ' curriculum-step--active' : ''}`}><b>3</b> Revisión</span>
        <span className={`curriculum-step${message.includes('Excel generado') ? ' curriculum-step--active' : ''}`}><b>4</b> Descarga</span>
      </nav>

      <section className="curriculum-upload-panel" aria-labelledby="curriculum-upload-title">
        <div className="curriculum-section-head">
          <div>
            <p className="eyebrow">Entrada</p>
            <h2 id="curriculum-upload-title">Malla, PEA y sílabos</h2>
          </div>
          <button type="button" className="primary-action" onClick={() => void analyze()} disabled={analyzing || !workbookFile}>
            {analyzing ? 'Analizando documentos...' : 'Analizar malla y documentos'}
          </button>
        </div>

        <div className="curriculum-upload-grid">
          <label className="curriculum-field">
            <span className="curriculum-field-label">Carrera</span>
            <input
              value={careerName}
              maxLength={180}
              placeholder="Se detectará desde el Excel"
              onChange={(event) => {
                setCareerName(event.target.value)
                resetResult()
              }}
            />
            <small>{careerName.trim() ? 'Carrera definida' : 'Detección automática'}</small>
          </label>
          <label className="curriculum-field curriculum-file-field">
            <span className="curriculum-field-label">Archivo de malla (.xlsx)</span>
            <span className="curriculum-file-picker">
              <span className="curriculum-file-picker__action">Seleccionar Excel</span>
              <span className="curriculum-file-picker__value" title={workbookFile?.name || undefined}>
                {workbookFile?.name || 'Ningún archivo seleccionado'}
              </span>
              <input
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={selectWorkbook}
              />
            </span>
            <small>{workbookFile ? fileSize(workbookFile.size) : 'Archivo pendiente'}</small>
          </label>
          <label className="curriculum-field curriculum-file-field">
            <span className="curriculum-field-label">Documentos PEA o sílabo (.pdf)</span>
            <span className="curriculum-file-picker">
              <span className="curriculum-file-picker__action">Seleccionar PDF</span>
              <span className="curriculum-file-picker__value">
                {academicFiles.length
                  ? `${academicFiles.length} archivo(s) seleccionado(s)`
                  : 'Ningún archivo seleccionado'}
              </span>
              <input type="file" accept="application/pdf,.pdf" multiple onChange={selectAcademicFiles} />
            </span>
            <small>{academicFiles.length ? `${academicFiles.length} documento(s)` : 'Sin documentos académicos'}</small>
          </label>
        </div>

        {academicFiles.length ? (
          <div className="curriculum-file-list" aria-label="PEA y sílabos seleccionados">
            {academicFiles.map((file, index) => (
              <div key={`${file.name}-${file.size}-${file.lastModified}`}>
                <span><strong>{file.name}</strong><small>{fileSize(file.size)}</small></span>
                <button
                  type="button"
                  onClick={() => removeAcademicFile(index)}
                  aria-label={`Quitar ${file.name}`}
                  title="Quitar archivo"
                >×</button>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      {error ? <div className="curriculum-alert curriculum-alert--error" role="alert">{error}</div> : null}
      {message ? <div className="curriculum-alert curriculum-alert--success" role="status">{message}</div> : null}

      {analysis ? (
        <>
          <section className="curriculum-structure-band">
            <div>
              <span>Hoja base</span>
              <strong>{analysis.workbook.source_sheet}</strong>
            </div>
            <div>
              <span>Estructura enriquecida</span>
              <strong>{analysis.workbook.target_sheet}</strong>
            </div>
            <div>
              <span>Acción</span>
              <strong>{analysis.workbook.target_exists ? 'Actualizar existente' : 'Crear para la carrera'}</strong>
            </div>
            <div>
              <span>OCR del servidor</span>
              <strong>{analysis.ocr_available ? 'Disponible' : 'Solo texto PDF'}</strong>
            </div>
          </section>

          {analysis.workbook.warnings.length ? (
            <section className="curriculum-warning-list" aria-label="Validaciones de estructura">
              {analysis.workbook.warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </section>
          ) : null}

          <section className="curriculum-summary" aria-label="Resumen del análisis">
            <div><span>Asignaturas</span><strong>{analysis.summary.subjects}</strong></div>
            <div><span>PEA y sílabos</span><strong>{analysis.summary.documents}</strong></div>
            <div><span>Listos</span><strong>{analysis.summary.ready}</strong></div>
            <div><span>Por revisar</span><strong>{analysis.summary.requires_review}</strong></div>
            <div><span>Sin documento</span><strong>{analysis.summary.without_pea}</strong></div>
            <div><span>Seleccionados</span><strong>{selectedCount}</strong></div>
          </section>

          <section className="curriculum-results" aria-labelledby="curriculum-results-title">
            <div className="curriculum-section-head curriculum-results-head">
              <div>
                <p className="eyebrow">Vista previa</p>
                <h2 id="curriculum-results-title">Información por asignatura</h2>
              </div>
              <div className="curriculum-result-actions">
                <input
                  type="search"
                  value={filter}
                  placeholder="Buscar asignatura, PEA o sílabo"
                  aria-label="Buscar en los resultados"
                  onChange={(event) => setFilter(event.target.value)}
                />
                <button type="button" className="secondary-action" onClick={toggleVisibleRows} disabled={!visibleRows.length}>
                  {allVisibleSelected ? 'Desmarcar visibles' : 'Marcar visibles'}
                </button>
                <button type="button" className="primary-action" onClick={() => void generate()} disabled={generating}>
                  {generating ? 'Generando Excel...' : 'Generar Excel actualizado'}
                </button>
              </div>
            </div>

            <div className="curriculum-table-wrap">
              <table className="curriculum-table">
                <thead>
                  <tr>
                    <th className="curriculum-check-column"><span className="sr-only">Aplicar</span></th>
                    <th>Asignatura</th>
                    <th>Período</th>
                    <th>Fuentes académicas</th>
                    <th>Coincidencia</th>
                    <th>Información</th>
                    <th>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <tr key={`${row.row_number}-${row.subject_name}`}>
                      <td className="curriculum-check-column">
                        <input
                          type="checkbox"
                          checked={row.selected}
                          aria-label={`Aplicar información a ${row.subject_name}`}
                          onChange={(event) => updateRow(row.row_number, (current) => ({ ...current, selected: event.target.checked }))}
                        />
                      </td>
                      <td data-label="Asignatura"><strong>{row.subject_name}</strong><small>{row.curricular_unit}</small></td>
                      <td data-label="Período">{row.period}</td>
                      <td className="curriculum-source-cell" data-label="Fuentes académicas">
                        {(row.source_files.length ? row.source_files : ['Sin documento asignado']).map((filename) => (
                          <span key={filename}>{filename}</span>
                        ))}
                        {row.document_index !== null ? (
                          <small>{analysis.documents
                            .filter((item) => row.document_indices.includes(item.index))
                            .map(methodLabel)
                            .join(' + ') || methodLabel(analysis.documents.find((item) => item.index === row.document_index))}</small>
                        ) : null}
                      </td>
                      <td data-label="Coincidencia">
                        <span className={statusClass(row.status)}>{statusLabel(row.status)}</span>
                        {row.match_score ? <small>{row.match_score.toFixed(1)}%</small> : null}
                      </td>
                      <td data-label="Información">
                        <strong>{row.proposal.field || 'Campo pendiente'}</strong>
                        <small>{row.proposal.minimum_contents.split('\n').filter(Boolean).length} unidad(es)</small>
                      </td>
                      <td data-label="Acción">
                        <button
                          type="button"
                          className="secondary-action"
                          onClick={() => setEditingRowNumber(row.row_number)}
                        >Revisar</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {!visibleRows.length ? <p className="curriculum-empty">No hay asignaturas para el filtro actual.</p> : null}
          </section>

          {analysis.unmatched_documents.length ? (
            <section className="curriculum-unmatched">
              <div>
                <p className="eyebrow">Omitidos</p>
                <h2>Documentos sin una asignatura coincidente</h2>
              </div>
              <div>
                {analysis.unmatched_documents.map((document) => (
                  <span key={`${document.index}-${document.filename}`}>{document.filename}</span>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}

      {editingRow ? (
        <div className="curriculum-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setEditingRowNumber(null)
        }}>
          <section className="curriculum-modal" role="dialog" aria-modal="true" aria-labelledby="curriculum-modal-title">
            <header>
              <div>
                <p className="eyebrow">Asignatura · período {editingRow.period}</p>
                <h2 id="curriculum-modal-title">{editingRow.subject_name}</h2>
              </div>
              <button
                type="button"
                className="curriculum-modal-close"
                onClick={() => setEditingRowNumber(null)}
                aria-label="Cerrar"
                title="Cerrar"
              >×</button>
            </header>

            <div className="curriculum-modal-toolbar">
              <label>
                <span>Fuente principal o asignación manual</span>
                <select
                  value={editingRow.document_index ?? ''}
                  onChange={(event) => assignDocument(
                    editingRow.row_number,
                    event.target.value === '' ? null : Number(event.target.value),
                  )}
                >
                  <option value="">Sin documento asignado</option>
                  {(analysis?.documents || []).map((document) => (
                    <option key={document.index} value={document.index}>
                      {document.document_type === 'SILABO' ? 'Sílabo' : 'PEA'} · {document.filename} ·{' '}
                      {document.subject_name || 'sin asignatura'}
                    </option>
                  ))}
                </select>
              </label>
              <label className="curriculum-apply-toggle">
                <input
                  type="checkbox"
                  checked={editingRow.selected}
                  onChange={(event) => updateRow(editingRow.row_number, (row) => ({ ...row, selected: event.target.checked }))}
                />
                <span>Aplicar al Excel</span>
              </label>
            </div>

            {editingRow.warnings.length ? (
              <div className="curriculum-modal-warnings">
                {editingRow.warnings.map((warning) => <p key={warning}>{warning}</p>)}
              </div>
            ) : null}

            <div className="curriculum-editor-grid">
              <div className="curriculum-current-values">
                <h3>Información actual</h3>
                <label><span>Campo de formación</span><p>{editingRow.current.field || 'Sin información'}</p></label>
                <label><span>Resultados de aprendizaje</span><p>{editingRow.current.learning_outcomes || 'Sin información'}</p></label>
                <label><span>Contenidos mínimos</span><p>{editingRow.current.minimum_contents || 'Sin información'}</p></label>
              </div>
              <div className="curriculum-proposal-values">
                <h3>Información que se generará</h3>
                <label>
                  <span>Campo de formación</span>
                  <textarea
                    rows={2}
                    value={editingRow.proposal.field}
                    onChange={(event) => updateProposal(editingRow.row_number, 'field', event.target.value)}
                  />
                </label>
                <label>
                  <span>Resultados de aprendizaje</span>
                  <textarea
                    rows={8}
                    value={editingRow.proposal.learning_outcomes}
                    onChange={(event) => updateProposal(editingRow.row_number, 'learning_outcomes', event.target.value)}
                  />
                </label>
                <label>
                  <span>Unidades y contenidos mínimos</span>
                  <textarea
                    rows={7}
                    value={editingRow.proposal.minimum_contents}
                    onChange={(event) => updateProposal(editingRow.row_number, 'minimum_contents', event.target.value)}
                  />
                </label>
              </div>
            </div>

            <footer>
              <span>{editingRow.source_file || 'Sin PEA o sílabo asignado'}</span>
              <button type="button" className="primary-action" onClick={() => setEditingRowNumber(null)}>Cerrar revisión</button>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  )
}
