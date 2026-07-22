import { useEffect, useMemo, useState } from 'react'

import { ApiError, fetchPortalTeacherContracts } from '../../lib/api'
import type { PortalTeacherContract, PortalTeacherContractsResponse } from '../../types/app'

type Props = { displayName: string }

const money = new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' })

function formatMoney(value?: number | null) {
  return value == null ? 'No registrado' : money.format(value)
}

function formatDate(value?: string) {
  if (!value) return 'No registrada'
  const date = new Date(`${value.slice(0, 10)}T00:00:00`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('es-EC')
}

function textOrPending(value?: string) {
  return value?.trim() || 'No registrado'
}

export function PortalDocenteContratosView({ displayName }: Readonly<Props>) {
  const [data, setData] = useState<PortalTeacherContractsResponse | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetchPortalTeacherContracts()
      setData(response)
      setSelectedId((current) => response.contracts.some((item) => item.contrato_id === current)
        ? current
        : response.contracts[0]?.contrato_id ?? null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo cargar la información contractual')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const selected = useMemo<PortalTeacherContract | null>(() => (
    data?.contracts.find((item) => item.contrato_id === selectedId) || null
  ), [data, selectedId])

  const totals = useMemo(() => {
    const classes = selected?.clases || []
    return {
      planned: classes.reduce((sum, item) => sum + Number(item.horas_planificadas || 0), 0),
      executed: classes.reduce((sum, item) => sum + Number(item.horas_ejecutadas || 0), 0),
      value: classes.reduce((sum, item) => sum + Number(item.valor_total_planificado || 0), 0),
    }
  }, [selected])

  return (
    <div className="student-dashboard portal-page teacher-contract-page">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Portal docente</p>
          <h1>Contrato docente</h1>
          <p>{data?.teacher?.nombre || displayName}</p>
        </div>
        <button type="button" className="ghost-button" onClick={() => void load()} disabled={loading}>
          {loading ? 'Actualizando...' : 'Actualizar'}
        </button>
      </header>

      {error ? <p className="contract-notice contract-notice--error">{error}</p> : null}
      {!loading && !error && data?.contracts.length === 0 ? (
        <section className="contract-empty">
          <span>Sin contrato registrado</span>
          <h2>No existe información contractual disponible</h2>
          <p>{data.detail || 'La información aparecerá cuando el contrato sea registrado y sincronizado por administración.'}</p>
        </section>
      ) : null}

      {selected ? (
        <>
          <section className="contract-toolbar">
            <label>
              <span>Contrato a consultar</span>
              <select value={selected.contrato_id} onChange={(event) => setSelectedId(Number(event.target.value))}>
                {data?.contracts.map((contract) => (
                  <option key={contract.contrato_id} value={contract.contrato_id}>
                    {textOrPending(contract.numero_contrato)} · {textOrPending(contract.tipo_nombre)} · {textOrPending(contract.codigo_periodo)}
                  </option>
                ))}
              </select>
            </label>
            <div className="contract-status" data-status={selected.estado_codigo?.toLowerCase() || 'pendiente'}>
              <span>Estado contractual</span>
              <strong>{textOrPending(selected.estado_nombre)}</strong>
            </div>
          </section>

          <section className="contract-summary" aria-label="Resumen del contrato">
            <div><span>Materias</span><strong>{selected.clases.length}</strong></div>
            <div><span>Horas planificadas</span><strong>{totals.planned}</strong></div>
            <div><span>Horas ejecutadas</span><strong>{totals.executed}</strong></div>
            <div><span>Total de carga</span><strong>{formatMoney(totals.value)}</strong></div>
          </section>

          <section className="contract-point">
            <header><span>1</span><div><small>Identificación</small><h2>Datos del contrato y docente</h2></div></header>
            <dl className="contract-data-grid">
              <div><dt>Número de contrato</dt><dd>{textOrPending(selected.numero_contrato)}</dd></div>
              <div><dt>Tipo de contrato</dt><dd>{textOrPending(selected.tipo_nombre)}</dd></div>
              <div><dt>Cédula</dt><dd>{textOrPending(data?.teacher?.cedula)}</dd></div>
              <div><dt>Correo institucional</dt><dd>{textOrPending(data?.teacher?.correo)}</dd></div>
              <div><dt>Relación laboral</dt><dd>{textOrPending(data?.teacher?.relacion_laboral)}</dd></div>
              <div><dt>Tiempo de dedicación</dt><dd>{textOrPending(data?.teacher?.tiempo_dedicacion)}</dd></div>
            </dl>
          </section>

          <section className="contract-point">
            <header><span>2</span><div><small>Vigencia</small><h2>Periodo y fechas</h2></div></header>
            <dl className="contract-data-grid contract-data-grid--three">
              <div><dt>Periodo académico</dt><dd>{textOrPending(selected.codigo_periodo)}</dd></div>
              <div><dt>Fecha de inicio</dt><dd>{formatDate(selected.fecha_inicio)}</dd></div>
              <div><dt>Fecha de finalización</dt><dd>{formatDate(selected.fecha_fin)}</dd></div>
            </dl>
          </section>

          <section className="contract-point">
            <header><span>3</span><div><small>Condiciones</small><h2>Valores económicos registrados</h2></div></header>
            <dl className="contract-data-grid contract-data-grid--three">
              <div><dt>Valor por hora</dt><dd>{formatMoney(selected.valor_hora_clase)}</dd></div>
              <div><dt>Valor mensual</dt><dd>{formatMoney(selected.valor_mensual)}</dd></div>
              <div><dt>Valor total del contrato</dt><dd>{formatMoney(selected.valor_total_contrato)}</dd></div>
            </dl>
          </section>

          <section className="contract-point">
            <header><span>4</span><div><small>Respaldo</small><h2>Responsable, observación y documento</h2></div></header>
            <dl className="contract-data-grid contract-data-grid--three">
              <div><dt>Responsable de contratación</dt><dd>{textOrPending(selected.responsable_contratacion)}</dd></div>
              <div><dt>Observación</dt><dd>{textOrPending(selected.observacion)}</dd></div>
              <div><dt>Contrato firmado</dt><dd>{selected.ruta_contrato_firmado ? 'Documento registrado' : 'Pendiente de registro'}</dd></div>
            </dl>
          </section>

          <section className="contract-point contract-point--classes">
            <header><span>5</span><div><small>Carga académica</small><h2>Materias incluidas en el contrato</h2></div></header>
            <div className="contract-table-wrap">
              <table className="contract-table">
                <thead><tr><th>Materia</th><th>Carrera</th><th>Periodo</th><th>Paralelo</th><th>Jornada</th><th>Horas</th><th>Ejecutadas</th><th>Valor hora</th><th>Estado</th></tr></thead>
                <tbody>
                  {selected.clases.length ? selected.clases.map((item) => (
                    <tr key={item.clase_id}>
                      <td><strong>{textOrPending(item.nombre_materia)}</strong><small>{textOrPending(item.codigo_materia)}</small></td>
                      <td>{textOrPending(item.nombre_carrera)}</td>
                      <td>{textOrPending(item.codigo_periodo)}</td>
                      <td>{textOrPending(item.paralelo)}</td>
                      <td>{textOrPending(item.jornada)}</td>
                      <td>{item.horas_planificadas ?? 0}</td>
                      <td>{item.horas_ejecutadas ?? 0}</td>
                      <td>{formatMoney(item.valor_hora)}</td>
                      <td><span className="contract-class-status">{textOrPending(item.estado)}</span></td>
                    </tr>
                  )) : <tr><td colSpan={9} className="contract-table-empty">Este contrato no tiene materias asociadas.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}
