using Microsoft.AspNetCore.Http;
using Titulacion.Application;
using Titulacion.Contracts;
using Titulacion.Domain;

namespace Titulacion.Tests;

public sealed class ServicesTests
{
    [Fact]
    public async Task Habilitacion_bloquea_estudiante_con_requisito_pendiente()
    {
        var repository = new FakeTitulacionRepository
        {
            EstudianteApto = new EstudianteAptoDto
            {
                Cedula = "0102030405",
                Nombres = "Ada Lovelace",
                Carrera = "Software",
                CodigoCarrera = "SW",
                Periodo = "2026A",
                PuedeHabilitar = false,
                MotivoNoApto = "Registra deuda financiera."
            }
        };
        var service = new HabilitacionTitulacionService(repository, new RecordingAuditoriaService());

        var ex = await Assert.ThrowsAsync<TitulacionException>(() => service.HabilitarAsync(
            new HabilitarEstudianteRequest { Cedula = "0102030405", MecanismoCodigo = "EXAMEN_COMPLEXIVO" },
            "admin",
            CancellationToken.None));

        Assert.Equal(TitulacionErrorCodes.EstudianteNoApto, ex.Code);
        Assert.False(repository.HabilitarFueLlamado);
    }

    [Fact]
    public async Task Habilitacion_permiste_solo_estudiante_apto_y_audita()
    {
        var repository = new FakeTitulacionRepository
        {
            EstudianteApto = new EstudianteAptoDto
            {
                Cedula = "0102030405",
                Nombres = "Ada Lovelace",
                Carrera = "Software",
                CodigoCarrera = "SW",
                Periodo = "2026A",
                PuedeHabilitar = true
            }
        };
        var auditoria = new RecordingAuditoriaService();
        var service = new HabilitacionTitulacionService(repository, auditoria);

        var result = await service.HabilitarAsync(
            new HabilitarEstudianteRequest { Cedula = "0102030405", MecanismoCodigo = "EXAMEN_COMPLEXIVO" },
            "admin",
            CancellationToken.None);

        Assert.True(repository.HabilitarFueLlamado);
        Assert.Equal(10, result.HabilitacionId);
        Assert.Contains(auditoria.Acciones, x => x.StartsWith("HABILITAR_ESTUDIANTE:", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Responsable_complexivo_bloquea_menos_de_tres_evaluadores()
    {
        var repository = new FakeTitulacionRepository();
        var service = new ResponsableTitulacionService(repository, new RecordingAuditoriaService());

        var ex = await Assert.ThrowsAsync<TitulacionException>(() => service.AsignarResponsableComplexivoAsync(
            1,
            new AsignarResponsableComplexivoRequest
            {
                GrupoTitulacionId = 1,
                ResponsableComplexivoId = 10,
                EvaluadoresIds = new List<long> { 11, 12 }
            },
            "coordinador",
            CancellationToken.None));

        Assert.Equal(TitulacionErrorCodes.FaltanTresEvaluadores, ex.Code);
        Assert.False(repository.AsignarComplexivoFueLlamado);
    }

    [Fact]
    public async Task Complexivo_teams_crea_evento_asigna_responsable_y_guarda_enlace()
    {
        var repository = new FakeTitulacionRepository();
        var auditoria = new RecordingAuditoriaService();
        var teams = new FakeTeamsCalendarService();
        var service = new GrupoTitulacionService(repository, auditoria, teams);

        var result = await service.CrearComplexivoConTeamsAsync(new CrearGrupoComplexivoTeamsRequest
        {
            CodigoGrupo = "CX-2026-01",
            Tema = "Examen complexivo de software",
            FechaProgramada = new DateOnly(2026, 7, 10),
            HoraInicio = new TimeOnly(9, 0),
            HoraFin = new TimeOnly(11, 0),
            ResponsableComplexivoId = 10,
            EvaluadoresIds = new List<long> { 11, 12, 13 },
            CorreosAsistentes = new List<string> { "responsable@intec.edu.ec" }
        }, "coordinador", CancellationToken.None);

        Assert.True(result.TeamsCreado);
        Assert.Equal("https://teams.microsoft.com/l/meetup-join/qa", result.TeamsJoinUrl);
        Assert.Equal(result.TeamsJoinUrl, repository.UltimaProgramacionRequest?.AulaOLink);
        Assert.Equal("VIRTUAL", repository.UltimaProgramacionRequest?.Modalidad);
        Assert.True(repository.AsignarComplexivoFueLlamado);
        Assert.Equal(10, repository.UltimaAsignacionComplexivoRequest?.ResponsableComplexivoId);
        Assert.Equal(3, repository.UltimaAsignacionComplexivoRequest?.EvaluadoresIds.Count);
        Assert.Equal("responsable@intec.edu.ec", teams.LastRequest?.AttendeeEmails.Single());
        Assert.Contains(auditoria.Acciones, x => x.StartsWith("GUARDAR_ENLACE_TEAMS_COMPLEXIVO:", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Tribunal_defensa_bloquea_tribunal_incompleto()
    {
        var repository = new FakeTitulacionRepository();
        var service = new ResponsableTitulacionService(repository, new RecordingAuditoriaService());

        var ex = await Assert.ThrowsAsync<TitulacionException>(() => service.AsignarTribunalDefensaAsync(
            1,
            new AsignarTribunalDefensaRequest
            {
                GrupoTitulacionId = 1,
                PresidenteTribunalId = 10,
                Vocal1Id = 0,
                Vocal2Id = 12
            },
            "coordinador",
            CancellationToken.None));

        Assert.Equal(TitulacionErrorCodes.TribunalIncompleto, ex.Code);
        Assert.False(repository.AsignarTribunalFueLlamado);
    }

    [Fact]
    public async Task Calificacion_bloquea_ruta_de_expediente_inconsistente()
    {
        var service = new CalificacionTitulacionService(new FakeTitulacionRepository(), new RecordingAuditoriaService());

        var ex = await Assert.ThrowsAsync<TitulacionException>(() => service.RegistrarEvaluadorAsync(
            1,
            new RegistrarCalificacionEvaluadorRequest
            {
                ExpedienteId = 2,
                GrupoTitulacionId = 1,
                ResponsableTitulacionId = 3,
                EvaluadorNumero = 1,
                NotaExamenComplexivo = 9
            },
            "evaluador",
            CancellationToken.None));

        Assert.Equal("EXPEDIENTE_INCONSISTENTE", ex.Code);
    }

    [Fact]
    public async Task Calificacion_reabrir_actualiza_repositorio_y_audita()
    {
        var repository = new FakeTitulacionRepository();
        var auditoria = new RecordingAuditoriaService();
        var service = new CalificacionTitulacionService(repository, auditoria);

        await service.ReabrirAsync(33, "coordinador", CancellationToken.None);

        Assert.Equal(33, repository.CalificacionReabiertaId);
        Assert.Contains(auditoria.Acciones, x => x.StartsWith("REABRIR_CALIFICACION:", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Documento_upload_guarda_archivo_y_registra_auditoria()
    {
        var repository = new FakeTitulacionRepository();
        var storage = new MemoryStorageService();
        var auditoria = new RecordingAuditoriaService();
        var service = new DocumentoTitulacionService(repository, storage, auditoria);

        var file = FormFile("acta.pdf", "application/pdf", "%PDF QA");
        var result = await service.UploadAsync(
            new UploadDocumentoTitulacionRequest
            {
                ExpedienteId = 20,
                TipoDocumentoCodigo = "ACTA_GRADO",
                Archivo = file
            },
            "secretaria",
            CancellationToken.None);

        Assert.Single(storage.SavedFiles);
        Assert.Equal("ACTA_GRADO", repository.UltimoDocumentoRequest?.TipoDocumentoCodigo);
        Assert.Equal("acta.pdf", result.NombreArchivo);
        Assert.Contains(auditoria.Acciones, x => x.StartsWith("CARGAR_DOCUMENTO:", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Titulo_service_fija_tipo_de_documento_registrado()
    {
        var repository = new FakeTitulacionRepository();
        var service = new TituloService(repository, new MemoryStorageService(), new RecordingAuditoriaService());

        await service.UploadTituloRegistradoAsync(
            new UploadDocumentoTitulacionRequest
            {
                ExpedienteId = 20,
                RutaNubeManual = "https://storage/titulo.pdf",
                CodigoRegistroSenescyt = "SEN-2026-001",
                FechaRegistroSenescyt = new DateOnly(2026, 7, 7)
            },
            "secretaria",
            CancellationToken.None);

        Assert.Equal("TITULO_REGISTRO_SENESCYT", repository.UltimoDocumentoRequest?.TipoDocumentoCodigo);
    }

    [Fact]
    public async Task Acta_service_genera_numero_si_no_viene_en_request_y_guarda_pdf()
    {
        var repository = new FakeTitulacionRepository();
        var storage = new MemoryStorageService();
        var pdf = new StaticPdfActaService();
        var service = new ActaGradoService(repository, storage, pdf, new RecordingAuditoriaService());

        var result = await service.GenerarAsync(
            20,
            new GenerarActaGradoRequest
            {
                FechaActa = new DateOnly(2026, 7, 7),
                Ciudad = "Quito",
                NombreInstitucion = "Instituto Superior Tecnologico INTEC"
            },
            "autoridad",
            CancellationToken.None);

        Assert.Equal(repository.NumeroActaGenerado, repository.UltimaActaRequest?.NumeroActa);
        Assert.Equal(repository.NumeroActaGenerado, pdf.LastDto?.NumeroActa);
        Assert.Single(storage.SavedFiles);
        Assert.Equal(7, result.ActaGradoId);
    }

    [Fact]
    public async Task Acta_firmada_se_carga_como_documento_firmado_del_expediente()
    {
        var repository = new FakeTitulacionRepository();
        var service = new ActaGradoService(repository, new MemoryStorageService(), new StaticPdfActaService(), new RecordingAuditoriaService());

        var result = await service.UploadFirmadaAsync(
            7,
            new UploadDocumentoTitulacionRequest
            {
                Archivo = FormFile("acta-firmada.pdf", "application/pdf", "%PDF firmada")
            },
            "secretaria",
            CancellationToken.None);

        Assert.Equal("ACTA_GRADO_FIRMADA", repository.UltimoDocumentoRequest?.TipoDocumentoCodigo);
        Assert.Equal(20, repository.UltimoDocumentoRequest?.ExpedienteId);
        Assert.Equal("0102030405", repository.UltimoDocumentoRequest?.Cedula);
        Assert.True(repository.UltimoDocumentoRequest?.EsFirmadoElectronicamente);
        Assert.Equal("acta-firmada.pdf", result.NombreArchivo);
    }

    private static IFormFile FormFile(string fileName, string contentType, string content)
    {
        return new TestFormFile(fileName, contentType, System.Text.Encoding.UTF8.GetBytes(content));
    }

    private sealed class TestFormFile : IFormFile
    {
        private readonly byte[] _content;

        public TestFormFile(string fileName, string contentType, byte[] content)
        {
            FileName = fileName;
            ContentType = contentType;
            _content = content;
        }

        public string ContentType { get; }
        public string ContentDisposition => string.Empty;
        public IHeaderDictionary Headers => null!;
        public long Length => _content.Length;
        public string Name => "archivo";
        public string FileName { get; }

        public void CopyTo(Stream target) => OpenReadStream().CopyTo(target);

        public Task CopyToAsync(Stream target, CancellationToken cancellationToken = default) =>
            OpenReadStream().CopyToAsync(target, cancellationToken);

        public Stream OpenReadStream() => new MemoryStream(_content, writable: false);
    }
}
