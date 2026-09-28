export type ValidationCourse = { id: number; fullname: string; shortname: string; category: string; parallel: string }
export type ValidationCatalog = {
  periods: Array<{ code: number; name: string; enrollment_type: string }>
  parallels: string[]
  courses: ValidationCourse[]
  careers: Array<{ code: number; name: string; period_codes: number[] }>
  max_courses: number
}
export type ValidationSelection = { period_code: number; courses: Array<{ id: number; parallel: string }> }
export type AcademicValidationSelection = ValidationSelection & { career_code: number }
export type ValidationRow = {
  status: string; status_label: string; student_code: string; student: string; document: string
  email: string; moodle_email: string; moodle_user_id: string; course_id: string; course: string
  moodle_code: string; subject_code: string; subject: string; academic_career: string
  moodle_idnumber: string; code_match: string; code_match_detail: string; code_candidates: string
  period: string; period_code: string; academic_parallel: string; moodle_parallel: string
  period_careers: string; previous_careers: string; career_changes: string; reason: string
  enrollment_periods?: string; subject_careers?: string; period_relation?: string
}
export type ValidationStudent = {
  student_code: string; student: string; document: string; email: string; academic_career: string
  career_code: string; period: string; period_code: string; findings: number; query_error: string
  evaluated_subjects?: number
  academic_subjects: Array<{ subject_id: number; subject_code: string; subject: string; semester: number; parallel: string; linked: boolean; in_scope?: boolean }>
  moodle_courses: ValidationRow[]; rows: ValidationRow[]
}
export type AcademicValidationJob = {
  job_id: string; status: 'running' | 'completed' | 'error'; processed: number; total: number
  error: string; report: ValidationReport | null
  unit?: 'courses' | 'students'
}
export type ValidationReport = {
  mode?: 'academic'; course_selection?: boolean; career?: { code: number; name: string }; students?: ValidationStudent[]
  report_id: string; generated_at: string; actor: string; period: { code: number; name: string }
  scope: Array<{ id: number; name: string; parallel: string; subject_code: string; error: string; code_match: string; code_match_detail: string }>
  summary: { rows: number; matches: number; inactive: number; findings: number; career_history: number }
  warnings: string[]; rows: ValidationRow[]
}
