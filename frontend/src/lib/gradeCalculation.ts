export function constrainDecimalInput(value: string, maximum: number, decimals = 2): string | null {
  const normalized = value.replace(',', '.')
  if (normalized === '') return ''
  if (!/^-?\d*(?:\.\d*)?$/.test(normalized) || ['-', '.', '-.'].includes(normalized)) return null

  const parsed = Number(normalized)
  if (!Number.isFinite(parsed)) return null
  if (parsed < 0) return '0'
  if (parsed > maximum) return String(maximum)

  const [integer, fraction] = normalized.split('.')
  if (fraction !== undefined && fraction.length > decimals) {
    return `${integer}.${fraction.slice(0, decimals)}`
  }
  return normalized
}

export function parseBoundedDecimal(value: string, maximum: number, label: string): number | null {
  const normalized = value.trim().replace(',', '.')
  if (!normalized) return null

  const parsed = Number(normalized)
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > maximum) {
    throw new Error(`${label} debe estar entre 0 y ${maximum}.`)
  }
  return parsed
}

export type RegularGradeCalculation = {
  partials: [number | null, number | null, number | null]
  final: number | null
  replacement: { partialIndex: number; componentIndex: number } | null
}

function roundGrade(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

function weightedPartial(partial: ReadonlyArray<number | null>): number | null {
  if (partial.length !== 3 || partial.some((value) => value === null)) return null
  const [tasks, projects, exam] = partial.map(Number)
  return roundGrade((tasks * 0.3) + (projects * 0.3) + (exam * 0.4))
}

export function calculateRegularGradeWithRecovery(
  partials: Array<ReadonlyArray<number | null>>,
  recovery: number | null,
): RegularGradeCalculation {
  if (partials.length !== 3 || partials.some((partial) => partial.length !== 3)) {
    return { partials: [null, null, null], final: null, replacement: null }
  }

  const adjusted = partials.map((partial) => [...partial])
  const allComponents = adjusted.flat()
  let replacement: RegularGradeCalculation['replacement'] = null
  if (recovery !== null && allComponents.every((value) => value !== null)) {
    const numericComponents = allComponents.map(Number)
    const lowest = Math.min(...numericComponents)
    if (recovery > lowest) {
      const lowestIndex = numericComponents.indexOf(lowest)
      const partialIndex = Math.floor(lowestIndex / 3)
      const componentIndex = lowestIndex % 3
      adjusted[partialIndex][componentIndex] = recovery
      replacement = { partialIndex, componentIndex }
    }
  }

  const calculated = adjusted.map(weightedPartial) as [number | null, number | null, number | null]
  const final = calculated.some((partial) => partial === null)
    ? null
    : roundGrade(calculated.reduce<number>((total, partial) => total + Number(partial), 0) / 3)

  return { partials: calculated, final, replacement }
}

export function regularFinalWithRecovery(
  partials: Array<ReadonlyArray<number | null>>,
  recovery: number | null,
): number | null {
  return calculateRegularGradeWithRecovery(partials, recovery).final
}
