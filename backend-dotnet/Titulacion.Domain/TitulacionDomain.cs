namespace Titulacion.Domain;

public static class TitulacionErrorCodes
{
    public const string EstudianteNoApto = "ESTUDIANTE_NO_APTO";
    public const string ExpedienteDuplicado = "EXPEDIENTE_DUPLICADO";
    public const string MecanismoInvalido = "MECANISMO_INVALIDO";
    public const string DefensaMaximoDosEstudiantes = "DEFENSA_MAXIMO_DOS_ESTUDIANTES";
    public const string TribunalIncompleto = "TRIBUNAL_INCOMPLETO";
    public const string ResponsableComplexivoObligatorio = "RESPONSABLE_COMPLEXIVO_OBLIGATORIO";
    public const string FaltanTresEvaluadores = "FALTAN_TRES_EVALUADORES";
    public const string NotasIncompletas = "NOTAS_INCOMPLETAS";
    public const string DocumentosObligatoriosPendientes = "DOCUMENTOS_OBLIGATORIOS_PENDIENTES";
    public const string ActaYaGenerada = "ACTA_YA_GENERADA";
    public const string TituloRegistroRequiereActa = "TITULO_REGISTRO_REQUIERE_ACTA";
    public const string TituloIntecRequiereActa = "TITULO_INTEC_REQUIERE_ACTA";
    public const string TeamsConfigIncompleta = "TEAMS_CONFIG_INCOMPLETA";
    public const string TeamsEventoNoCreado = "TEAMS_EVENTO_NO_CREADO";
}

public static class MecanismosTitulacion
{
    public const string ExamenComplexivo = "EXAMEN_COMPLEXIVO";
    public const string DefensaGrado = "DEFENSA_GRADO";

    public static bool EsValido(string? codigo) =>
        string.Equals(codigo, ExamenComplexivo, StringComparison.OrdinalIgnoreCase)
        || string.Equals(codigo, DefensaGrado, StringComparison.OrdinalIgnoreCase);
}

public sealed class TitulacionException : Exception
{
    public TitulacionException(string code, string message, int statusCode = 400)
        : base(message)
    {
        Code = code;
        StatusCode = statusCode;
    }

    public string Code { get; }
    public int StatusCode { get; }
}

public sealed record ResultadoCalculoNotas(
    decimal EquivalenciaAsignaturas80,
    decimal NotaTitulacionSobre20,
    decimal EquivalenciaTitulacion20,
    decimal NotaFinal);

public static class CalculoNotasTitulacion
{
    public static ResultadoCalculoNotas CalcularDefensa(
        decimal notaAsignaturas,
        decimal promedioTrabajoEscrito,
        decimal promedioDefensaOral,
        decimal pesoAsignaturas = 0.80m,
        decimal pesoTitulacion = 0.20m)
    {
        ValidarNota10(notaAsignaturas, nameof(notaAsignaturas));
        ValidarNota10(promedioTrabajoEscrito, nameof(promedioTrabajoEscrito));
        ValidarNota10(promedioDefensaOral, nameof(promedioDefensaOral));

        var notaTitulacionSobre20 = Math.Round(promedioTrabajoEscrito + promedioDefensaOral, 2);
        return Calcular(notaAsignaturas, notaTitulacionSobre20, pesoAsignaturas, pesoTitulacion);
    }

    public static ResultadoCalculoNotas CalcularComplexivo(
        decimal notaAsignaturas,
        decimal promedioExamenComplexivo,
        decimal pesoAsignaturas = 0.80m,
        decimal pesoTitulacion = 0.20m)
    {
        return CalcularComplexivo(
            notaAsignaturas,
            promedioExamenComplexivo,
            promedioComponenteOral: null,
            pesoAsignaturas: pesoAsignaturas,
            pesoTitulacion: pesoTitulacion);
    }

    public static ResultadoCalculoNotas CalcularComplexivo(
        decimal notaAsignaturas,
        decimal promedioExamenComplexivo,
        decimal? promedioComponenteOral,
        decimal pesoAsignaturas = 0.80m,
        decimal pesoTitulacion = 0.20m)
    {
        ValidarNota10(notaAsignaturas, nameof(notaAsignaturas));
        ValidarNota10(promedioExamenComplexivo, nameof(promedioExamenComplexivo));
        if (promedioComponenteOral.HasValue)
        {
            ValidarNota10(promedioComponenteOral.Value, nameof(promedioComponenteOral));
        }

        var notaTitulacionSobre20 = promedioComponenteOral.HasValue
            ? Math.Round(promedioExamenComplexivo + promedioComponenteOral.Value, 2)
            : Math.Round(promedioExamenComplexivo * 2, 2);
        return Calcular(notaAsignaturas, notaTitulacionSobre20, pesoAsignaturas, pesoTitulacion);
    }

    private static ResultadoCalculoNotas Calcular(
        decimal notaAsignaturas,
        decimal notaTitulacionSobre20,
        decimal pesoAsignaturas,
        decimal pesoTitulacion)
    {
        var equivalencia80 = notaAsignaturas * pesoAsignaturas;
        var equivalencia20 = notaTitulacionSobre20 * (pesoTitulacion / 2);
        var notaFinal = Math.Round(equivalencia80 + equivalencia20, 2);

        return new ResultadoCalculoNotas(equivalencia80, notaTitulacionSobre20, equivalencia20, notaFinal);
    }

    private static void ValidarNota10(decimal nota, string campo)
    {
        if (nota < 0 || nota > 10)
        {
            throw new ArgumentOutOfRangeException(campo, "La nota debe estar entre 0 y 10.");
        }
    }
}
