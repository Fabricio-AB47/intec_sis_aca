import { expect, test, type Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await mockTitulacionApi(page);
});

test('dashboard carga resumen con rol autorizado', async ({ page }) => {
  await setRoles(page, ['ADMIN_TITULACION']);

  await page.goto('/titulacion/dashboard');

  await expect(page.getByRole('heading', { name: 'Dashboard de titulación' })).toBeVisible();
  await expect(page.getByText('Estudiantes aptos')).toBeVisible();
  await expect(page.getByRole('main').getByText('Actas')).toBeVisible();
});

test('estudiantes aptos muestra aptos y bloquea habilitar pendientes', async ({ page }) => {
  await setRoles(page, ['ADMIN_TITULACION']);

  await page.goto('/titulacion/estudiantes-aptos');

  await expect(page.getByText('Ada Lovelace')).toBeVisible();
  await expect(page.getByText('Grace Hopper')).toBeVisible();
  await expect(page.locator('tr', { hasText: 'Grace Hopper' }).getByRole('button', { name: 'Habilitar' })).toBeDisabled();
  await expect(page.locator('tr', { hasText: 'Ada Lovelace' }).getByRole('button', { name: 'Habilitar' })).toBeEnabled();
});

test('secretaria no puede entrar a actas y vuelve al dashboard', async ({ page }) => {
  await setRoles(page, ['SECRETARIA_TITULACION']);

  await page.goto('/titulacion/actas');

  await expect(page).toHaveURL(/\/titulacion\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Dashboard de titulación' })).toBeVisible();
});

test('portal de titulos exige metadatos SENESCYT antes de cargar', async ({ page }) => {
  await setRoles(page, ['SECRETARIA_TITULACION']);

  await page.goto('/titulacion/titulos');
  await page.locator('app-upload-titulo-base input[formcontrolname="expedienteId"]').first().fill('20');
  await page.locator('app-upload-titulo-base input[formcontrolname="rutaNubeManual"]').first().fill('https://storage/titulo.pdf');
  let dialogMessage = '';
  page.once('dialog', async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.accept();
  });
  await page.getByRole('button', { name: 'Cargar título' }).first().click();

  expect(dialogMessage).toContain('SENESCYT');
});

async function setRoles(page: Page, roles: string[]) {
  await page.addInitScript((value) => {
    window.localStorage.setItem('intec_roles', JSON.stringify(value));
  }, roles);
}

async function mockTitulacionApi(page: Page) {
  await page.route('**/api/titulacion/dashboard/resumen', async (route) => {
    await route.fulfill({
      json: {
        estudiantesAptos: 2,
        estudiantesHabilitados: 1,
        examenesComplexivosProgramados: 1,
        defensasProgramadas: 0,
        actasGeneradas: 1,
        titulosRegistradosCargados: 0,
        titulosIntecCargados: 0,
        expedientesConDocumentosPendientes: 1,
        calificacionesPendientes: 1
      }
    });
  });

  await page.route('**/api/titulacion/estudiantes-aptos**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          estudiante('0102030405', 'Ada Lovelace', true),
          estudiante('0203040506', 'Grace Hopper', false)
        ],
        total: 2,
        page: 1,
        pageSize: 100
      }
    });
  });

  await page.route('**/api/titulacion/titulos**', async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.route('**/api/titulacion/actas**', async (route) => {
    await route.fulfill({ json: [] });
  });
}

function estudiante(cedula: string, nombres: string, puedeHabilitar: boolean) {
  return {
    cedula,
    nombres,
    codigoEstud: 1,
    carrera: 'Software',
    codigoCarrera: 'SW',
    periodo: '2026A',
    cumpleTituloBachiller: puedeHabilitar,
    cumpleInglesA2: puedeHabilitar,
    cumplePracticas: puedeHabilitar,
    cumpleVinculacion: puedeHabilitar,
    cumpleMalla: puedeHabilitar,
    noAdeudaFinanciero: puedeHabilitar,
    aptoSustentacion: puedeHabilitar,
    notaAsignaturas: puedeHabilitar ? 9.47 : null,
    equivalencia80: puedeHabilitar ? 7.576 : null,
    puedeHabilitar,
    motivoNoApto: puedeHabilitar ? '' : 'Pendiente practicas',
    estado: puedeHabilitar ? 'APTO' : 'PENDIENTE'
  };
}
