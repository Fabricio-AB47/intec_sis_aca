import { ReporteriaIntegralView } from './ReporteriaIntegralView'

type ReportesIndividualesViewProps = {
  displayName: string
  initialReportKey?: string
}

export function ReportesIndividualesView({ displayName, initialReportKey }: Readonly<ReportesIndividualesViewProps>) {
  const heading =
    initialReportKey === 'notas_carrera_materia'
      ? 'Notas por carrera y periodo'
      : initialReportKey === 'estud_per_c_m'
        ? 'Estudiantes por periodo, carrera y materia'
        : initialReportKey === 'becas_edades'
          ? 'Becas y edades'
          : 'Reportes por modulo'

  return (
    <ReporteriaIntegralView
      displayName={displayName}
      eyebrow="Reporteria"
      heading={heading}
      individualMode
      initialReportKey={initialReportKey}
    />
  )
}
