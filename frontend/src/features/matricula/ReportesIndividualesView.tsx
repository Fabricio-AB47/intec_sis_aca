import { ReporteriaIntegralView } from './ReporteriaIntegralView'

type ReportesIndividualesViewProps = {
  displayName: string
  role?: string
  initialReportKey?: string
}

export function ReportesIndividualesView({ displayName, role, initialReportKey }: Readonly<ReportesIndividualesViewProps>) {
  const heading =
    initialReportKey === 'notas_carrera_materia'
      ? 'Calificaciones de estudiantes'
      : initialReportKey === 'estud_per_c_m'
        ? 'Estudiantes por periodo, carrera y materia'
        : initialReportKey === 'becas_edades'
          ? 'Becas y edades'
          : 'Reportes por modulo'

  return (
    <ReporteriaIntegralView
      displayName={displayName}
      role={role}
      eyebrow="Reporteria"
      heading={heading}
      individualMode
      initialReportKey={initialReportKey}
    />
  )
}
