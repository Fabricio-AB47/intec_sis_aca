import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { TITULACION_ROLES, getTitulacionRoles, titulacionRoleGuard } from './auth.guard';

describe('titulacionRoleGuard', () => {
  const router = jasmine.createSpyObj<Router>('Router', ['navigateByUrl']);

  beforeEach(() => {
    localStorage.clear();
    router.navigateByUrl.calls.reset();
    TestBed.configureTestingModule({
      providers: [{ provide: Router, useValue: router }]
    });
  });

  afterEach(() => localStorage.clear());

  it('normaliza roles heredados a los roles formales del modulo', () => {
    localStorage.setItem('intec_roles', JSON.stringify(['TITULACION_ADMIN', 'TITULACION_COORDINADOR']));

    const roles = getTitulacionRoles();

    expect(roles).toContain(TITULACION_ROLES.admin);
    expect(roles).toContain(TITULACION_ROLES.coordinador);
  });

  it('permite una ruta cuando el usuario tiene el rol requerido', () => {
    localStorage.setItem('intec_roles', JSON.stringify([TITULACION_ROLES.secretaria]));

    const result = TestBed.runInInjectionContext(() =>
      titulacionRoleGuard({ data: { roles: [TITULACION_ROLES.secretaria] } } as any, {} as any)
    );

    expect(result).toBeTrue();
    expect(router.navigateByUrl).not.toHaveBeenCalled();
  });

  it('bloquea una ruta cuando faltan roles', () => {
    localStorage.setItem('intec_roles', JSON.stringify([TITULACION_ROLES.consulta]));

    const result = TestBed.runInInjectionContext(() =>
      titulacionRoleGuard({ data: { roles: [TITULACION_ROLES.autoridad] } } as any, {} as any)
    );

    expect(result).toBeFalse();
    expect(router.navigateByUrl).toHaveBeenCalledWith('/titulacion/dashboard');
  });

  it('bloquea cuando no existe lista de roles', () => {
    const result = TestBed.runInInjectionContext(() =>
      titulacionRoleGuard({ data: { roles: [TITULACION_ROLES.admin] } } as any, {} as any)
    );

    expect(result).toBeFalse();
  });
});
