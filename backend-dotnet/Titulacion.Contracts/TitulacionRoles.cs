namespace Titulacion.Contracts;

public static class TitulacionRoles
{
    public const string Admin = "ADMIN_TITULACION";
    public const string Secretaria = "SECRETARIA_TITULACION";
    public const string Coordinador = "COORDINADOR_ACADEMICO";
    public const string Evaluador = "EVALUADOR_TITULACION";
    public const string Autoridad = "AUTORIDAD_ACADEMICA";
    public const string Consulta = "CONSULTA_TITULACION";

    public const string Todos = $"{Admin},{Secretaria},{Coordinador},{Evaluador},{Autoridad},{Consulta}";
    public const string AdminOCoordinador = $"{Admin},{Coordinador}";
    public const string AdminOSecretaria = $"{Admin},{Secretaria}";
    public const string GestionDocumental = $"{Admin},{Secretaria},{Coordinador}";
    public const string ConsultaAcademica = $"{Admin},{Secretaria},{Coordinador},{Autoridad},{Consulta}";
    public const string GeneracionActas = $"{Admin},{Autoridad}";
}
