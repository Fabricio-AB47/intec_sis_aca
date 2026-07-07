import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

export const TITULACION_ROLES = {
  admin: 'ADMIN_TITULACION',
  secretaria: 'SECRETARIA_TITULACION',
  coordinador: 'COORDINADOR_ACADEMICO',
  evaluador: 'EVALUADOR_TITULACION',
  autoridad: 'AUTORIDAD_ACADEMICA',
  consulta: 'CONSULTA_TITULACION'
} as const;

export const TODOS_LOS_ROLES_TITULACION = Object.values(TITULACION_ROLES);

const ROLE_ALIASES: Record<string, string> = {
  ADMIN: TITULACION_ROLES.admin,
  TITULACION_ADMIN: TITULACION_ROLES.admin,
  TITULACION_COORDINADOR: TITULACION_ROLES.coordinador
};

export function getTitulacionRoles(): string[] {
  const rawRoles = localStorage.getItem('intec_roles');
  if (!rawRoles) return [];

  try {
    const roles = JSON.parse(rawRoles) as string[];
    const expanded = new Set<string>();
    roles.forEach((role) => {
      expanded.add(role);
      expanded.add(ROLE_ALIASES[role] ?? role);
    });
    return Array.from(expanded);
  } catch {
    return [];
  }
}

export const titulacionRoleGuard: CanActivateFn = (route) => {
  const router = inject(Router);
  const roles = getTitulacionRoles();
  const required = (route.data?.['roles'] as string[] | undefined) ?? [];

  if (!required.length || required.some((role) => roles.includes(role))) {
    return true;
  }

  router.navigateByUrl('/titulacion/dashboard');
  return false;
};
