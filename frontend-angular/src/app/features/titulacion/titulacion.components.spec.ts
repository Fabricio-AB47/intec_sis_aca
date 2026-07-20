import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import {
  DocumentosTitulacionComponent,
  UploadTituloBaseComponent
} from './titulacion.components';
import {
  DocumentosTitulacionService,
  TitulosTitulacionService
} from '../../services/titulacion-api.service';

describe('UploadTituloBaseComponent', () => {
  let fixture: ComponentFixture<UploadTituloBaseComponent>;
  let component: UploadTituloBaseComponent;
  let titulosService: jasmine.SpyObj<TitulosTitulacionService>;

  beforeEach(async () => {
    titulosService = jasmine.createSpyObj<TitulosTitulacionService>('TitulosTitulacionService', [
      'uploadRegistro',
      'uploadIntec'
    ]);
    titulosService.uploadRegistro.and.returnValue(of(documentoResponse('TITULO_REGISTRO_SENESCYT')));
    titulosService.uploadIntec.and.returnValue(of(documentoResponse('TITULO_INTEC')));

    await TestBed.configureTestingModule({
      imports: [UploadTituloBaseComponent],
      providers: [
        provideNoopAnimations(),
        { provide: TitulosTitulacionService, useValue: titulosService }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(UploadTituloBaseComponent);
    component = fixture.componentInstance;
    spyOn(window, 'alert');
  });

  it('bloquea titulo SENESCYT sin codigo y fecha de registro', () => {
    fixture.componentRef.setInput('tipo', 'registro');
    fixture.detectChanges();
    component.form.patchValue({ expedienteId: 20, rutaNubeManual: 'https://storage/titulo.pdf' });

    component.upload();

    expect(window.alert).toHaveBeenCalled();
    expect(titulosService.uploadRegistro).not.toHaveBeenCalled();
  });

  it('envia metadatos de titulo SENESCYT en FormData', () => {
    fixture.componentRef.setInput('tipo', 'registro');
    fixture.detectChanges();
    component.form.patchValue({
      expedienteId: 20,
      cedula: '0102030405',
      codigoRegistroSenescyt: 'SEN-2026-001',
      fechaRegistroSenescyt: '2026-07-07',
      rutaNubeManual: 'https://storage/titulo.pdf'
    });

    component.upload();

    const formData = titulosService.uploadRegistro.calls.mostRecent().args[0] as FormData;
    expect(formData.get('tipoDocumentoCodigo')).toBe('TITULO_REGISTRO_SENESCYT');
    expect(formData.get('codigoRegistroSenescyt')).toBe('SEN-2026-001');
    expect(formData.get('fechaRegistroSenescyt')).toBe('2026-07-07');
  });

  it('bloquea titulo INTEC sin numero y fecha de emision', () => {
    fixture.componentRef.setInput('tipo', 'intec');
    fixture.detectChanges();
    component.form.patchValue({ expedienteId: 20, rutaNubeManual: 'https://storage/titulo-intec.pdf' });

    component.upload();

    expect(window.alert).toHaveBeenCalled();
    expect(titulosService.uploadIntec).not.toHaveBeenCalled();
  });
});

describe('DocumentosTitulacionComponent', () => {
  let component: DocumentosTitulacionComponent;
  let documentosService: jasmine.SpyObj<DocumentosTitulacionService>;

  beforeEach(async () => {
    documentosService = jasmine.createSpyObj<DocumentosTitulacionService>('DocumentosTitulacionService', [
      'upload',
      'getByExpediente',
      'getHistorial',
      'validar',
      'observar'
    ]);
    documentosService.upload.and.returnValue(of(documentoResponse('ACTA_GRADO')));
    documentosService.getByExpediente.and.returnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [DocumentosTitulacionComponent],
      providers: [
        provideNoopAnimations(),
        { provide: DocumentosTitulacionService, useValue: documentosService }
      ]
    }).compileComponents();

    const fixture = TestBed.createComponent(DocumentosTitulacionComponent);
    component = fixture.componentInstance;
    spyOn(window, 'alert');
  });

  it('bloquea carga documental sin archivo ni ruta manual', () => {
    component.form.patchValue({ expedienteId: 20, tipoDocumentoCodigo: 'ACTA_GRADO' });

    component.upload();

    expect(window.alert).toHaveBeenCalled();
    expect(documentosService.upload).not.toHaveBeenCalled();
  });

  it('permite cargar documento con ruta nube manual', () => {
    component.form.patchValue({
      expedienteId: 20,
      tipoDocumentoCodigo: 'ACTA_GRADO',
      rutaNubeManual: 'https://storage/acta.pdf',
      observacion: 'Acta cargada'
    });

    component.upload();

    const formData = documentosService.upload.calls.mostRecent().args[0] as FormData;
    expect(formData.get('expedienteId')).toBe('20');
    expect(formData.get('tipoDocumentoCodigo')).toBe('ACTA_GRADO');
    expect(formData.get('rutaNubeManual')).toBe('https://storage/acta.pdf');
    expect(formData.get('observacion')).toBe('Acta cargada');
  });
});

function documentoResponse(tipoDocumentoCodigo: string) {
  return {
    documentoId: 1,
    expedienteId: 20,
    tipoDocumentoCodigo,
    nombreArchivo: 'documento.pdf',
    estadoCodigo: 'CARGADO',
    esFirmadoElectronicamente: false
  } as any;
}
