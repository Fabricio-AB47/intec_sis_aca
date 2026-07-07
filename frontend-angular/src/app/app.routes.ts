import { Routes } from '@angular/router';
import { TITULACION_ROLES, TODOS_LOS_ROLES_TITULACION, titulacionRoleGuard } from './core/auth.guard';
import {
  ActasGradoComponent,
  CalificacionesComponent,
  ComplexivoComponent,
  DefensaGradoComponent,
  DocumentosTitulacionComponent,
  EstudiantesAptosComponent,
  GruposTitulacionComponent,
  HabilitacionesComponent,
  ReportesTitulacionComponent,
  ResponsablesComponent,
  TitulacionDashboardComponent,
  TitulacionLayoutComponent,
  TitulosPortalComponent
} from './features/titulacion/titulacion.components';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'titulacion/dashboard' },
  {
    path: 'titulacion',
    component: TitulacionLayoutComponent,
    canActivate: [titulacionRoleGuard],
    canActivateChild: [titulacionRoleGuard],
    data: { roles: TODOS_LOS_ROLES_TITULACION },
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: TitulacionDashboardComponent, data: { roles: TODOS_LOS_ROLES_TITULACION } },
      { path: 'estudiantes-aptos', component: EstudiantesAptosComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.secretaria, TITULACION_ROLES.coordinador, TITULACION_ROLES.autoridad, TITULACION_ROLES.consulta] } },
      { path: 'habilitaciones', component: HabilitacionesComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.coordinador] } },
      { path: 'grupos', component: GruposTitulacionComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.coordinador] } },
      { path: 'complexivo', component: ComplexivoComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.coordinador] } },
      { path: 'defensa-grado', component: DefensaGradoComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.coordinador] } },
      { path: 'responsables', component: ResponsablesComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.coordinador] } },
      { path: 'calificaciones', component: CalificacionesComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.coordinador, TITULACION_ROLES.evaluador] } },
      { path: 'documentos', component: DocumentosTitulacionComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.secretaria, TITULACION_ROLES.coordinador] } },
      { path: 'titulos', component: TitulosPortalComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.secretaria] } },
      { path: 'actas', component: ActasGradoComponent, data: { roles: [TITULACION_ROLES.admin, TITULACION_ROLES.autoridad] } },
      { path: 'reportes', component: ReportesTitulacionComponent, data: { roles: TODOS_LOS_ROLES_TITULACION } }
    ]
  },
  { path: '**', redirectTo: 'titulacion/dashboard' }
];
