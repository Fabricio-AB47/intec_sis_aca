import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Inject, OnInit, Output, ViewChild, forwardRef, inject, input } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialog, MatDialogRef } from '@angular/material/dialog';
import { RouterModule } from '@angular/router';
import { finalize } from 'rxjs';
import {
  ActaGrado,
  CalificacionConsolidada,
  DashboardResumen,
  DocumentoTitulacion,
  DocumentoTitulacionHistorial,
  EstudianteApto,
  GrupoComplexivoTeams,
  GrupoEstudiante,
  GrupoTitulacion,
  Habilitacion,
  MecanismoTitulacion,
  RegistrarCalificacionEvaluadorRequest,
  ResponsableTitulacion,
  TituloTitulacion
} from '../../models/titulacion.models';
import {
  ActasGradoService,
  CalificacionesTitulacionService,
  DocumentosTitulacionService,
  EstudiantesAptosService,
  GrupoTitulacionService,
  HabilitacionTitulacionService,
  ReportesTitulacionService,
  ResponsablesTitulacionService,
  TitulacionDashboardService,
  TitulosTitulacionService
} from '../../services/titulacion-api.service';
import { MATERIAL_IMPORTS } from '../../shared/material.imports';
import { downloadBlob, estadoVisual } from '../../shared/ui-utils';

const COMMON_IMPORTS = [CommonModule, ReactiveFormsModule, RouterModule, ...MATERIAL_IMPORTS];

@Component({
  selector: 'app-titulacion-layout',
  standalone: true,
  imports: [CommonModule, RouterModule, ...MATERIAL_IMPORTS],
  template: `
    <mat-sidenav-container class="shell">
      <mat-sidenav mode="side" opened class="nav">
        <div class="brand">
          <strong>INTEC</strong>
          <span>Titulación</span>
        </div>
        <a *ngFor="let item of nav" [routerLink]="item.link" routerLinkActive="active">
          <mat-icon>{{ item.icon }}</mat-icon>
          <span>{{ item.label }}</span>
        </a>
      </mat-sidenav>
      <mat-sidenav-content>
        <mat-toolbar class="topbar">
          <span>Portal de Titulación</span>
          <span class="spacer"></span>
          <button mat-stroked-button routerLink="/titulacion/reportes">
            <mat-icon>ios_share</mat-icon>
            Reportes
          </button>
        </mat-toolbar>
        <main class="page">
          <router-outlet />
        </main>
      </mat-sidenav-content>
    </mat-sidenav-container>
  `
})
export class TitulacionLayoutComponent {
  nav = [
    { label: 'Dashboard', link: '/titulacion/dashboard', icon: 'dashboard' },
    { label: 'Aptos', link: '/titulacion/estudiantes-aptos', icon: 'school' },
    { label: 'Habilitaciones', link: '/titulacion/habilitaciones', icon: 'how_to_reg' },
    { label: 'Grupos', link: '/titulacion/grupos', icon: 'groups' },
    { label: 'Complexivo', link: '/titulacion/complexivo', icon: 'quiz' },
    { label: 'Defensa', link: '/titulacion/defensa-grado', icon: 'record_voice_over' },
    { label: 'Responsables', link: '/titulacion/responsables', icon: 'badge' },
    { label: 'Calificaciones', link: '/titulacion/calificaciones', icon: 'fact_check' },
    { label: 'Documentos', link: '/titulacion/documentos', icon: 'folder' },
    { label: 'Títulos', link: '/titulacion/titulos', icon: 'workspace_premium' },
    { label: 'Actas', link: '/titulacion/actas', icon: 'picture_as_pdf' }
  ];
}

@Component({
  selector: 'app-titulacion-dashboard',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <section class="section-head">
      <div>
        <h1>Dashboard de titulación</h1>
        <p>Resumen operativo del proceso académico, documental y de calificación.</p>
      </div>
      <button mat-flat-button color="primary" (click)="load()"><mat-icon>refresh</mat-icon>Actualizar</button>
    </section>
    <mat-progress-bar *ngIf="loading" mode="indeterminate" />
    <section class="kpi-grid" *ngIf="resumen as r">
      <article class="kpi" *ngFor="let item of cards(r)">
        <mat-icon>{{ item.icon }}</mat-icon>
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>
  `
})
export class TitulacionDashboardComponent implements OnInit {
  private readonly service = inject(TitulacionDashboardService);
  resumen?: DashboardResumen;
  loading = false;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.service
      .getResumen()
      .pipe(finalize(() => (this.loading = false)))
      .subscribe((resumen) => (this.resumen = resumen));
  }

  cards(r: DashboardResumen) {
    return [
      { label: 'Estudiantes aptos', value: r.estudiantesAptos, icon: 'school' },
      { label: 'Habilitados', value: r.estudiantesHabilitados, icon: 'how_to_reg' },
      { label: 'Complexivos', value: r.examenesComplexivosProgramados, icon: 'quiz' },
      { label: 'Defensas', value: r.defensasProgramadas, icon: 'record_voice_over' },
      { label: 'Actas', value: r.actasGeneradas, icon: 'picture_as_pdf' },
      { label: 'Títulos SENESCYT', value: r.titulosRegistradosCargados, icon: 'verified' },
      { label: 'Títulos INTEC', value: r.titulosIntecCargados, icon: 'workspace_premium' },
      { label: 'Docs. pendientes', value: r.expedientesConDocumentosPendientes, icon: 'folder_off' },
      { label: 'Calif. pendientes', value: r.calificacionesPendientes, icon: 'pending_actions' }
    ];
  }
}

@Component({
  selector: 'app-estudiantes-aptos',
  standalone: true,
  imports: [forwardRef(() => RequisitoChipComponent), ...COMMON_IMPORTS],
  template: `
    <section class="section-head">
      <div>
        <h1>Estudiantes aptos</h1>
        <p>Validación académica, financiera, documental, Prácticas laborales y Servicio Comunitario.</p>
      </div>
      <button mat-flat-button color="primary" (click)="sincronizar()"><mat-icon>sync</mat-icon>Sincronizar</button>
    </section>
    <form class="filters" [formGroup]="filters" (ngSubmit)="load()">
      <mat-form-field><mat-label>Cédula</mat-label><input matInput formControlName="cedula" /></mat-form-field>
      <mat-form-field><mat-label>Nombres</mat-label><input matInput formControlName="nombres" /></mat-form-field>
      <mat-form-field><mat-label>Carrera</mat-label><input matInput formControlName="carrera" /></mat-form-field>
      <mat-form-field><mat-label>Periodo</mat-label><input matInput formControlName="periodo" /></mat-form-field>
      <button mat-stroked-button type="submit"><mat-icon>search</mat-icon>Buscar</button>
    </form>
    <mat-progress-bar *ngIf="loading" mode="indeterminate" />
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>Cédula</th><th>Estudiante</th><th>Carrera</th><th>Periodo</th>
            <th>Bachiller</th><th>Inglés</th><th>Servicio Comunitario</th><th>Prácticas laborales</th>
            <th>Malla</th><th>Financiero</th><th>Sustentación</th><th>Nota</th><th>80%</th><th>Estado</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let e of estudiantes">
            <td>{{ e.cedula }}</td>
            <td><strong>{{ e.nombres }}</strong></td>
            <td>{{ e.carrera }}</td>
            <td>{{ e.periodo }}</td>
            <td><app-requisito-chip [ok]="e.cumpleTituloBachiller" /></td>
            <td><app-requisito-chip [ok]="e.cumpleInglesA2" /></td>
            <td><app-requisito-chip [ok]="e.cumpleVinculacion" /></td>
            <td><app-requisito-chip [ok]="e.cumplePracticas" /></td>
            <td><app-requisito-chip [ok]="e.cumpleMalla" /></td>
            <td><app-requisito-chip [ok]="e.noAdeudaFinanciero" /></td>
            <td><app-requisito-chip [ok]="e.aptoSustentacion" /></td>
            <td>{{ e.notaAsignaturas ?? 'N/D' }}</td>
            <td>{{ e.equivalencia80 ?? 'N/D' }}</td>
            <td><span class="status" [class]="estado(e.estado)">{{ e.estado || (e.puedeHabilitar ? 'APTO' : 'PENDIENTE') }}</span></td>
            <td><button mat-flat-button color="primary" [disabled]="!e.puedeHabilitar" (click)="habilitar(e)">Habilitar</button></td>
          </tr>
          <tr *ngIf="!estudiantes.length && !loading"><td colspan="15" class="empty">No hay estudiantes para los filtros seleccionados.</td></tr>
        </tbody>
      </table>
    </div>
  `
})
export class EstudiantesAptosComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(EstudiantesAptosService);
  private readonly dialog = inject(MatDialog);
  estudiantes: EstudianteApto[] = [];
  loading = false;
  filters = this.fb.group({ cedula: [''], nombres: [''], carrera: [''], periodo: [''] });

  ngOnInit(): void {
    this.load();
  }

  estado = estadoVisual;

  load(): void {
    this.loading = true;
    const value = this.filters.value;
    this.service
      .get({
        cedula: value.cedula || undefined,
        nombres: value.nombres || undefined,
        carrera: value.carrera || undefined,
        periodo: value.periodo || undefined,
        page: 1,
        pageSize: 100
      })
      .pipe(finalize(() => (this.loading = false)))
      .subscribe((result) => (this.estudiantes = result.items ?? []));
  }

  sincronizar(): void {
    this.loading = true;
    this.service.sincronizar().pipe(finalize(() => (this.loading = false))).subscribe(() => this.load());
  }

  habilitar(estudiante: EstudianteApto): void {
    this.dialog.open(ModalHabilitarEstudianteComponent, { data: estudiante, width: '760px' }).afterClosed().subscribe((saved) => {
      if (saved) this.load();
    });
  }
}

@Component({
  selector: 'app-requisito-chip',
  standalone: true,
  imports: [CommonModule, ...MATERIAL_IMPORTS],
  template: `<span class="req" [class.ok]="ok()" [class.bad]="!ok()">{{ ok() ? 'Cumple' : 'Pendiente' }}</span>`
})
export class RequisitoChipComponent {
  ok = input(false);
}

@Component({
  selector: 'app-modal-habilitar-estudiante',
  standalone: true,
  imports: [forwardRef(() => RequisitoChipComponent), ...COMMON_IMPORTS],
  template: `
    <h2 mat-dialog-title>Habilitar estudiante</h2>
    <mat-dialog-content>
      <div class="summary">
        <strong>{{ data.nombres }}</strong>
        <span>{{ data.cedula }} · {{ data.carrera }} · {{ data.periodo }}</span>
      </div>
      <div class="req-list">
        <app-requisito-chip [ok]="data.cumpleTituloBachiller" />
        <app-requisito-chip [ok]="data.cumpleInglesA2" />
        <app-requisito-chip [ok]="data.cumplePracticas" />
        <app-requisito-chip [ok]="data.cumpleVinculacion" />
        <app-requisito-chip [ok]="data.cumpleMalla" />
        <app-requisito-chip [ok]="data.noAdeudaFinanciero" />
        <app-requisito-chip [ok]="data.aptoSustentacion" />
      </div>
      <form class="dialog-form" [formGroup]="form">
        <mat-form-field>
          <mat-label>Mecanismo</mat-label>
          <mat-select formControlName="mecanismoCodigo">
            <mat-option value="EXAMEN_COMPLEXIVO">Examen complexivo</mat-option>
            <mat-option value="DEFENSA_GRADO">Defensa de grado</mat-option>
          </mat-select>
        </mat-form-field>
        <mat-form-field><mat-label>Tema</mat-label><textarea matInput rows="2" formControlName="tema"></textarea></mat-form-field>
        <mat-form-field><mat-label>Fecha</mat-label><input matInput type="date" formControlName="fechaProgramada" /></mat-form-field>
        <mat-form-field><mat-label>Hora inicio</mat-label><input matInput type="time" formControlName="horaInicio" /></mat-form-field>
        <mat-form-field><mat-label>Hora fin</mat-label><input matInput type="time" formControlName="horaFin" /></mat-form-field>
        <mat-form-field>
          <mat-label>Modalidad</mat-label>
          <mat-select formControlName="modalidad">
            <mat-option value="PRESENCIAL">Presencial</mat-option>
            <mat-option value="VIRTUAL">Virtual</mat-option>
            <mat-option value="HIBRIDA">Híbrida</mat-option>
          </mat-select>
        </mat-form-field>
        <mat-form-field *ngIf="form.value.mecanismoCodigo === 'EXAMEN_COMPLEXIVO'">
          <mat-label>Grupo existente</mat-label>
          <input matInput type="number" formControlName="grupoTitulacionId" placeholder="Opcional" />
        </mat-form-field>
        <mat-form-field *ngIf="form.value.mecanismoCodigo === 'DEFENSA_GRADO'">
          <mat-label>Expediente acompañante</mat-label>
          <input matInput type="number" placeholder="Opcional, máximo 2 estudiantes" />
        </mat-form-field>
        <mat-form-field><mat-label>Observación</mat-label><textarea matInput rows="2" formControlName="observacion"></textarea></mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancelar</button>
      <button mat-flat-button color="primary" [disabled]="form.invalid || saving" (click)="save()">Guardar</button>
    </mat-dialog-actions>
  `
})
export class ModalHabilitarEstudianteComponent {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(HabilitacionTitulacionService);
  private readonly ref = inject(MatDialogRef<ModalHabilitarEstudianteComponent>);
  saving = false;
  form = this.fb.group({
    mecanismoCodigo: ['EXAMEN_COMPLEXIVO' as MecanismoTitulacion, Validators.required],
    tema: [''],
    fechaProgramada: [''],
    horaInicio: [''],
    horaFin: [''],
    modalidad: ['PRESENCIAL'],
    grupoTitulacionId: [null as number | null],
    observacion: ['']
  });

  constructor(@Inject(MAT_DIALOG_DATA) public data: EstudianteApto) {}

  save(): void {
    if (!confirm('¿Confirmas habilitar este estudiante para titulación?')) return;
    this.saving = true;
    this.service
      .habilitar({ cedula: this.data.cedula, ...(this.form.value as any) })
      .pipe(finalize(() => (this.saving = false)))
      .subscribe((result) => this.ref.close(result));
  }
}

@Component({
  selector: 'app-habilitaciones',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <section class="section-head"><div><h1>Habilitaciones</h1><p>Estudiantes habilitados para iniciar proceso de titulación.</p></div></section>
    <mat-progress-bar *ngIf="loading" mode="indeterminate" />
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>ID</th><th>Cédula</th><th>Carrera</th><th>Mecanismo</th><th>Estado</th><th>Fecha</th><th></th></tr></thead>
        <tbody>
          <tr *ngFor="let h of items">
            <td>{{ h.habilitacionId }}</td><td>{{ h.numeroIdentificacion }}</td><td>{{ h.carrera }}</td>
            <td>{{ h.mecanismoCodigo }}</td><td><span class="status" [class]="estado(h.estadoCodigo)">{{ h.estadoCodigo }}</span></td>
            <td>{{ h.fechaHabilitacion | date:'short' }}</td>
            <td><button mat-button color="warn" (click)="anular(h)">Anular</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  `
})
export class HabilitacionesComponent implements OnInit {
  private readonly service = inject(HabilitacionTitulacionService);
  items: Habilitacion[] = [];
  loading = false;
  estado = estadoVisual;
  ngOnInit(): void { this.load(); }
  load(): void {
    this.loading = true;
    this.service.get().pipe(finalize(() => (this.loading = false))).subscribe((items) => (this.items = items));
  }
  anular(h: Habilitacion): void {
    if (!confirm(`¿Anular habilitación ${h.habilitacionId}?`)) return;
    this.service.anular(h.habilitacionId).subscribe(() => this.load());
  }
}

@Component({
  selector: 'app-grupos-titulacion',
  standalone: true,
  imports: [forwardRef(() => GruposTableComponent), ...COMMON_IMPORTS],
  template: `
    <section class="section-head">
      <div><h1>Grupos de titulación</h1><p>Programación de complexivos y defensas con expedientes individuales.</p></div>
      <div class="actions"><button mat-flat-button color="primary" (click)="crearComplexivo()">Crear complexivo</button></div>
    </section>
    <app-grupos-table [mecanismo]="mecanismo" />
  `
})
export class GruposTitulacionComponent {
  mecanismo?: MecanismoTitulacion;
  private readonly service = inject(GrupoTitulacionService);
  crearComplexivo(): void {
    const codigoGrupo = prompt('Código del grupo');
    if (codigoGrupo) this.service.crearComplexivo({ codigoGrupo, modalidad: 'PRESENCIAL' }).subscribe(() => location.reload());
  }
}

@Component({
  selector: 'app-grupos-table',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <mat-progress-bar *ngIf="loading" mode="indeterminate" />
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Código</th><th>Tema</th><th>Carrera</th><th>Fecha</th><th>Hora</th><th>Modalidad</th><th>Enlace</th><th>Est.</th><th>Responsables</th><th>Estado</th><th>Acciones</th></tr></thead>
        <tbody>
          <tr *ngFor="let g of grupos">
            <td><strong>{{ g.codigoGrupo || g.grupoTitulacionId }}</strong></td>
            <td>{{ g.tema || g.nombreGrupo }}</td>
            <td>{{ g.carrera || 'N/D' }}</td>
            <td>{{ g.fechaProgramada || 'Pendiente' }}</td>
            <td>{{ g.horaInicio || 'N/D' }}</td>
            <td>{{ g.modalidad || 'N/D' }}</td>
            <td>
              <a *ngIf="g.aulaOLink" mat-icon-button [href]="g.aulaOLink" target="_blank" rel="noopener" matTooltip="Acceder a Teams">
                <mat-icon>video_call</mat-icon>
              </a>
              <span *ngIf="!g.aulaOLink" class="muted">Pendiente</span>
            </td>
            <td>{{ g.totalIntegrantes }}</td>
            <td>{{ responsables(g) }}</td>
            <td><span class="status" [class]="estado(g.estadoCodigo)">{{ g.estadoCodigo }}</span></td>
            <td class="row-actions">
              <button mat-icon-button matTooltip="Programar" (click)="programar(g)"><mat-icon>event</mat-icon></button>
              <button mat-icon-button matTooltip="Responsable" *ngIf="g.mecanismoCodigo === 'EXAMEN_COMPLEXIVO'" (click)="asignarComplexivo(g)"><mat-icon>assignment_ind</mat-icon></button>
              <button mat-icon-button matTooltip="Tribunal" *ngIf="g.mecanismoCodigo === 'DEFENSA_GRADO'" (click)="asignarTribunal(g)"><mat-icon>groups</mat-icon></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  `
})
export class GruposTableComponent implements OnInit {
  mecanismo = input<MecanismoTitulacion | undefined>();
  private readonly service = inject(GrupoTitulacionService);
  private readonly dialog = inject(MatDialog);
  grupos: GrupoTitulacion[] = [];
  loading = false;
  estado = estadoVisual;
  ngOnInit(): void { this.load(); }
  load(): void {
    this.loading = true;
    this.service.get(this.mecanismo()).pipe(finalize(() => (this.loading = false))).subscribe((items) => (this.grupos = items));
  }
  responsables(g: GrupoTitulacion): string {
    return (g.responsables || []).map((r) => `${r.rolCodigo}: ${r.nombres}`).join('; ') || 'Pendiente';
  }
  programar(g: GrupoTitulacion): void {
    const fechaProgramada = prompt('Fecha programada YYYY-MM-DD', g.fechaProgramada || '');
    if (!fechaProgramada) return;
    this.service.actualizarProgramacion(g.grupoTitulacionId, { fechaProgramada, modalidad: g.modalidad || 'PRESENCIAL' }).subscribe(() => this.load());
  }
  asignarComplexivo(g: GrupoTitulacion): void {
    this.dialog.open(ModalAsignarResponsableComplexivoComponent, { data: g, width: '640px' }).afterClosed().subscribe((ok) => ok && this.load());
  }
  asignarTribunal(g: GrupoTitulacion): void {
    this.dialog.open(ModalAsignarTribunalDefensaComponent, { data: g, width: '640px' }).afterClosed().subscribe((ok) => ok && this.load());
  }
}

@Component({
  selector: 'app-complexivo',
  standalone: true,
  imports: [GruposTableComponent, ...COMMON_IMPORTS],
  template: `
    <section class="section-head">
      <div>
        <h1>Examen complexivo</h1>
        <p>Crear grupos, asignar responsable y generar enlace de Teams para el calendario.</p>
      </div>
      <button mat-flat-button color="primary" type="submit" form="complexivoTeamsForm" [disabled]="form.invalid || saving">
        <mat-icon>event_available</mat-icon>
        Crear grupo Teams
      </button>
    </section>

    <form id="complexivoTeamsForm" class="form-panel complexivo-form" [formGroup]="form" (ngSubmit)="crearGrupoTeams()">
      <mat-form-field>
        <mat-label>Código del grupo</mat-label>
        <input matInput formControlName="codigoGrupo" placeholder="CX-2026-01" />
      </mat-form-field>
      <mat-form-field class="wide">
        <mat-label>Tema</mat-label>
        <input matInput formControlName="tema" />
      </mat-form-field>
      <mat-form-field>
        <mat-label>Carrera</mat-label>
        <input matInput formControlName="carrera" />
      </mat-form-field>
      <mat-form-field>
        <mat-label>Código carrera</mat-label>
        <input matInput formControlName="codigoCarrera" />
      </mat-form-field>
      <mat-form-field>
        <mat-label>Fecha</mat-label>
        <input matInput type="date" formControlName="fechaProgramada" />
      </mat-form-field>
      <mat-form-field>
        <mat-label>Hora inicio</mat-label>
        <input matInput type="time" formControlName="horaInicio" />
      </mat-form-field>
      <mat-form-field>
        <mat-label>Hora fin</mat-label>
        <input matInput type="time" formControlName="horaFin" />
      </mat-form-field>
      <mat-form-field>
        <mat-label>Modalidad</mat-label>
        <mat-select formControlName="modalidad">
          <mat-option value="VIRTUAL">Virtual</mat-option>
          <mat-option value="HIBRIDA">Híbrida</mat-option>
          <mat-option value="PRESENCIAL">Presencial</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field>
        <mat-label>Responsable</mat-label>
        <mat-select formControlName="responsableComplexivoId">
          <mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field>
        <mat-label>Evaluador 1</mat-label>
        <mat-select formControlName="evaluador1">
          <mat-option [value]="null">Pendiente</mat-option>
          <mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field>
        <mat-label>Evaluador 2</mat-label>
        <mat-select formControlName="evaluador2">
          <mat-option [value]="null">Pendiente</mat-option>
          <mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field>
        <mat-label>Evaluador 3</mat-label>
        <mat-select formControlName="evaluador3">
          <mat-option [value]="null">Pendiente</mat-option>
          <mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field class="wide">
        <mat-label>Correos invitados</mat-label>
        <textarea matInput formControlName="correosAsistentes" rows="2" placeholder="correo1@intec.edu.ec; correo2@intec.edu.ec"></textarea>
      </mat-form-field>
      <mat-form-field class="wide">
        <mat-label>Observación</mat-label>
        <textarea matInput formControlName="observacion" rows="2"></textarea>
      </mat-form-field>
    </form>

    <mat-progress-bar *ngIf="saving" mode="indeterminate" />

    <div class="notice error" *ngIf="errorMensaje">{{ errorMensaje }}</div>

    <div class="teams-result" *ngIf="ultimoTeamsUrl">
      <div>
        <span>Grupo creado</span>
        <strong>{{ ultimoResultado?.grupo?.codigoGrupo || ultimoResultado?.grupo?.grupoTitulacionId }}</strong>
      </div>
      <a mat-flat-button color="primary" [href]="ultimoTeamsUrl" target="_blank" rel="noopener">
        <mat-icon>open_in_new</mat-icon>
        Acceder a Teams
      </a>
    </div>

    <app-grupos-table #gruposTable mecanismo="EXAMEN_COMPLEXIVO" />
  `
})
export class ComplexivoComponent implements OnInit {
  @ViewChild('gruposTable') private gruposTable?: GruposTableComponent;
  private readonly fb = inject(FormBuilder);
  private readonly gruposService = inject(GrupoTitulacionService);
  private readonly responsablesService = inject(ResponsablesTitulacionService);
  responsables: ResponsableTitulacion[] = [];
  saving = false;
  errorMensaje = '';
  ultimoResultado?: GrupoComplexivoTeams;
  ultimoTeamsUrl?: string | null;
  form = this.fb.group({
    codigoGrupo: ['', Validators.required],
    tema: ['', Validators.required],
    carrera: [''],
    codigoCarrera: [''],
    fechaProgramada: ['', Validators.required],
    horaInicio: ['09:00', Validators.required],
    horaFin: ['11:00', Validators.required],
    modalidad: ['VIRTUAL', Validators.required],
    responsableComplexivoId: [null as number | null, Validators.required],
    evaluador1: [null as number | null],
    evaluador2: [null as number | null],
    evaluador3: [null as number | null],
    correosAsistentes: [''],
    observacion: ['']
  });

  ngOnInit(): void {
    this.responsablesService.get().subscribe((items) => (this.responsables = items));
  }

  crearGrupoTeams(): void {
    if (this.form.invalid || this.saving) return;
    this.errorMensaje = '';
    const evaluadores = [this.form.value.evaluador1, this.form.value.evaluador2, this.form.value.evaluador3].filter(Boolean) as number[];
    if (evaluadores.length > 0 && evaluadores.length < 3) {
      this.errorMensaje = 'Debe seleccionar los 3 evaluadores o dejarlos pendientes.';
      return;
    }
    if (new Set(evaluadores).size !== evaluadores.length) {
      this.errorMensaje = 'No se pueden repetir evaluadores.';
      return;
    }

    this.saving = true;
    this.gruposService.crearComplexivoTeams({
      codigoGrupo: this.form.value.codigoGrupo || null,
      tema: this.form.value.tema || null,
      carrera: this.form.value.carrera || null,
      codigoCarrera: this.form.value.codigoCarrera || null,
      fechaProgramada: this.form.value.fechaProgramada || null,
      horaInicio: this.form.value.horaInicio || null,
      horaFin: this.form.value.horaFin || null,
      modalidad: this.form.value.modalidad || 'VIRTUAL',
      responsableComplexivoId: this.form.value.responsableComplexivoId!,
      evaluadoresIds: evaluadores,
      correosAsistentes: this.correosInvitados(),
      observacion: this.form.value.observacion || null
    }).pipe(finalize(() => (this.saving = false))).subscribe({
      next: (result) => {
        this.ultimoResultado = result;
        this.ultimoTeamsUrl = result.teamsJoinUrl || result.grupo?.aulaOLink || null;
        this.gruposTable?.load();
      },
      error: (error) => {
        this.errorMensaje = error?.error?.detail || 'No se pudo crear el grupo ni el evento de Teams.';
      }
    });
  }

  private parseCorreos(value: string): string[] {
    return value
      .split(/[;,\n]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  private correosInvitados(): string[] {
    const correos = this.parseCorreos(this.form.value.correosAsistentes || '');
    const responsable = this.responsables.find((item) => item.responsableTitulacionId === this.form.value.responsableComplexivoId);
    if (responsable?.correo) {
      correos.push(responsable.correo);
    }

    return Array.from(new Set(correos.map((item) => item.trim()).filter(Boolean)));
  }
}

@Component({
  selector: 'app-defensa-grado',
  standalone: true,
  imports: [GruposTableComponent, ...COMMON_IMPORTS],
  template: `
    <section class="section-head"><div><h1>Defensa de grado</h1><p>Defensas unitarias o de máximo 2 estudiantes con tribunal obligatorio.</p></div></section>
    <app-grupos-table mecanismo="DEFENSA_GRADO" />
  `
})
export class DefensaGradoComponent {}

@Component({
  selector: 'app-responsables',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <section class="section-head"><div><h1>Responsables</h1><p>Catálogo de docentes, coordinadores, evaluadores y tribunal.</p></div></section>
    <form class="filters" [formGroup]="form" (ngSubmit)="save()">
      <mat-form-field><mat-label>Cédula</mat-label><input matInput formControlName="cedula" /></mat-form-field>
      <mat-form-field><mat-label>Nombres</mat-label><input matInput formControlName="nombres" /></mat-form-field>
      <mat-form-field><mat-label>Correo</mat-label><input matInput formControlName="correo" /></mat-form-field>
      <mat-form-field><mat-label>Cargo</mat-label><input matInput formControlName="cargo" /></mat-form-field>
      <mat-form-field><mat-label>Rol</mat-label><input matInput formControlName="rolCodigo" /></mat-form-field>
      <button mat-flat-button color="primary" type="submit" [disabled]="form.invalid">Guardar</button>
    </form>
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Cédula</th><th>Nombres</th><th>Correo</th><th>Cargo</th><th>Rol</th><th>Activo</th><th></th></tr></thead>
        <tbody><tr *ngFor="let r of items">
          <td>{{ r.cedula }}</td><td><strong>{{ r.nombres }}</strong></td><td>{{ r.correo }}</td><td>{{ r.cargo }}</td><td>{{ r.rolCodigo }}</td><td>{{ r.activo ? 'Sí' : 'No' }}</td>
          <td><button mat-button (click)="edit(r)">Editar</button><button mat-button color="warn" (click)="delete(r)">Inactivar</button></td>
        </tr></tbody>
      </table>
    </div>
  `
})
export class ResponsablesComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(ResponsablesTitulacionService);
  items: ResponsableTitulacion[] = [];
  editing?: ResponsableTitulacion;
  form = this.fb.group({ cedula: [''], nombres: ['', Validators.required], correo: [''], cargo: [''], rolCodigo: ['', Validators.required] });
  ngOnInit(): void { this.load(); }
  load(): void { this.service.get().subscribe((items) => (this.items = items)); }
  save(): void {
    const request = this.form.value as any;
    const call = this.editing ? this.service.actualizar(this.editing.responsableTitulacionId, request) : this.service.crear(request);
    call.subscribe(() => { this.form.reset(); this.editing = undefined; this.load(); });
  }
  edit(r: ResponsableTitulacion): void { this.editing = r; this.form.patchValue(r); }
  delete(r: ResponsableTitulacion): void {
    if (confirm(`¿Inactivar ${r.nombres}?`)) this.service.inactivar(r.responsableTitulacionId).subscribe(() => this.load());
  }
}

@Component({
  selector: 'app-modal-asignar-responsable-complexivo',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <h2 mat-dialog-title>Asignar responsable complexivo</h2>
    <mat-dialog-content>
      <form class="dialog-form" [formGroup]="form">
        <mat-form-field><mat-label>Responsable</mat-label><mat-select formControlName="responsableComplexivoId"><mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Evaluador 1</mat-label><mat-select formControlName="evaluador1"><mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Evaluador 2</mat-label><mat-select formControlName="evaluador2"><mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Evaluador 3</mat-label><mat-select formControlName="evaluador3"><mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Observación</mat-label><textarea matInput formControlName="observacion"></textarea></mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end"><button mat-button mat-dialog-close>Cancelar</button><button mat-flat-button color="primary" (click)="save()" [disabled]="form.invalid">Guardar</button></mat-dialog-actions>
  `
})
export class ModalAsignarResponsableComplexivoComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  protected readonly service = inject(ResponsablesTitulacionService);
  protected readonly ref = inject(MatDialogRef<ModalAsignarResponsableComplexivoComponent>);
  responsables: ResponsableTitulacion[] = [];
  form = this.fb.group({
    responsableComplexivoId: [null as number | null, Validators.required],
    evaluador1: [null as number | null, Validators.required],
    evaluador2: [null as number | null, Validators.required],
    evaluador3: [null as number | null, Validators.required],
    observacion: ['']
  });
  constructor(@Inject(MAT_DIALOG_DATA) public data: GrupoTitulacion) {}
  ngOnInit(): void { this.service.get().subscribe((items) => (this.responsables = items)); }
  save(): void {
    const ids = [this.form.value.evaluador1, this.form.value.evaluador2, this.form.value.evaluador3].filter(Boolean) as number[];
    if (new Set(ids).size !== ids.length) { alert('No se pueden repetir evaluadores.'); return; }
    this.service.asignarComplexivo(this.data.grupoTitulacionId, {
      grupoTitulacionId: this.data.grupoTitulacionId,
      responsableComplexivoId: this.form.value.responsableComplexivoId!,
      evaluadoresIds: ids,
      observacion: this.form.value.observacion || null
    }).subscribe(() => this.ref.close(true));
  }
}

@Component({
  selector: 'app-modal-asignar-tribunal-defensa',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <h2 mat-dialog-title>Asignar tribunal defensa</h2>
    <mat-dialog-content>
      <form class="dialog-form" [formGroup]="form">
        <mat-form-field><mat-label>Presidente</mat-label><mat-select formControlName="presidenteTribunalId"><mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Vocal 1</mat-label><mat-select formControlName="vocal1Id"><mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Vocal 2</mat-label><mat-select formControlName="vocal2Id"><mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Tutor opcional</mat-label><mat-select formControlName="tutorId"><mat-option [value]="null">Sin tutor</mat-option><mat-option *ngFor="let r of responsables" [value]="r.responsableTitulacionId">{{ r.nombres }}</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Observación</mat-label><textarea matInput formControlName="observacion"></textarea></mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end"><button mat-button mat-dialog-close>Cancelar</button><button mat-flat-button color="primary" (click)="save()" [disabled]="form.invalid">Guardar</button></mat-dialog-actions>
  `
})
export class ModalAsignarTribunalDefensaComponent implements OnInit {
  private readonly service = inject(ResponsablesTitulacionService);
  private readonly ref = inject(MatDialogRef<ModalAsignarTribunalDefensaComponent>);
  responsables: ResponsableTitulacion[] = [];
  form = inject(FormBuilder).group({
    presidenteTribunalId: [null as number | null, Validators.required],
    vocal1Id: [null as number | null, Validators.required],
    vocal2Id: [null as number | null, Validators.required],
    tutorId: [null as number | null],
    observacion: ['']
  });
  constructor(@Inject(MAT_DIALOG_DATA) public data: GrupoTitulacion) {}
  ngOnInit(): void {
    this.service.get().subscribe((items) => (this.responsables = items));
  }
  save(): void {
    const ids = [this.form.value.presidenteTribunalId, this.form.value.vocal1Id, this.form.value.vocal2Id].filter(Boolean) as number[];
    if (new Set(ids).size !== ids.length) { alert('No se puede repetir la misma persona en el tribunal.'); return; }
    this.service.asignarTribunal(this.data.grupoTitulacionId, {
      grupoTitulacionId: this.data.grupoTitulacionId,
      presidenteTribunalId: this.form.value.presidenteTribunalId!,
      vocal1Id: this.form.value.vocal1Id!,
      vocal2Id: this.form.value.vocal2Id!,
      tutorId: this.form.value.tutorId || null,
      observacion: this.form.value.observacion || null
    }).subscribe(() => this.ref.close(true));
  }
}

@Component({
  selector: 'app-calificaciones',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <section class="section-head"><div><h1>Calificaciones</h1><p>Calificación por estudiante y por tres evaluadores.</p></div></section>
    <form class="filters" [formGroup]="filters" (ngSubmit)="load()">
      <mat-form-field><mat-label>Mecanismo</mat-label><mat-select formControlName="mecanismo"><mat-option value="">Todos</mat-option><mat-option value="EXAMEN_COMPLEXIVO">Complexivo</mat-option><mat-option value="DEFENSA_GRADO">Defensa</mat-option></mat-select></mat-form-field>
      <button mat-stroked-button type="submit">Filtrar</button>
    </form>
    <div class="table-wrap"><table class="data-table">
      <thead><tr><th>Grupo</th><th>Mecanismo</th><th>Estudiante</th><th>Evaluadores</th><th>Acción</th></tr></thead>
      <tbody><ng-container *ngFor="let g of grupos"><tr *ngFor="let e of g.estudiantes || []">
        <td>{{ g.codigoGrupo || g.grupoTitulacionId }}</td><td>{{ g.mecanismoCodigo }}</td><td>{{ e.numeroIdentificacion }}</td>
        <td>1 · 2 · 3</td><td><button mat-flat-button color="primary" (click)="calificar(g, e)">Calificar</button></td>
      </tr></ng-container></tbody>
    </table></div>
  `
})
export class CalificacionesComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly gruposService = inject(GrupoTitulacionService);
  private readonly dialog = inject(MatDialog);
  grupos: GrupoTitulacion[] = [];
  filters = this.fb.group({ mecanismo: [''] });
  ngOnInit(): void { this.load(); }
  load(): void { this.gruposService.get(this.filters.value.mecanismo || undefined).subscribe((items) => (this.grupos = items)); }
  calificar(g: GrupoTitulacion, e: GrupoEstudiante): void {
    this.dialog.open(ModalCalificarEvaluadorComponent, { data: { grupo: g, estudiante: e }, width: '640px' }).afterClosed().subscribe((ok) => ok && this.load());
  }
}

@Component({
  selector: 'app-modal-calificar-evaluador',
  standalone: true,
  imports: [forwardRef(() => ConsolidadoNotasComponent), ...COMMON_IMPORTS],
  template: `
    <h2 mat-dialog-title>Registrar calificación</h2>
    <mat-dialog-content>
      <div class="summary">{{ data.estudiante.numeroIdentificacion }} · {{ data.grupo.mecanismoCodigo }} · {{ data.grupo.tema }}</div>
      <form class="dialog-form" [formGroup]="form">
        <mat-form-field><mat-label>Responsable/Evaluador ID</mat-label><input matInput type="number" formControlName="responsableTitulacionId" /></mat-form-field>
        <mat-form-field><mat-label>Evaluador</mat-label><mat-select formControlName="evaluadorNumero"><mat-option [value]="1">1</mat-option><mat-option [value]="2">2</mat-option><mat-option [value]="3">3</mat-option></mat-select></mat-form-field>
        <mat-form-field><mat-label>Trabajo escrito</mat-label><input matInput type="number" min="0" max="10" formControlName="notaTrabajoEscrito" /></mat-form-field>
        <mat-form-field><mat-label>Defensa oral / componente oral</mat-label><input matInput type="number" min="0" max="10" formControlName="notaDefensaOral" /></mat-form-field>
        <mat-form-field><mat-label>Examen complexivo</mat-label><input matInput type="number" min="0" max="10" formControlName="notaExamenComplexivo" /></mat-form-field>
        <mat-form-field><mat-label>Observaciones</mat-label><textarea matInput formControlName="observacion"></textarea></mat-form-field>
        <mat-checkbox formControlName="cerrarCalificacion">Cerrar calificación</mat-checkbox>
      </form>
      <app-consolidado-notas [consolidado]="preview()" />
    </mat-dialog-content>
    <mat-dialog-actions align="end"><button mat-button mat-dialog-close>Cancelar</button><button mat-flat-button color="primary" [disabled]="form.invalid" (click)="save()">Guardar</button></mat-dialog-actions>
  `
})
export class ModalCalificarEvaluadorComponent {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(CalificacionesTitulacionService);
  private readonly ref = inject(MatDialogRef<ModalCalificarEvaluadorComponent>);
  form = this.fb.group({
    responsableTitulacionId: [null as number | null, Validators.required],
    evaluadorNumero: [1 as 1 | 2 | 3, Validators.required],
    notaTrabajoEscrito: [null as number | null, [Validators.min(0), Validators.max(10)]],
    notaDefensaOral: [null as number | null, [Validators.min(0), Validators.max(10)]],
    notaExamenComplexivo: [null as number | null, [Validators.min(0), Validators.max(10)]],
    observacion: [''],
    cerrarCalificacion: [true]
  });
  constructor(@Inject(MAT_DIALOG_DATA) public data: { grupo: GrupoTitulacion; estudiante: GrupoEstudiante }) {}
  preview(): CalificacionConsolidada {
    const v = this.form.value;
    const examen = v.notaExamenComplexivo == null ? null : Number(v.notaExamenComplexivo);
    const oral = v.notaDefensaOral == null ? null : Number(v.notaDefensaOral);
    const titulacion = examen != null
      ? (oral != null ? examen + oral : examen * 2)
      : Number(v.notaTrabajoEscrito || 0) + Number(v.notaDefensaOral || 0);
    return { calificacionConsolidadaId: 0, expedienteId: this.data.estudiante.expedienteId, numeroIdentificacion: this.data.estudiante.numeroIdentificacion, notaTitulacionSobre20: titulacion, equivalenciaTitulacion20: +(titulacion * 0.1).toFixed(2), evaluadoresCompletos: false, aprobado: false };
  }
  save(): void {
    const request: RegistrarCalificacionEvaluadorRequest = {
      expedienteId: this.data.estudiante.expedienteId,
      grupoTitulacionId: this.data.grupo.grupoTitulacionId,
      ...(this.form.value as any)
    };
    this.service.registrarEvaluador(this.data.estudiante.expedienteId, request).subscribe(() => this.ref.close(true));
  }
}

@Component({
  selector: 'app-consolidado-notas',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <div class="consolidado" *ngIf="consolidado() as c">
      <span>Trabajo: {{ c.promedioTrabajoEscrito ?? 'N/D' }}</span>
      <span>Oral/Examen: {{ c.promedioDefensaOral ?? c.promedioExamenComplexivo ?? 'N/D' }}</span>
      <span>Titulación /20: {{ c.notaTitulacionSobre20 ?? 'N/D' }}</span>
      <span>20%: {{ c.equivalenciaTitulacion20 ?? 'N/D' }}</span>
      <span>80%: {{ c.equivalenciaAsignaturas80 ?? 'N/D' }}</span>
      <strong>Final: {{ c.notaFinalGrado ?? 'Preliminar' }}</strong>
    </div>
  `
})
export class ConsolidadoNotasComponent {
  consolidado = input<CalificacionConsolidada | null>(null);
}

@Component({
  selector: 'app-documentos-titulacion',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <section class="section-head"><div><h1>Documentos</h1><p>Carga, validación y observación de documentos obligatorios.</p></div></section>
    <form class="filters" [formGroup]="form" (ngSubmit)="upload()">
      <mat-form-field><mat-label>Expediente</mat-label><input matInput type="number" formControlName="expedienteId" /></mat-form-field>
      <mat-form-field><mat-label>Tipo documento</mat-label><mat-select formControlName="tipoDocumentoCodigo"><mat-option *ngFor="let t of tipos" [value]="t">{{ t }}</mat-option></mat-select></mat-form-field>
      <mat-form-field><mat-label>Ruta nube manual</mat-label><input matInput formControlName="rutaNubeManual" /></mat-form-field>
      <mat-form-field><mat-label>Observación</mat-label><input matInput formControlName="observacion" /></mat-form-field>
      <mat-checkbox formControlName="esFirmadoElectronicamente">Firmado electrónicamente</mat-checkbox>
      <input type="file" accept=".pdf,.xlsx,.doc,.docx" (change)="pick($event)" />
      <button mat-flat-button color="primary" type="submit" [disabled]="form.invalid">Cargar</button>
      <button mat-stroked-button type="button" (click)="load()">Consultar</button>
    </form>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Tipo</th><th>Versión</th><th>Archivo</th><th>Estado</th><th>Usuario</th><th>Fecha</th><th>Ruta</th><th></th></tr></thead>
      <tbody><tr *ngFor="let d of items">
        <td>{{ d.tipoDocumentoCodigo }}</td>
        <td>{{ d.version || 1 }}</td>
        <td>{{ d.nombreArchivo }}</td>
        <td><span class="status" [class]="estado(d.estadoCodigo)">{{ d.estadoCodigo }}</span></td>
        <td>{{ d.usuarioCarga || 'N/D' }}</td>
        <td>{{ d.fechaCarga | date:'short' }}</td>
        <td>{{ d.urlPublica || d.rutaNube }}</td>
        <td class="row-actions">
          <button mat-icon-button matTooltip="Historial" (click)="historial(d)"><mat-icon>history</mat-icon></button>
          <button mat-icon-button matTooltip="Validar" (click)="validar(d)"><mat-icon>check_circle</mat-icon></button>
          <button mat-icon-button matTooltip="Observar" (click)="observar(d)"><mat-icon>rate_review</mat-icon></button>
        </td>
      </tr></tbody>
    </table></div>
  `
})
export class DocumentosTitulacionComponent {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(DocumentosTitulacionService);
  estado = estadoVisual;
  file?: File;
  items: DocumentoTitulacion[] = [];
  tipos = ['APTITUD_LEGAL', 'PROGRAMACION_EXAMEN', 'EVIDENCIA_EXAMEN_COMPLEXIVO', 'RUBRICA_EVALUADORES', 'RUBRICA_TRABAJO_ESCRITO', 'RUBRICA_DEFENSA_ORAL', 'TRABAJO_FINAL_GRADO', 'ACTA_DEFENSA', 'ACTA_GRADO', 'ACTA_GRADO_FIRMADA', 'CERTIFICADO_PRACTICAS', 'CERTIFICADO_VINCULACION'];
  form = this.fb.group({
    expedienteId: [null as number | null, Validators.required],
    tipoDocumentoCodigo: ['APTITUD_LEGAL', Validators.required],
    rutaNubeManual: [''],
    observacion: [''],
    esFirmadoElectronicamente: [false]
  });
  pick(event: Event): void { this.file = (event.target as HTMLInputElement).files?.[0]; }
  upload(): void {
    if (!this.file && !this.form.value.rutaNubeManual) {
      alert('Carga un archivo o indica una ruta en nube.');
      return;
    }
    const data = new FormData();
    data.append('expedienteId', String(this.form.value.expedienteId));
    data.append('tipoDocumentoCodigo', this.form.value.tipoDocumentoCodigo!);
    data.append('esFirmadoElectronicamente', String(!!this.form.value.esFirmadoElectronicamente));
    this.appendIfPresent(data, 'rutaNubeManual', this.form.value.rutaNubeManual);
    this.appendIfPresent(data, 'observacion', this.form.value.observacion);
    if (this.file) data.append('archivo', this.file);
    this.service.upload(data).subscribe(() => this.load());
  }
  load(): void {
    if (!this.form.value.expedienteId) return;
    this.service.getByExpediente(this.form.value.expedienteId).subscribe((items) => (this.items = items));
  }
  validar(d: DocumentoTitulacion): void { this.service.validar(d.documentoId).subscribe(() => this.load()); }
  observar(d: DocumentoTitulacion): void {
    const observacion = prompt('Observación');
    if (observacion) this.service.observar(d.documentoId, observacion).subscribe(() => this.load());
  }
  historial(d: DocumentoTitulacion): void {
    this.service.getHistorial(d.documentoId).subscribe((items) => {
      alert(this.formatHistorial(items));
    });
  }
  private appendIfPresent(data: FormData, key: string, value?: string | null): void {
    if (value) data.append(key, value);
  }
  private formatHistorial(items: DocumentoTitulacionHistorial[]): string {
    if (!items.length) return 'Este documento no tiene historial registrado.';
    return items
      .map((h) => `${new Date(h.fechaAccion).toLocaleString()} · ${h.accion} · v${h.version || 1} · ${h.estadoCodigo || 'N/D'} · ${h.usuarioAccion}${h.observacion ? ` · ${h.observacion}` : ''}`)
      .join('\n');
  }
}

@Component({
  selector: 'app-titulos-portal',
  standalone: true,
  imports: [
    forwardRef(() => UploadTituloRegistroComponent),
    forwardRef(() => UploadTituloIntecComponent),
    forwardRef(() => TitulosTableComponent),
    ...COMMON_IMPORTS
  ],
  template: `
    <section class="section-head"><div><h1>Portal de títulos</h1><p>Títulos registrados/SENESCYT y títulos INTEC.</p></div></section>
    <form class="filters" [formGroup]="filters" (ngSubmit)="load()">
      <mat-form-field><mat-label>Buscar</mat-label><input matInput formControlName="search" placeholder="Cédula, estudiante, carrera o acta" /></mat-form-field>
      <button mat-stroked-button type="submit"><mat-icon>search</mat-icon>Buscar</button>
      <button mat-button type="button" (click)="limpiar()">Limpiar</button>
    </form>
    <mat-tab-group>
      <mat-tab label="Registrados / SENESCYT"><app-upload-titulo-registro (uploaded)="load()" /><app-titulos-table [items]="registrados" /></mat-tab>
      <mat-tab label="Títulos INTEC"><app-upload-titulo-intec (uploaded)="load()" /><app-titulos-table [items]="intec" /></mat-tab>
    </mat-tab-group>
  `
})
export class TitulosPortalComponent implements OnInit {
  private readonly service = inject(TitulosTitulacionService);
  private readonly fb = inject(FormBuilder);
  filters = this.fb.group({ search: [''] });
  registrados: TituloTitulacion[] = [];
  intec: TituloTitulacion[] = [];
  ngOnInit(): void { this.load(); }
  load(): void {
    this.service.get(this.filters.value.search || undefined).subscribe((items) => {
      this.registrados = items.filter((i) => i.tipoDocumentoCodigo === 'TITULO_REGISTRO_SENESCYT');
      this.intec = items.filter((i) => i.tipoDocumentoCodigo === 'TITULO_INTEC');
    });
  }
  limpiar(): void {
    this.filters.reset({ search: '' });
    this.load();
  }
}

@Component({
  selector: 'app-titulos-table',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `<div class="table-wrap"><table class="data-table"><thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Acta</th><th>Registro</th><th>Emisión</th><th>Versión</th><th>Archivo</th><th>Estado</th><th>Observación</th><th>URL</th></tr></thead><tbody><tr *ngFor="let t of items()"><td>{{ t.nombresEstudiante }}</td><td>{{ t.numeroIdentificacion }}</td><td>{{ t.carrera }}</td><td>{{ t.numeroActaGrado || t.numeroActa || 'N/D' }}</td><td>{{ t.codigoRegistroSenescyt || t.numeroTituloIntec || 'N/D' }}</td><td>{{ t.fechaRegistroSenescyt || t.fechaEmisionTitulo || 'N/D' }}</td><td>{{ t.version || 1 }}</td><td>{{ t.nombreArchivo }}</td><td><span class="status" [class]="estado(t.estadoCodigo)">{{ t.estadoCodigo }}</span></td><td>{{ t.observacion || '' }}</td><td>{{ t.urlPublica || t.rutaNube }}</td></tr></tbody></table></div>`
})
export class TitulosTableComponent {
  items = input<TituloTitulacion[]>([]);
  estado = estadoVisual;
}

@Component({
  selector: 'app-upload-titulo-registro',
  standalone: true,
  imports: [forwardRef(() => UploadTituloBaseComponent), ...COMMON_IMPORTS],
  template: `<app-upload-titulo-base tipo="registro" (uploaded)="uploaded.emit()" />`
})
export class UploadTituloRegistroComponent {
  @Output() uploaded = new EventEmitter<void>();
}

@Component({
  selector: 'app-upload-titulo-intec',
  standalone: true,
  imports: [forwardRef(() => UploadTituloBaseComponent), ...COMMON_IMPORTS],
  template: `<app-upload-titulo-base tipo="intec" (uploaded)="uploaded.emit()" />`
})
export class UploadTituloIntecComponent {
  @Output() uploaded = new EventEmitter<void>();
}

@Component({
  selector: 'app-upload-titulo-base',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <form class="filters" [formGroup]="form" (ngSubmit)="upload()">
      <mat-form-field><mat-label>Expediente</mat-label><input matInput type="number" formControlName="expedienteId" /></mat-form-field>
      <mat-form-field><mat-label>Cédula</mat-label><input matInput formControlName="cedula" /></mat-form-field>
      <mat-form-field *ngIf="tipo() === 'registro'"><mat-label>Código registro SENESCYT</mat-label><input matInput formControlName="codigoRegistroSenescyt" /></mat-form-field>
      <mat-form-field *ngIf="tipo() === 'registro'"><mat-label>Fecha registro SENESCYT</mat-label><input matInput type="date" formControlName="fechaRegistroSenescyt" /></mat-form-field>
      <mat-form-field *ngIf="tipo() === 'intec'"><mat-label>Número título INTEC</mat-label><input matInput formControlName="numeroTituloIntec" /></mat-form-field>
      <mat-form-field *ngIf="tipo() === 'intec'"><mat-label>Fecha emisión título</mat-label><input matInput type="date" formControlName="fechaEmisionTitulo" /></mat-form-field>
      <mat-form-field *ngIf="tipo() === 'intec'"><mat-label>Código QR/verificación</mat-label><input matInput formControlName="codigoVerificacionQr" /></mat-form-field>
      <mat-form-field><mat-label>Ruta nube manual</mat-label><input matInput formControlName="rutaNubeManual" /></mat-form-field>
      <mat-form-field><mat-label>Observación</mat-label><input matInput formControlName="observacion" /></mat-form-field>
      <input type="file" accept=".pdf" (change)="pick($event)" />
      <button mat-flat-button color="primary" type="submit" [disabled]="form.invalid">Cargar título</button>
    </form>
  `
})
export class UploadTituloBaseComponent {
  tipo = input<'registro' | 'intec'>('registro');
  @Output() uploaded = new EventEmitter<void>();
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(TitulosTitulacionService);
  file?: File;
  form = this.fb.group({
    expedienteId: [null as number | null, Validators.required],
    cedula: [''],
    codigoRegistroSenescyt: [''],
    fechaRegistroSenescyt: [''],
    numeroTituloIntec: [''],
    fechaEmisionTitulo: [''],
    codigoVerificacionQr: [''],
    rutaNubeManual: [''],
    observacion: ['']
  });
  pick(event: Event): void { this.file = (event.target as HTMLInputElement).files?.[0]; }
  upload(): void {
    if (!this.validarMetadatos()) return;
    if (!this.file && !this.form.value.rutaNubeManual) {
      alert('Carga el PDF del título o indica una ruta en nube.');
      return;
    }
    const data = new FormData();
    data.append('expedienteId', String(this.form.value.expedienteId));
    data.append('cedula', this.form.value.cedula || '');
    data.append('tipoDocumentoCodigo', this.tipo() === 'registro' ? 'TITULO_REGISTRO_SENESCYT' : 'TITULO_INTEC');
    this.appendIfPresent(data, 'codigoRegistroSenescyt', this.form.value.codigoRegistroSenescyt);
    this.appendIfPresent(data, 'fechaRegistroSenescyt', this.form.value.fechaRegistroSenescyt);
    this.appendIfPresent(data, 'numeroTituloIntec', this.form.value.numeroTituloIntec);
    this.appendIfPresent(data, 'fechaEmisionTitulo', this.form.value.fechaEmisionTitulo);
    this.appendIfPresent(data, 'codigoVerificacionQr', this.form.value.codigoVerificacionQr);
    this.appendIfPresent(data, 'rutaNubeManual', this.form.value.rutaNubeManual);
    this.appendIfPresent(data, 'observacion', this.form.value.observacion);
    if (this.file) data.append('archivo', this.file);
    const call = this.tipo() === 'registro' ? this.service.uploadRegistro(data) : this.service.uploadIntec(data);
    call.subscribe(() => this.uploaded.emit());
  }
  private validarMetadatos(): boolean {
    const v = this.form.value;
    if (this.tipo() === 'registro' && (!v.codigoRegistroSenescyt || !v.fechaRegistroSenescyt)) {
      alert('Indica el código y fecha de registro SENESCYT.');
      return false;
    }
    if (this.tipo() === 'intec' && (!v.numeroTituloIntec || !v.fechaEmisionTitulo)) {
      alert('Indica el número y fecha de emisión del título INTEC.');
      return false;
    }
    return true;
  }
  private appendIfPresent(data: FormData, key: string, value?: string | null): void {
    if (value) data.append(key, value);
  }
}

@Component({
  selector: 'app-actas-grado',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <section class="section-head"><div><h1>Actas de grado</h1><p>Generación, descarga y control de actas individuales.</p></div><button mat-flat-button color="primary" (click)="generar()">Generar acta</button></section>
    <input #actaFirmadaInput type="file" accept=".pdf" hidden (change)="subirFirmada($event)" />
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Número</th><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Mecanismo</th><th>Nota</th><th>Fecha</th><th>Estado</th><th>Texto</th><th>Acciones</th></tr></thead>
      <tbody><tr *ngFor="let a of items">
        <td>{{ a.numeroActa }}</td>
        <td>{{ a.nombresEstudiante }}</td>
        <td>{{ a.numeroIdentificacion }}</td>
        <td>{{ a.carrera }}</td>
        <td>{{ a.mecanismoCodigo }}</td>
        <td>{{ a.notaFinalGrado }}</td>
        <td>{{ a.fechaActa }}</td>
        <td><span class="status" [class]="estado(a.estadoCodigo)">{{ a.activo === false ? 'ANULADA' : a.estadoCodigo }}</span></td>
        <td>{{ a.textoVariableActa || '' }}</td>
        <td class="row-actions">
          <button mat-icon-button matTooltip="Descargar PDF" (click)="pdf(a)"><mat-icon>download</mat-icon></button>
          <button mat-icon-button matTooltip="Subir acta firmada" [disabled]="a.activo === false" (click)="seleccionarFirmada(a, actaFirmadaInput)"><mat-icon>upload_file</mat-icon></button>
          <button mat-icon-button matTooltip="Anular" [disabled]="a.activo === false" (click)="anular(a)"><mat-icon>block</mat-icon></button>
        </td>
      </tr></tbody>
    </table></div>
  `
})
export class ActasGradoComponent implements OnInit {
  private readonly service = inject(ActasGradoService);
  private readonly documentos = inject(DocumentosTitulacionService);
  private readonly dialog = inject(MatDialog);
  items: ActaGrado[] = [];
  actaParaFirma?: ActaGrado;
  estado = estadoVisual;
  ngOnInit(): void { this.load(); }
  load(): void { this.service.get().subscribe((items) => (this.items = items)); }
  generar(): void { this.dialog.open(ModalGenerarActaComponent, { width: '620px' }).afterClosed().subscribe((ok) => ok && this.load()); }
  pdf(a: ActaGrado): void { this.service.descargarPdf(a.actaGradoId).subscribe((blob) => downloadBlob(blob, `${a.numeroActa}.pdf`)); }
  seleccionarFirmada(a: ActaGrado, input: HTMLInputElement): void {
    this.actaParaFirma = a;
    input.value = '';
    input.click();
  }
  subirFirmada(event: Event): void {
    const archivo = (event.target as HTMLInputElement).files?.[0];
    if (!archivo || !this.actaParaFirma) return;
    const data = new FormData();
    data.append('expedienteId', String(this.actaParaFirma.expedienteId));
    data.append('tipoDocumentoCodigo', 'ACTA_GRADO_FIRMADA');
    data.append('archivo', archivo);
    data.append('esFirmadoElectronicamente', 'true');
    data.append('observacion', `Acta firmada ${this.actaParaFirma.numeroActa}`);
    this.documentos.upload(data).subscribe(() => {
      this.actaParaFirma = undefined;
      this.load();
    });
  }
  anular(a: ActaGrado): void {
    const motivo = prompt(`Motivo de anulación del acta ${a.numeroActa}`);
    if (!motivo) return;
    this.service.anular(a.actaGradoId, motivo).subscribe(() => this.load());
  }
}

@Component({
  selector: 'app-modal-generar-acta',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <h2 mat-dialog-title>Generar acta</h2>
    <mat-dialog-content><form class="dialog-form" [formGroup]="form">
      <mat-form-field><mat-label>Expediente</mat-label><input matInput type="number" formControlName="expedienteId" /></mat-form-field>
      <mat-form-field><mat-label>Número acta</mat-label><input matInput formControlName="numeroActa" /></mat-form-field>
      <mat-form-field><mat-label>Fecha</mat-label><input matInput type="date" formControlName="fechaActa" /></mat-form-field>
      <mat-form-field><mat-label>Hora</mat-label><input matInput type="time" formControlName="horaActa" /></mat-form-field>
      <mat-form-field><mat-label>Ciudad</mat-label><input matInput formControlName="ciudad" /></mat-form-field>
      <mat-form-field><mat-label>Institución</mat-label><input matInput formControlName="nombreInstitucion" /></mat-form-field>
      <mat-form-field><mat-label>Escuela</mat-label><input matInput formControlName="escuela" /></mat-form-field>
      <mat-form-field><mat-label>Autoridad académica</mat-label><input matInput formControlName="autoridadAcademica" /></mat-form-field>
    </form></mat-dialog-content>
    <mat-dialog-actions align="end"><button mat-button mat-dialog-close>Cancelar</button><button mat-flat-button color="primary" [disabled]="form.invalid" (click)="save()">Generar</button></mat-dialog-actions>
  `
})
export class ModalGenerarActaComponent {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(ActasGradoService);
  private readonly ref = inject(MatDialogRef<ModalGenerarActaComponent>);
  form = this.fb.group({
    expedienteId: [null as number | null, Validators.required],
    numeroActa: [''],
    fechaActa: [new Date().toISOString().slice(0, 10), Validators.required],
    horaActa: [''],
    ciudad: ['Quito', Validators.required],
    nombreInstitucion: ['Instituto Superior Tecnológico INTEC'],
    escuela: [''],
    autoridadAcademica: ['']
  });
  save(): void {
    if (!confirm('¿Generar acta individual para este expediente?')) return;
    const expedienteId = this.form.value.expedienteId!;
    const { expedienteId: _, ...request } = this.form.value as any;
    this.service.generar(expedienteId, request).subscribe(() => this.ref.close(true));
  }
}

@Component({
  selector: 'app-reportes-titulacion',
  standalone: true,
  imports: COMMON_IMPORTS,
  template: `
    <section class="section-head"><div><h1>Reportes</h1><p>Exportación operativa para seguimiento y auditoría.</p></div></section>
    <section class="report-grid">
      <button mat-stroked-button (click)="exportar('aptos')"><mat-icon>table_view</mat-icon>Exportar aptos CSV</button>
      <button mat-stroked-button (click)="exportar('grupos')"><mat-icon>table_view</mat-icon>Exportar grupos CSV</button>
      <button mat-stroked-button (click)="exportar('actas')"><mat-icon>picture_as_pdf</mat-icon>Generar reporte PDF</button>
    </section>
  `
})
export class ReportesTitulacionComponent {
  private readonly reportes = inject(ReportesTitulacionService);
  exportar(tipo: string): void {
    this.reportes.exportarCsv(`titulacion-${tipo}`, [{ reporte: tipo, generado: new Date().toISOString() }]);
  }
}
