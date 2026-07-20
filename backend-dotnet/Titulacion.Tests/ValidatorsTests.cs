using Titulacion.Application;
using Titulacion.Contracts;
using Titulacion.Domain;

namespace Titulacion.Tests;

public sealed class ValidatorsTests
{
    [Fact]
    public void Habilitacion_rechaza_mecanismo_invalido_y_horas_inconsistentes()
    {
        var validator = new HabilitarEstudianteRequestValidator();

        var result = validator.Validate(new HabilitarEstudianteRequest
        {
            Cedula = "0102030405",
            MecanismoCodigo = "OTRO",
            HoraInicio = new TimeOnly(10, 0),
            HoraFin = new TimeOnly(9, 0)
        });

        Assert.Contains(result.Errors, e => e.ErrorCode == TitulacionErrorCodes.MecanismoInvalido);
        Assert.Contains(result.Errors, e => e.PropertyName == nameof(HabilitarEstudianteRequest.HoraFin));
    }

    [Fact]
    public void Responsable_complexivo_exige_tres_evaluadores_si_se_envia_lista()
    {
        var validator = new AsignarResponsableComplexivoRequestValidator();

        var result = validator.Validate(new AsignarResponsableComplexivoRequest
        {
            GrupoTitulacionId = 1,
            ResponsableComplexivoId = 10,
            EvaluadoresIds = new List<long> { 11, 12 }
        });

        Assert.Contains(result.Errors, e => e.ErrorCode == TitulacionErrorCodes.FaltanTresEvaluadores);
    }

    [Fact]
    public void Tribunal_defensa_exige_tres_integrantes()
    {
        var validator = new AsignarTribunalDefensaRequestValidator();

        var result = validator.Validate(new AsignarTribunalDefensaRequest
        {
            GrupoTitulacionId = 1,
            PresidenteTribunalId = 10,
            Vocal1Id = 0,
            Vocal2Id = 12
        });

        Assert.Contains(result.Errors, e => e.PropertyName == nameof(AsignarTribunalDefensaRequest.Vocal1Id));
    }

    [Fact]
    public void Calificacion_rechaza_evaluador_fuera_de_rango_y_notas_vacias()
    {
        var validator = new RegistrarCalificacionEvaluadorRequestValidator();

        var result = validator.Validate(new RegistrarCalificacionEvaluadorRequest
        {
            ExpedienteId = 1,
            GrupoTitulacionId = 2,
            ResponsableTitulacionId = 3,
            EvaluadorNumero = 4
        });

        Assert.Contains(result.Errors, e => e.PropertyName == nameof(RegistrarCalificacionEvaluadorRequest.EvaluadorNumero));
        Assert.Contains(result.Errors, e => e.ErrorCode == TitulacionErrorCodes.NotasIncompletas);
    }

    [Fact]
    public void Titulo_registrado_exige_codigo_y_fecha_senescyt()
    {
        var validator = new UploadDocumentoTitulacionRequestValidator();

        var result = validator.Validate(new UploadDocumentoTitulacionRequest
        {
            ExpedienteId = 1,
            TipoDocumentoCodigo = "TITULO_REGISTRO_SENESCYT",
            RutaNubeManual = "https://storage/titulo.pdf"
        });

        Assert.Contains(result.Errors, e => e.PropertyName == nameof(UploadDocumentoTitulacionRequest.CodigoRegistroSenescyt));
        Assert.Contains(result.Errors, e => e.PropertyName == nameof(UploadDocumentoTitulacionRequest.FechaRegistroSenescyt));
    }

    [Fact]
    public void Titulo_intec_exige_numero_y_fecha_emision()
    {
        var validator = new UploadDocumentoTitulacionRequestValidator();

        var result = validator.Validate(new UploadDocumentoTitulacionRequest
        {
            ExpedienteId = 1,
            TipoDocumentoCodigo = "TITULO_INTEC",
            RutaNubeManual = "https://storage/titulo-intec.pdf"
        });

        Assert.Contains(result.Errors, e => e.PropertyName == nameof(UploadDocumentoTitulacionRequest.NumeroTituloIntec));
        Assert.Contains(result.Errors, e => e.PropertyName == nameof(UploadDocumentoTitulacionRequest.FechaEmisionTitulo));
    }
}
