import type { DirectAdmissionCredentialNames } from '../../types/app'

export function proposedCredentialNames(names: string, surnames: string): DirectAdmissionCredentialNames {
  const [firstName = '', ...otherNames] = names.trim().split(/\s+/)
  const [firstSurname = '', ...otherSurnames] = surnames.trim().split(/\s+/)
  return { primer_nombre: firstName, segundo_nombre: otherNames.join(' '), primer_apellido: firstSurname, segundo_apellido: otherSurnames.join(' ') }
}
