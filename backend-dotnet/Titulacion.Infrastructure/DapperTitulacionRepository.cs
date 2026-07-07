using Dapper;
using System.Data;
using Titulacion.Application;
using Titulacion.Contracts;
using Titulacion.Domain;

namespace Titulacion.Infrastructure;

public sealed class DapperTitulacionRepository(ISqlConnectionFactory connectionFactory) : ITitulacionRepository
{
    public async Task<DashboardResumenDto> GetDashboardAsync(CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT
                (SELECT COUNT(1) FROM rpt.vw_EstudiantesCumplenRequisitosTitulacion) AS EstudiantesAptos,
                (SELECT COUNT(1) FROM tit.HabilitacionTitulacion WHERE EstadoCodigo <> 'ANULADO') AS EstudiantesHabilitados,
                (SELECT COUNT(1) FROM rpt.vw_GruposComplexivo WHERE FechaProgramada IS NOT NULL) AS ExamenesComplexivosProgramados,
                (SELECT COUNT(1) FROM rpt.vw_DefensasGrado WHERE FechaProgramada IS NOT NULL) AS DefensasProgramadas,
                (SELECT COUNT(1) FROM rpt.vw_ActasGeneradas WHERE EstadoCodigo <> 'ANULADO') AS ActasGeneradas,
                (SELECT COUNT(1) FROM rpt.vw_TitulosCargados WHERE TipoDocumentoCodigo = 'TITULO_REGISTRO_SENESCYT') AS TitulosRegistradosCargados,
                (SELECT COUNT(1) FROM rpt.vw_TitulosCargados WHERE TipoDocumentoCodigo = 'TITULO_INTEC') AS TitulosIntecCargados,
                (SELECT COUNT(DISTINCT E.ExpedienteId)
                   FROM tit.ExpedienteTitulacion E
                  WHERE NOT EXISTS (
                        SELECT 1
                        FROM cat.TipoDocumentoTitulacion TD
                        WHERE TD.Activo = 1
                          AND TD.EsObligatorio = 1
                          AND TD.Codigo NOT IN ('TITULO_REGISTRO_SENESCYT', 'TITULO_INTEC')
                          AND (TD.AplicaMecanismoCodigo IS NULL OR TD.AplicaMecanismoCodigo = E.MecanismoTitulacionId)
                          AND NOT EXISTS (
                              SELECT 1 FROM doc.DocumentoTitulacion D
                              WHERE D.ExpedienteId = E.ExpedienteId
                                AND D.TipoDocumentoCodigo = TD.Codigo
                                AND D.EstadoCodigo <> 'ANULADO'))) AS ExpedientesConDocumentosPendientes,
                (SELECT COUNT(1) FROM rpt.vw_CalificacionesPendientes) AS CalificacionesPendientes;
            """;

        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QuerySingleAsync<DashboardResumenDto>(new CommandDefinition(sql, cancellationToken: cancellationToken));
    }

    public async Task<PagedResult<EstudianteAptoDto>> GetEstudiantesAptosAsync(EstudianteAptoFiltro filtro, CancellationToken cancellationToken)
    {
        var parameters = new DynamicParameters();
        var where = BuildEstudiantesWhere(filtro, parameters);
        var offset = Math.Max(0, filtro.Page - 1) * filtro.PageSize;
        parameters.Add("Offset", offset);
        parameters.Add("PageSize", filtro.PageSize);

        var sql = $"""
            {EstudiantesBaseSql}
            WHERE {where}
            ORDER BY Nombres, Cedula
            OFFSET @Offset ROWS FETCH NEXT @PageSize ROWS ONLY;

            SELECT COUNT(1)
            FROM tit.ExpedienteTitulacion E
            LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
            WHERE {where};
            """;

        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        using var grid = await connection.QueryMultipleAsync(new CommandDefinition(sql, parameters, cancellationToken: cancellationToken));
        var items = (await grid.ReadAsync<EstudianteAptoDto>()).ToList();
        var total = await grid.ReadSingleAsync<int>();
        return new PagedResult<EstudianteAptoDto> { Items = items, Total = total, Page = filtro.Page, PageSize = filtro.PageSize };
    }

    public async Task<EstudianteAptoDto?> GetEstudianteAptoByCedulaAsync(string cedula, CancellationToken cancellationToken)
    {
        var filtro = new EstudianteAptoFiltro { Cedula = cedula, PageSize = 1 };
        var result = await GetEstudiantesAptosAsync(filtro, cancellationToken);
        return result.Items.FirstOrDefault();
    }

    public async Task<SincronizacionEstudiantesDto> SincronizarEstudiantesAsync(CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT
                (SELECT COUNT(1) FROM rpt.vw_EstudiantesCumplenRequisitosTitulacion) AS EstudiantesAptos,
                (SELECT COUNT(1) FROM rpt.vw_EstudiantesPendientesRequisitosTitulacion) AS EstudiantesPendientes,
                CAST(N'Sincronizacion logica ejecutada sobre vistas y expedientes existentes.' AS nvarchar(300)) AS Mensaje;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QuerySingleAsync<SincronizacionEstudiantesDto>(new CommandDefinition(sql, cancellationToken: cancellationToken));
    }

    public async Task<HabilitacionDto> HabilitarEstudianteAsync(HabilitarEstudianteRequest request, string usuario, CancellationToken cancellationToken)
    {
        var parameters = new DynamicParameters();
        parameters.Add("NumeroIdentificacion", request.Cedula);
        parameters.Add("MecanismoCodigo", request.MecanismoCodigo);
        parameters.Add("Tema", request.Tema ?? request.Observacion);
        parameters.Add("FechaProgramada", ToDateTime(request.FechaProgramada));
        parameters.Add("HoraInicio", ToTimeSpan(request.HoraInicio));
        parameters.Add("HoraFin", ToTimeSpan(request.HoraFin));
        parameters.Add("Modalidad", request.Modalidad);
        parameters.Add("Usuario", usuario);

        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition("tit.sp_HabilitarEstudianteTitulacion", parameters, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
        return await connection.QuerySingleAsync<HabilitacionDto>(new CommandDefinition("""
            SELECT TOP (1)
                HabilitacionId, ExpedienteId, NumeroIdentificacion, CodigoEstud, Carrera, CodigoCarrera,
                CodigoPeriodo, MecanismoCodigo, EstadoCodigo, FechaHabilitacion, UsuarioHabilitacion, Observacion
            FROM tit.HabilitacionTitulacion
            WHERE NumeroIdentificacion = @Cedula
            ORDER BY HabilitacionId DESC;
            """, new { request.Cedula }, cancellationToken: cancellationToken));
    }

    public async Task<IReadOnlyList<HabilitacionDto>> GetHabilitacionesAsync(CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT HabilitacionId, ExpedienteId, NumeroIdentificacion, CodigoEstud, Carrera, CodigoCarrera,
                   CodigoPeriodo, MecanismoCodigo, EstadoCodigo, FechaHabilitacion, UsuarioHabilitacion, Observacion
            FROM tit.HabilitacionTitulacion
            ORDER BY HabilitacionId DESC;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<HabilitacionDto>(new CommandDefinition(sql, cancellationToken: cancellationToken))).ToList();
    }

    public async Task<HabilitacionDto?> GetHabilitacionAsync(long id, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT HabilitacionId, ExpedienteId, NumeroIdentificacion, CodigoEstud, Carrera, CodigoCarrera,
                   CodigoPeriodo, MecanismoCodigo, EstadoCodigo, FechaHabilitacion, UsuarioHabilitacion, Observacion
            FROM tit.HabilitacionTitulacion
            WHERE HabilitacionId = @Id;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QueryFirstOrDefaultAsync<HabilitacionDto>(new CommandDefinition(sql, new { Id = id }, cancellationToken: cancellationToken));
    }

    public async Task AnularHabilitacionAsync(long id, string usuario, CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE tit.HabilitacionTitulacion
               SET EstadoCodigo = 'ANULADO',
                   Observacion = COALESCE(NULLIF(Observacion, ''), N'Anulado desde API')
             WHERE HabilitacionId = @Id;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition(sql, new { Id = id, Usuario = usuario }, cancellationToken: cancellationToken));
    }

    public async Task<GrupoTitulacionDto> CrearGrupoComplexivoAsync(CrearGrupoComplexivoRequest request, string usuario, CancellationToken cancellationToken)
    {
        var parameters = GrupoParameters(request, usuario);
        parameters.Add("GrupoTitulacionId", dbType: DbType.Int64, direction: ParameterDirection.Output);
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition("tit.sp_CrearGrupoComplexivo", parameters, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
        var id = parameters.Get<long>("GrupoTitulacionId");
        return await GetGrupoAsync(id, cancellationToken) ?? throw new TitulacionException("GRUPO_NO_ENCONTRADO", "No se pudo leer el grupo creado.", 500);
    }

    public async Task<GrupoTitulacionDto> CrearDefensaGradoAsync(CrearDefensaGradoRequest request, string usuario, CancellationToken cancellationToken)
    {
        var parameters = GrupoParameters(request, usuario);
        parameters.Add("ExpedienteId1", request.ExpedienteId1);
        parameters.Add("ExpedienteId2", request.ExpedienteId2);
        parameters.Add("GrupoTitulacionId", dbType: DbType.Int64, direction: ParameterDirection.Output);
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition("tit.sp_CrearDefensaGrado", parameters, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
        var id = parameters.Get<long>("GrupoTitulacionId");
        return await GetGrupoAsync(id, cancellationToken) ?? throw new TitulacionException("GRUPO_NO_ENCONTRADO", "No se pudo leer el grupo creado.", 500);
    }

    public async Task<IReadOnlyList<GrupoTitulacionDto>> GetGruposAsync(string? mecanismo, CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT * FROM (
                {GrupoSelectSql("rpt.vw_GruposComplexivo")}
                UNION ALL
                {GrupoSelectSql("rpt.vw_DefensasGrado")}
            ) G
            WHERE (@Mecanismo IS NULL OR G.MecanismoCodigo = @Mecanismo)
            ORDER BY G.GrupoTitulacionId DESC;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<GrupoTitulacionDto>(new CommandDefinition(sql, new { Mecanismo = mecanismo }, cancellationToken: cancellationToken))).ToList();
    }

    public async Task<GrupoTitulacionDto?> GetGrupoAsync(long id, CancellationToken cancellationToken)
    {
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await GetGrupoWithConnectionAsync(connection, id, cancellationToken);
    }

    public async Task AgregarEstudianteGrupoAsync(long grupoId, AgregarEstudianteGrupoRequest request, string usuario, CancellationToken cancellationToken)
    {
        const string sql = """
            DECLARE @ExpedienteId BIGINT = @RequestExpedienteId;
            IF @ExpedienteId IS NULL
            BEGIN
                SELECT TOP (1) @ExpedienteId = E.ExpedienteId
                FROM tit.ExpedienteTitulacion E
                LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
                WHERE COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion) = @Cedula
                ORDER BY E.ExpedienteId DESC;
            END;

            IF @ExpedienteId IS NULL THROW 59711, 'No existe expediente activo para el estudiante.', 1;
            IF EXISTS (SELECT 1 FROM tit.GrupoTitulacion WHERE GrupoTitulacionId = @GrupoId AND MecanismoCodigo = 'DEFENSA_GRADO')
               AND (SELECT COUNT(1) FROM tit.GrupoTitulacionEstudiante WHERE GrupoTitulacionId = @GrupoId AND Activo = 1) >= 2
                THROW 59702, 'La defensa de grado permite maximo 2 estudiantes.', 1;

            INSERT INTO tit.GrupoTitulacionEstudiante(GrupoTitulacionId, ExpedienteId, NumeroIdentificacion, CodigoEstud, OrdenIntegrante, EsPrincipal, EstadoCodigo)
            SELECT @GrupoId, E.ExpedienteId, COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion), COALESCE(E.CodigoEstud, ER.CodigoEstud),
                   COALESCE(@OrdenIntegrante, (SELECT COUNT(1) + 1 FROM tit.GrupoTitulacionEstudiante WHERE GrupoTitulacionId = @GrupoId)),
                   0, 'HABILITADO'
            FROM tit.ExpedienteTitulacion E
            LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
            WHERE E.ExpedienteId = @ExpedienteId;
            """;

        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition(sql, new
        {
            GrupoId = grupoId,
            RequestExpedienteId = request.ExpedienteId,
            request.Cedula,
            request.OrdenIntegrante,
            Usuario = usuario
        }, cancellationToken: cancellationToken));
    }

    public async Task EliminarEstudianteGrupoAsync(long grupoId, string cedula, string usuario, CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE tit.GrupoTitulacionEstudiante
               SET Activo = 0,
                   EstadoCodigo = 'ANULADO'
             WHERE GrupoTitulacionId = @GrupoId
               AND NumeroIdentificacion = @Cedula
               AND Activo = 1;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition(sql, new { GrupoId = grupoId, Cedula = cedula, Usuario = usuario }, cancellationToken: cancellationToken));
    }

    public async Task ActualizarProgramacionGrupoAsync(long grupoId, ActualizarProgramacionGrupoRequest request, string usuario, CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE tit.GrupoTitulacion
               SET FechaProgramada = @FechaProgramada,
                   HoraInicio = @HoraInicio,
                   HoraFin = @HoraFin,
                   HoraProgramada = @HoraInicio,
                   AulaOLink = @AulaOLink,
                   Lugar = @AulaOLink,
                   Modalidad = @Modalidad,
                   EstadoCodigo = 'PROGRAMADO',
                   EstadoGrupo = 'PROGRAMADO',
                   FechaActualizacion = SYSDATETIME()
             WHERE GrupoTitulacionId = @GrupoId;

            DECLARE @MecanismoId INT = (
                SELECT M.MecanismoTitulacionId
                FROM tit.GrupoTitulacion G
                INNER JOIN cat.MecanismoTitulacion M ON M.Codigo = G.MecanismoCodigo
                WHERE G.GrupoTitulacionId = @GrupoId
            );

            MERGE tit.ProgramacionTitulacion AS T
            USING (
                SELECT GE.ExpedienteId
                FROM tit.GrupoTitulacionEstudiante GE
                WHERE GE.GrupoTitulacionId = @GrupoId AND GE.Activo = 1
            ) AS S
            ON T.ExpedienteId = S.ExpedienteId AND T.MecanismoTitulacionId = @MecanismoId AND T.Activo = 1
            WHEN MATCHED THEN UPDATE SET
                FechaProgramada = @FechaProgramada,
                HoraProgramada = @HoraInicio,
                Lugar = @AulaOLink,
                Modalidad = @Modalidad,
                EnlaceVirtual = @AulaOLink,
                EstadoProgramacion = 'PROGRAMADA'
            WHEN NOT MATCHED THEN
                INSERT(ExpedienteId, MecanismoTitulacionId, FechaProgramada, HoraProgramada, Lugar, Modalidad, EnlaceVirtual, UsuarioRegistro)
                VALUES(S.ExpedienteId, @MecanismoId, @FechaProgramada, @HoraInicio, @AulaOLink, @Modalidad, @AulaOLink, @Usuario);
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition(sql, new
        {
            GrupoId = grupoId,
            FechaProgramada = ToDateTime(request.FechaProgramada),
            HoraInicio = ToTimeSpan(request.HoraInicio),
            HoraFin = ToTimeSpan(request.HoraFin),
            request.AulaOLink,
            request.Modalidad,
            Usuario = usuario
        }, cancellationToken: cancellationToken));
    }

    public async Task<IReadOnlyList<ResponsableTitulacionDto>> GetResponsablesAsync(string? rolCodigo, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT ResponsableTitulacionId, Cedula, Nombres, Correo, Cargo, RolCodigo, Activo
            FROM resp.ResponsableTitulacion
            WHERE Activo = 1 AND (@RolCodigo IS NULL OR RolCodigo = @RolCodigo)
            ORDER BY Nombres;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<ResponsableTitulacionDto>(new CommandDefinition(sql, new { RolCodigo = rolCodigo }, cancellationToken: cancellationToken))).ToList();
    }

    public async Task<ResponsableTitulacionDto> CreateResponsableAsync(UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken)
    {
        const string sql = """
            DECLARE @Insertados TABLE(ResponsableTitulacionId BIGINT NOT NULL);

            INSERT INTO resp.ResponsableTitulacion(Cedula, CedulaResponsable, Nombres, NombreResponsable, Correo, CorreoResponsable, Cargo, RolCodigo, UsuarioRegistro, UsuarioCreacion)
            OUTPUT inserted.ResponsableTitulacionId INTO @Insertados
            VALUES(@Cedula, @Cedula, @Nombres, @Nombres, @Correo, @Correo, @Cargo, @RolCodigo, @Usuario, @Usuario);

            SELECT R.ResponsableTitulacionId, R.Cedula, R.Nombres, R.Correo, R.Cargo, R.RolCodigo, R.Activo
            FROM resp.ResponsableTitulacion R
            INNER JOIN @Insertados I ON I.ResponsableTitulacionId = R.ResponsableTitulacionId;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QuerySingleAsync<ResponsableTitulacionDto>(new CommandDefinition(sql, new
        {
            request.Cedula,
            request.Nombres,
            request.Correo,
            request.Cargo,
            request.RolCodigo,
            Usuario = usuario
        }, cancellationToken: cancellationToken));
    }

    public async Task<ResponsableTitulacionDto> UpdateResponsableAsync(long id, UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE resp.ResponsableTitulacion
               SET Cedula = @Cedula,
                   CedulaResponsable = @Cedula,
                   Nombres = @Nombres,
                   NombreResponsable = @Nombres,
                   Correo = @Correo,
                   CorreoResponsable = @Correo,
                   Cargo = @Cargo,
                   RolCodigo = @RolCodigo,
                   UsuarioRegistro = @Usuario,
                   UsuarioCreacion = @Usuario
             OUTPUT inserted.ResponsableTitulacionId, inserted.Cedula, inserted.Nombres, inserted.Correo, inserted.Cargo, inserted.RolCodigo, inserted.Activo
             WHERE ResponsableTitulacionId = @Id;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QuerySingleAsync<ResponsableTitulacionDto>(new CommandDefinition(sql, new
        {
            Id = id,
            request.Cedula,
            request.Nombres,
            request.Correo,
            request.Cargo,
            request.RolCodigo,
            Usuario = usuario
        }, cancellationToken: cancellationToken));
    }

    public async Task DeleteResponsableAsync(long id, string usuario, CancellationToken cancellationToken)
    {
        const string sql = "UPDATE resp.ResponsableTitulacion SET Activo = 0 WHERE ResponsableTitulacionId = @Id;";
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition(sql, new { Id = id, Usuario = usuario }, cancellationToken: cancellationToken));
    }

    public async Task AsignarResponsableComplexivoAsync(long grupoId, AsignarResponsableComplexivoRequest request, string usuario, CancellationToken cancellationToken)
    {
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        using var tx = connection.BeginTransaction();
        await connection.ExecuteAsync(new CommandDefinition("""
            UPDATE resp.AsignacionResponsableTitulacion
               SET Activo = 0
             WHERE GrupoTitulacionId = @GrupoId
               AND RolCodigo IN ('RESPONSABLE_COMPLEXIVO', 'EVALUADOR_1', 'EVALUADOR_2', 'EVALUADOR_3');
            """, new { GrupoId = grupoId }, tx, cancellationToken: cancellationToken));

        await InsertAsignacionAsync(connection, tx, grupoId, request.ResponsableComplexivoId, "RESPONSABLE_COMPLEXIVO", 0, false, usuario);
        var orden = 1;
        foreach (var evaluadorId in request.EvaluadoresIds.Take(3))
        {
            await InsertAsignacionAsync(connection, tx, grupoId, evaluadorId, $"EVALUADOR_{orden}", orden, false, usuario);
            orden++;
        }
        tx.Commit();
    }

    public async Task AsignarTribunalDefensaAsync(long grupoId, AsignarTribunalDefensaRequest request, string usuario, CancellationToken cancellationToken)
    {
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        using var tx = connection.BeginTransaction();
        await connection.ExecuteAsync(new CommandDefinition("""
            UPDATE resp.AsignacionResponsableTitulacion
               SET Activo = 0
             WHERE GrupoTitulacionId = @GrupoId
               AND EsTribunal = 1;
            """, new { GrupoId = grupoId }, tx, cancellationToken: cancellationToken));

        await InsertAsignacionAsync(connection, tx, grupoId, request.PresidenteTribunalId, "PRESIDENTE_TRIBUNAL", 1, true, usuario);
        await InsertAsignacionAsync(connection, tx, grupoId, request.Vocal1Id, "VOCAL_1", 2, true, usuario);
        await InsertAsignacionAsync(connection, tx, grupoId, request.Vocal2Id, "VOCAL_2", 3, true, usuario);
        if (request.TutorId is > 0)
        {
            await InsertAsignacionAsync(connection, tx, grupoId, request.TutorId.Value, "TUTOR", 4, true, usuario);
        }
        tx.Commit();
    }

    public async Task<IReadOnlyList<ResponsableAsignadoDto>> GetResponsablesAsignadosAsync(long grupoId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT AsignacionId, GrupoTitulacionId, ExpedienteId, ResponsableTitulacionId, Nombres, RolCodigo, Orden, EsTribunal
            FROM rpt.vw_ResponsablesTribunal
            WHERE GrupoTitulacionId = @GrupoId
            ORDER BY ISNULL(Orden, 999), AsignacionId;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<ResponsableAsignadoDto>(new CommandDefinition(sql, new { GrupoId = grupoId }, cancellationToken: cancellationToken))).ToList();
    }

    public async Task<IReadOnlyList<CalificacionEvaluadorDto>> GetCalificacionesEvaluadorAsync(long expedienteId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT CalificacionEvaluadorId, ExpedienteId, GrupoTitulacionId, ResponsableTitulacionId, EvaluadorNumero,
                   NotaTrabajoEscrito, NotaDefensaOral, NotaExamenComplexivo, NotaTitulacionSobre20, Cerrado, Observacion
            FROM eval.CalificacionEvaluador
            WHERE ExpedienteId = @ExpedienteId
            ORDER BY GrupoTitulacionId DESC, EvaluadorNumero;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<CalificacionEvaluadorDto>(new CommandDefinition(sql, new { ExpedienteId = expedienteId }, cancellationToken: cancellationToken))).ToList();
    }

    public async Task<CalificacionConsolidadaDto?> RegistrarCalificacionEvaluadorAsync(RegistrarCalificacionEvaluadorRequest request, string usuario, CancellationToken cancellationToken)
    {
        var parameters = new DynamicParameters();
        parameters.Add("ExpedienteId", request.ExpedienteId);
        parameters.Add("GrupoTitulacionId", request.GrupoTitulacionId);
        parameters.Add("EvaluadorNumero", request.EvaluadorNumero);
        parameters.Add("ResponsableTitulacionId", request.ResponsableTitulacionId);
        parameters.Add("NotaTrabajoEscrito", request.NotaTrabajoEscrito);
        parameters.Add("NotaDefensaOral", request.NotaDefensaOral);
        parameters.Add("NotaExamenComplexivo", request.NotaExamenComplexivo);
        parameters.Add("Observacion", request.Observacion);
        parameters.Add("Usuario", usuario);

        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QueryFirstOrDefaultAsync<CalificacionConsolidadaDto>(new CommandDefinition("eval.sp_RegistrarNotaEvaluador", parameters, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
    }

    public async Task<CalificacionConsolidadaDto?> ConsolidarCalificacionAsync(long expedienteId, long grupoId, string usuario, CancellationToken cancellationToken)
    {
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QueryFirstOrDefaultAsync<CalificacionConsolidadaDto>(new CommandDefinition("eval.sp_CalcularConsolidadoEstudiante", new
        {
            ExpedienteId = expedienteId,
            GrupoTitulacionId = grupoId,
            Usuario = usuario
        }, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
    }

    public async Task<CalificacionConsolidadaDto?> GetConsolidadoAsync(long expedienteId, CancellationToken cancellationToken)
    {
        const string sql = "SELECT * FROM eval.CalificacionConsolidada WHERE ExpedienteId = @ExpedienteId;";
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QueryFirstOrDefaultAsync<CalificacionConsolidadaDto>(new CommandDefinition(sql, new { ExpedienteId = expedienteId }, cancellationToken: cancellationToken));
    }

    public async Task ReabrirCalificacionAsync(long calificacionId, string usuario, CancellationToken cancellationToken)
    {
        const string sql = """
            DECLARE @ExpedienteId BIGINT;
            DECLARE @GrupoTitulacionId BIGINT;

            SELECT
                @ExpedienteId = ExpedienteId,
                @GrupoTitulacionId = GrupoTitulacionId
            FROM eval.CalificacionEvaluador
            WHERE CalificacionEvaluadorId = @CalificacionId;

            IF @ExpedienteId IS NULL
                THROW 59760, 'No existe la calificacion solicitada.', 1;

            UPDATE eval.CalificacionEvaluador
               SET Cerrado = 0,
                   UsuarioRegistro = @Usuario,
                   FechaRegistro = SYSDATETIME()
             WHERE CalificacionEvaluadorId = @CalificacionId;

            EXEC eval.sp_CalcularConsolidadoEstudiante
                @ExpedienteId = @ExpedienteId,
                @GrupoTitulacionId = @GrupoTitulacionId,
                @Usuario = @Usuario;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition(sql, new { CalificacionId = calificacionId, Usuario = usuario }, cancellationToken: cancellationToken));
    }

    public async Task<DocumentoTitulacionDto> InsertDocumentoAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken)
    {
        const string sql = """
            INSERT INTO doc.DocumentoTitulacion(ExpedienteId, GrupoTitulacionId, NumeroIdentificacion, TipoDocumentoCodigo, NombreArchivo,
                RutaNube, UrlPublica, HashArchivo, ContentType, EsFirmadoElectronico, EstadoCodigo, Observacion, UsuarioCarga)
            OUTPUT inserted.DocumentoTitulacionId AS DocumentoId, inserted.ExpedienteId, inserted.GrupoTitulacionId, inserted.NumeroIdentificacion,
                   inserted.TipoDocumentoCodigo, inserted.NombreArchivo, inserted.RutaNube, inserted.UrlPublica, inserted.EstadoCodigo,
                   inserted.EsFirmadoElectronico AS EsFirmadoElectronicamente, inserted.Observacion, inserted.Version,
                   inserted.CodigoRegistroSenescyt, inserted.FechaRegistroSenescyt, inserted.NumeroTituloIntec,
                   inserted.FechaEmisionTitulo, inserted.CodigoVerificacionQr, inserted.FechaCarga, inserted.UsuarioCarga
            VALUES(@ExpedienteId, @GrupoTitulacionId, @Cedula, @TipoDocumentoCodigo, @NombreArchivo, @RutaNube, @UrlPublica, @HashArchivo, @ContentType,
                   @EsFirmadoElectronicamente, 'CARGADO', @Observacion, @Usuario);
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        var documento = await connection.QuerySingleAsync<DocumentoTitulacionDto>(new CommandDefinition(sql, new
        {
            request.ExpedienteId,
            request.GrupoTitulacionId,
            request.Cedula,
            request.TipoDocumentoCodigo,
            storedFile.FileName,
            storedFile.RutaNube,
            storedFile.UrlPublica,
            HashArchivo = storedFile.Hash.Length == 0 ? null : storedFile.Hash,
            storedFile.ContentType,
            request.EsFirmadoElectronicamente,
            request.Observacion,
            Usuario = usuario
        }, cancellationToken: cancellationToken));
        await connection.ExecuteAsync(new CommandDefinition("doc.sp_RegistrarHistorialDocumento", new
        {
            DocumentoTitulacionId = documento.DocumentoId,
            Accion = "CARGA",
            request.Observacion,
            Usuario = usuario
        }, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
        return documento;
    }

    public async Task<IReadOnlyList<DocumentoTitulacionDto>> GetDocumentosByExpedienteAsync(long expedienteId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT DocumentoTitulacionId AS DocumentoId, ExpedienteId, GrupoTitulacionId, NumeroIdentificacion, TipoDocumentoCodigo,
                   NombreArchivo, RutaNube, UrlPublica, EstadoCodigo, EsFirmadoElectronico AS EsFirmadoElectronicamente,
                   Observacion, Version, CodigoRegistroSenescyt, FechaRegistroSenescyt, NumeroTituloIntec,
                   FechaEmisionTitulo, CodigoVerificacionQr, FechaCarga, UsuarioCarga
            FROM doc.DocumentoTitulacion
            WHERE ExpedienteId = @ExpedienteId
            ORDER BY DocumentoTitulacionId DESC;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<DocumentoTitulacionDto>(new CommandDefinition(sql, new { ExpedienteId = expedienteId }, cancellationToken: cancellationToken))).ToList();
    }

    public async Task<IReadOnlyList<DocumentoTitulacionHistorialDto>> GetDocumentoHistorialAsync(long documentoId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT HistorialId, DocumentoTitulacionId, ExpedienteId, TipoDocumentoCodigo, Version, EstadoCodigo,
                   Accion, Observacion, NombreArchivo, RutaNube, UrlPublica, UsuarioAccion, FechaAccion
            FROM doc.DocumentoTitulacionHistorial
            WHERE DocumentoTitulacionId = @DocumentoId
            ORDER BY HistorialId DESC;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<DocumentoTitulacionHistorialDto>(new CommandDefinition(sql, new { DocumentoId = documentoId }, cancellationToken: cancellationToken))).ToList();
    }

    public async Task ValidarDocumentoAsync(long documentoId, string usuario, CancellationToken cancellationToken)
    {
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition("doc.sp_ValidarDocumentoTitulacion", new { DocumentoTitulacionId = documentoId, Usuario = usuario }, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
    }

    public async Task ObservarDocumentoAsync(long documentoId, string observacion, string usuario, CancellationToken cancellationToken)
    {
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition("doc.sp_ObservarDocumentoTitulacion", new { DocumentoTitulacionId = documentoId, Observacion = observacion, Usuario = usuario }, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
    }

    public async Task<string> GenerarNumeroActaAsync(long expedienteId, GenerarActaGradoRequest request, CancellationToken cancellationToken)
    {
        var parameters = new DynamicParameters();
        parameters.Add("ExpedienteId", expedienteId);
        parameters.Add("FechaActa", ToDateTime(request.FechaActa));
        parameters.Add("EscuelaCodigo", request.Escuela);
        parameters.Add("NumeroActa", dbType: DbType.String, size: 100, direction: ParameterDirection.Output);
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition("tit.sp_GenerarNumeroActaGrado", parameters, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
        return parameters.Get<string>("NumeroActa");
    }

    public async Task<ActaGradoPdfDto> BuildActaPdfDtoAsync(long expedienteId, GenerarActaGradoRequest request, string numeroActa, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT TOP (1)
                @NumeroActa AS NumeroActa,
                COALESCE(@Escuela, E.Carrera, N'INTEC') AS Escuela,
                @Ciudad AS Ciudad,
                @FechaActa AS FechaActa,
                COALESCE(@HoraActa, CAST('00:00:00' AS time)) AS HoraActa,
                @NombreInstitucion AS NombreInstitucion,
                COALESCE(E.Carrera, N'') AS Carrera,
                COALESCE(A.Modalidad, E.MecanismoTitulacionId, N'') AS Modalidad,
                COALESCE(ER.ApellidosNombres, E.NumeroIdentificacion, N'') AS NombreEstudiante,
                COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion, N'') AS Cedula,
                COALESCE(E.MecanismoTitulacionId, N'') AS MecanismoTitulacion,
                COALESCE(E.TituloOtorgado, N'') AS TituloOtorgado,
                COALESCE(C.NotaAsignaturas, E.PromedioAsignaturas, 0) AS NotaAsignaturas,
                COALESCE(C.EquivalenciaAsignaturas80, E.NotaPromedioAsignaturas80, 0) AS EquivalenciaAsignaturas80,
                COALESCE(C.NotaTitulacionSobre20, 0) AS NotaProcesoTitulacion,
                COALESCE(C.EquivalenciaTitulacion20, E.NotaProcesoTitulacion20, 0) AS EquivalenciaTitulacion20,
                COALESCE(C.NotaFinalGrado, E.NotaFinalGrado, 0) AS NotaFinalGrado,
                COALESCE(@AutoridadAcademica, N'') AS AutoridadAcademica,
                COALESCE(@CoordinadorAcademico, N'') AS CoordinadorAcademico,
                COALESCE(@DocenteEvaluador, N'') AS DocenteEvaluador
            FROM tit.ExpedienteTitulacion E
            LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
            LEFT JOIN eval.CalificacionConsolidada C ON C.ExpedienteId = E.ExpedienteId
            OUTER APPLY (
                SELECT TOP (1) Modalidad
                FROM tit.ActaGrado
                WHERE ExpedienteId = E.ExpedienteId
                ORDER BY ActaGradoId DESC
            ) A
            WHERE E.ExpedienteId = @ExpedienteId;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        var dto = await connection.QuerySingleAsync<ActaGradoPdfDto>(new CommandDefinition(sql, new
        {
            ExpedienteId = expedienteId,
            NumeroActa = numeroActa,
            request.Escuela,
            request.Ciudad,
            FechaActa = ToDateTime(request.FechaActa),
            HoraActa = ToTimeSpan(request.HoraActa),
            request.NombreInstitucion,
            request.AutoridadAcademica,
            request.CoordinadorAcademico,
            request.DocenteEvaluador
        }, cancellationToken: cancellationToken));
        dto.TextoVariable = BuildTextoVariable(dto);
        dto.Firmas = new List<FirmaActaDto>
        {
            new() { Cargo = "Autoridad academica", Nombre = dto.AutoridadAcademica },
            new() { Cargo = "Coordinador academico", Nombre = dto.CoordinadorAcademico },
            new() { Cargo = "Docente evaluador", Nombre = dto.DocenteEvaluador }
        };
        return dto;
    }

    public async Task<ActaGradoDto> GenerarActaAsync(long expedienteId, GenerarActaGradoRequest request, StoredFile actaPdf, ActaGradoPdfDto pdfDto, string usuario, CancellationToken cancellationToken)
    {
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        var acta = await connection.QuerySingleAsync<ActaGradoDto>(new CommandDefinition("tit.sp_GenerarActaGradoEstudiante", new
        {
            ExpedienteId = expedienteId,
            request.NumeroActa,
            FechaActa = ToDateTime(request.FechaActa),
            HoraActa = ToTimeSpan(request.HoraActa),
            request.Ciudad,
            request.Escuela,
            request.AutoridadAcademica,
            request.CoordinadorAcademico,
            request.DocenteEvaluador,
            RutaActaPdf = actaPdf.RutaNube,
            Usuario = usuario
        }, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));

        await connection.ExecuteAsync(new CommandDefinition("""
            UPDATE tit.ActaGrado
               SET NombreInstitucion = @NombreInstitucion,
                   TextoVariableActa = @TextoVariable,
                   HashPdf = @HashPdf,
                   Activo = 1
             WHERE ActaGradoId = @ActaGradoId;

            INSERT INTO doc.DocumentoTitulacion(ExpedienteId, NumeroIdentificacion, TipoDocumentoCodigo, NombreArchivo, RutaNube, UrlPublica, HashArchivo, ContentType, EstadoCodigo, UsuarioCarga)
            VALUES(@ExpedienteId, @Cedula, 'ACTA_GRADO', @NombreArchivo, @RutaNube, @UrlPublica, @HashPdf, @ContentType, 'CARGADO', @Usuario);

            DECLARE @DocumentoId BIGINT = SCOPE_IDENTITY();
            EXEC doc.sp_RegistrarHistorialDocumento @DocumentoTitulacionId = @DocumentoId, @Accion = 'CARGA', @Usuario = @Usuario;
            """, new
        {
            acta.ActaGradoId,
            ExpedienteId = expedienteId,
            pdfDto.Cedula,
            pdfDto.NombreInstitucion,
            pdfDto.TextoVariable,
            HashPdf = actaPdf.Hash.Length == 0 ? null : actaPdf.Hash,
            actaPdf.FileName,
            actaPdf.RutaNube,
            actaPdf.UrlPublica,
            actaPdf.ContentType,
            Usuario = usuario
        }, cancellationToken: cancellationToken));

        return await GetActaByIdAsync(acta.ActaGradoId, cancellationToken) ?? acta;
    }

    public async Task<ActaGradoDto?> GetActaByExpedienteAsync(long expedienteId, CancellationToken cancellationToken)
    {
        const string sql = "SELECT * FROM tit.ActaGrado WHERE ExpedienteId = @ExpedienteId AND ISNULL(Activo, 1) = 1 ORDER BY ActaGradoId DESC;";
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QueryFirstOrDefaultAsync<ActaGradoDto>(new CommandDefinition(sql, new { ExpedienteId = expedienteId }, cancellationToken: cancellationToken));
    }

    public async Task<ActaGradoDto?> GetActaByIdAsync(long actaId, CancellationToken cancellationToken)
    {
        const string sql = "SELECT * FROM tit.ActaGrado WHERE ActaGradoId = @ActaId;";
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QueryFirstOrDefaultAsync<ActaGradoDto>(new CommandDefinition(sql, new { ActaId = actaId }, cancellationToken: cancellationToken));
    }

    public async Task<IReadOnlyList<ActaGradoDto>> GetActasAsync(CancellationToken cancellationToken)
    {
        const string sql = "SELECT * FROM tit.ActaGrado ORDER BY ActaGradoId DESC;";
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<ActaGradoDto>(new CommandDefinition(sql, cancellationToken: cancellationToken))).ToList();
    }

    public async Task AnularActaAsync(long actaId, string motivo, string usuario, CancellationToken cancellationToken)
    {
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        await connection.ExecuteAsync(new CommandDefinition("tit.sp_AnularActaGrado", new
        {
            ActaGradoId = actaId,
            Motivo = motivo,
            Usuario = usuario
        }, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
    }

    public async Task<DocumentoTitulacionDto> CargarTituloRegistradoAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken)
    {
        return await ExecuteTituloProcedureAsync("doc.sp_CargarTituloRegistradoV2", request, storedFile, usuario, cancellationToken);
    }

    public async Task<DocumentoTitulacionDto> CargarTituloIntecAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken)
    {
        return await ExecuteTituloProcedureAsync("doc.sp_CargarTituloIntecV2", request, storedFile, usuario, cancellationToken);
    }

    public async Task<IReadOnlyList<TituloTitulacionDto>> GetTitulosAsync(string? search, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT DocumentoId, ExpedienteId, GrupoTitulacionId, NumeroIdentificacion, TipoDocumentoCodigo,
                   NombreArchivo, RutaNube, UrlPublica, EstadoCodigo, CAST(0 AS bit) AS EsFirmadoElectronicamente,
                   Observacion, Version, CodigoRegistroSenescyt, FechaRegistroSenescyt, NumeroTituloIntec,
                   FechaEmisionTitulo, CodigoVerificacionQr, FechaCarga, UsuarioCarga,
                   NombresEstudiante, Carrera, NumeroActa, NumeroActaGrado
            FROM rpt.vw_TitulosPortal
            WHERE @Search IS NULL
               OR NumeroIdentificacion LIKE @Term
               OR NombresEstudiante LIKE @Term
               OR Carrera LIKE @Term
               OR NumeroActa LIKE @Term
               OR NumeroActaGrado LIKE @Term
               OR EstadoCodigo LIKE @Term
            ORDER BY DocumentoId DESC;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return (await connection.QueryAsync<TituloTitulacionDto>(new CommandDefinition(sql, new { Search = search, Term = $"%{search}%" }, cancellationToken: cancellationToken))).ToList();
    }

    private async Task<GrupoTitulacionDto?> GetGrupoWithConnectionAsync(IDbConnection connection, long id, CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT * FROM (
                {GrupoSelectSql("rpt.vw_GruposComplexivo")}
                UNION ALL
                {GrupoSelectSql("rpt.vw_DefensasGrado")}
            ) G
            WHERE G.GrupoTitulacionId = @Id;
            """;
        var grupo = await connection.QueryFirstOrDefaultAsync<GrupoTitulacionDto>(new CommandDefinition(sql, new { Id = id }, cancellationToken: cancellationToken));
        if (grupo is null)
        {
            return null;
        }

        grupo.Estudiantes = (await connection.QueryAsync<GrupoEstudianteDto>(new CommandDefinition("""
            SELECT GrupoTitulacionEstudianteId, ExpedienteId, NumeroIdentificacion, CodigoEstud, OrdenIntegrante, EsPrincipal, EstadoCodigo
            FROM tit.GrupoTitulacionEstudiante
            WHERE GrupoTitulacionId = @Id AND Activo = 1
            ORDER BY ISNULL(OrdenIntegrante, 999), GrupoTitulacionEstudianteId;
            """, new { Id = id }, cancellationToken: cancellationToken))).ToList();
        grupo.Responsables = (await connection.QueryAsync<ResponsableAsignadoDto>(new CommandDefinition("""
            SELECT AsignacionId, GrupoTitulacionId, ExpedienteId, ResponsableTitulacionId, Nombres, RolCodigo, Orden, EsTribunal
            FROM rpt.vw_ResponsablesTribunal
            WHERE GrupoTitulacionId = @Id
            ORDER BY ISNULL(Orden, 999), AsignacionId;
            """, new { Id = id }, cancellationToken: cancellationToken))).ToList();
        return grupo;
    }

    private async Task<DocumentoTitulacionDto> ExecuteTituloProcedureAsync(string procedureName, UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken)
    {
        if (request.ExpedienteId is null)
        {
            throw new TitulacionException("EXPEDIENTE_REQUERIDO", "Debe indicar expediente para cargar el titulo.");
        }

        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        object parameters = procedureName.Contains("Registrado", StringComparison.OrdinalIgnoreCase)
            ? new
            {
                ExpedienteId = request.ExpedienteId.Value,
                NumeroIdentificacion = request.Cedula,
                NombreArchivo = storedFile.FileName,
                RutaNube = storedFile.RutaNube,
                UrlPublica = storedFile.UrlPublica,
                HashArchivo = storedFile.Hash.Length == 0 ? null : storedFile.Hash,
                ContentType = storedFile.ContentType,
                request.CodigoRegistroSenescyt,
                FechaRegistroSenescyt = ToDateTime(request.FechaRegistroSenescyt),
                request.Observacion,
                Usuario = usuario
            }
            : new
            {
                ExpedienteId = request.ExpedienteId.Value,
                NumeroIdentificacion = request.Cedula,
                NombreArchivo = storedFile.FileName,
                RutaNube = storedFile.RutaNube,
                UrlPublica = storedFile.UrlPublica,
                HashArchivo = storedFile.Hash.Length == 0 ? null : storedFile.Hash,
                ContentType = storedFile.ContentType,
                request.NumeroTituloIntec,
                FechaEmisionTitulo = ToDateTime(request.FechaEmisionTitulo),
                request.CodigoVerificacionQr,
                request.Observacion,
                Usuario = usuario
            };

        return await connection.QuerySingleAsync<DocumentoTitulacionDto>(new CommandDefinition(procedureName,
            parameters, commandType: CommandType.StoredProcedure, cancellationToken: cancellationToken));
    }

    private async Task<DocumentoTitulacionDto> GetUltimoTituloAsync(long expedienteId, string tipo, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT TOP (1) DocumentoTitulacionId AS DocumentoId, ExpedienteId, GrupoTitulacionId, NumeroIdentificacion,
                   TipoDocumentoCodigo, NombreArchivo, RutaNube, UrlPublica, EstadoCodigo,
                   EsFirmadoElectronico AS EsFirmadoElectronicamente, CAST(NULL AS nvarchar(1000)) AS Observacion
            FROM doc.DocumentoTitulacion
            WHERE ExpedienteId = @ExpedienteId AND TipoDocumentoCodigo = @Tipo
            ORDER BY DocumentoTitulacionId DESC;
            """;
        using var connection = await connectionFactory.OpenAsync(cancellationToken);
        return await connection.QuerySingleAsync<DocumentoTitulacionDto>(new CommandDefinition(sql, new { ExpedienteId = expedienteId, Tipo = tipo }, cancellationToken: cancellationToken));
    }

    private static string BuildTextoVariable(ActaGradoPdfDto dto)
    {
        var accion = string.Equals(dto.MecanismoTitulacion, "EXAMEN_COMPLEXIVO", StringComparison.OrdinalIgnoreCase)
            ? "rendir su examen complexivo"
            : "sustentar la defensa de grado";

        return $"se presenta el/la estudiante {dto.NombreEstudiante} con cedula de ciudadania No. {dto.Cedula}; para {accion} como requisito previo para obtener el titulo de: {dto.TituloOtorgado}";
    }

    private static async Task InsertAsignacionAsync(IDbConnection connection, IDbTransaction tx, long grupoId, long responsableId, string rolCodigo, int orden, bool esTribunal, string usuario)
    {
        await connection.ExecuteAsync("""
            INSERT INTO resp.AsignacionResponsableTitulacion(GrupoTitulacionId, ResponsableTitulacionId, RolCodigo, Orden, EsTribunal, UsuarioAsignacion)
            VALUES(@GrupoId, @ResponsableId, @RolCodigo, @Orden, @EsTribunal, @Usuario);
            """, new { GrupoId = grupoId, ResponsableId = responsableId, RolCodigo = rolCodigo, Orden = orden, EsTribunal = esTribunal, Usuario = usuario }, tx);
    }

    private static DynamicParameters GrupoParameters(CrearGrupoComplexivoRequest request, string usuario)
    {
        var parameters = new DynamicParameters();
        parameters.Add("CodigoGrupo", request.CodigoGrupo);
        parameters.Add("Tema", request.Tema);
        parameters.Add("Carrera", request.Carrera);
        parameters.Add("CodigoCarrera", request.CodigoCarrera);
        parameters.Add("FechaProgramada", ToDateTime(request.FechaProgramada));
        parameters.Add("HoraInicio", ToTimeSpan(request.HoraInicio));
        parameters.Add("HoraFin", ToTimeSpan(request.HoraFin));
        parameters.Add("AulaOLink", request.AulaOLink);
        parameters.Add("Modalidad", request.Modalidad);
        parameters.Add("Usuario", usuario);
        return parameters;
    }

    private static string GrupoSelectSql(string viewName) => $"""
        SELECT GrupoTitulacionId, CodigoGrupo, NombreGrupo, MecanismoCodigo, Tema, Carrera, CodigoCarrera,
               FechaProgramada, HoraInicio, HoraFin, AulaOLink, Modalidad, EstadoCodigo, MaximoIntegrantes, TotalIntegrantes
        FROM {viewName}
        """;

    private static string BuildEstudiantesWhere(EstudianteAptoFiltro filtro, DynamicParameters parameters)
    {
        var filters = new List<string> { "1 = 1" };
        AddLike(filters, parameters, "Cedula", "COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion)", filtro.Cedula);
        AddLike(filters, parameters, "Nombres", "ER.ApellidosNombres", filtro.Nombres);
        AddLike(filters, parameters, "Carrera", "E.Carrera", filtro.Carrera);
        AddLike(filters, parameters, "Periodo", "E.CodigoPeriodo", filtro.Periodo);
        AddEquals(filters, parameters, "Estado", "E.EstadoExpediente", filtro.Estado);
        AddEquals(filters, parameters, "Mecanismo", "E.MecanismoTitulacionId", filtro.MecanismoSugerido);
        AddBit(filters, parameters, "Practicas", "E.PracticasPreprofesionalesCumple", filtro.CumplePracticas);
        AddBit(filters, parameters, "Vinculacion", "E.VinculacionCumple", filtro.CumpleVinculacion);
        AddBit(filters, parameters, "Financiero", "E.NoAdeudaFinanciero", filtro.Financiero);
        AddBit(filters, parameters, "Malla", "E.MallaCurricularCumple", filtro.Malla);
        AddBit(filters, parameters, "Ingles", "E.InglesA2Cumple", filtro.Ingles);
        return string.Join(" AND ", filters);
    }

    private static void AddLike(List<string> filters, DynamicParameters parameters, string name, string column, string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return;
        filters.Add($"{column} LIKE @{name}");
        parameters.Add(name, $"%{value.Trim()}%");
    }

    private static void AddEquals(List<string> filters, DynamicParameters parameters, string name, string column, string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return;
        filters.Add($"{column} = @{name}");
        parameters.Add(name, value.Trim());
    }

    private static void AddBit(List<string> filters, DynamicParameters parameters, string name, string column, bool? value)
    {
        if (!value.HasValue) return;
        filters.Add($"ISNULL({column}, 0) = @{name}");
        parameters.Add(name, value.Value);
    }

    private static DateTime? ToDateTime(DateOnly? date) => date?.ToDateTime(TimeOnly.MinValue);
    private static TimeSpan? ToTimeSpan(TimeOnly? time) => time?.ToTimeSpan();

    private const string EstudiantesBaseSql = """
        SELECT
            COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion) AS Cedula,
            COALESCE(E.CodigoEstud, ER.CodigoEstud) AS CodigoEstud,
            COALESCE(ER.ApellidosNombres, COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion)) AS Nombres,
            COALESCE(E.Carrera, N'') AS Carrera,
            COALESCE(E.CodigoCarrera, N'') AS CodigoCarrera,
            COALESCE(E.CodigoPeriodo, N'') AS Periodo,
            CAST(ISNULL(E.TituloBachillerCumple, 0) AS bit) AS CumpleTituloBachiller,
            CAST(ISNULL(E.InglesA2Cumple, 0) AS bit) AS CumpleInglesA2,
            CAST(ISNULL(E.PracticasPreprofesionalesCumple, 0) AS bit) AS CumplePracticas,
            CAST(ISNULL(E.VinculacionCumple, 0) AS bit) AS CumpleVinculacion,
            CAST(ISNULL(E.MallaCurricularCumple, 0) AS bit) AS CumpleMalla,
            CAST(ISNULL(E.NoAdeudaFinanciero, 0) AS bit) AS NoAdeudaFinanciero,
            CAST(ISNULL(E.AptoSustentacion, 0) AS bit) AS AptoSustentacion,
            E.PromedioAsignaturas AS NotaAsignaturas,
            E.NotaPromedioAsignaturas80 AS Equivalencia80,
            CAST(CASE WHEN
                ISNULL(E.CedulaValidada, 0) = 1 AND
                ISNULL(E.TituloBachillerCumple, 0) = 1 AND
                ISNULL(E.InglesA2Cumple, 0) = 1 AND
                ISNULL(E.PracticasPreprofesionalesCumple, 0) = 1 AND
                ISNULL(E.VinculacionCumple, 0) = 1 AND
                ISNULL(E.MallaCurricularCumple, 0) = 1 AND
                ISNULL(E.NoAdeudaFinanciero, 0) = 1 AND
                ISNULL(E.AptoSustentacion, 0) = 1 AND
                E.PromedioAsignaturas IS NOT NULL
                THEN 1 ELSE 0 END AS bit) AS PuedeHabilitar,
            CONCAT(
                CASE WHEN ISNULL(E.CedulaValidada, 0) = 0 THEN N'Cedula; ' ELSE N'' END,
                CASE WHEN ISNULL(E.TituloBachillerCumple, 0) = 0 THEN N'Bachiller; ' ELSE N'' END,
                CASE WHEN ISNULL(E.InglesA2Cumple, 0) = 0 THEN N'Ingles; ' ELSE N'' END,
                CASE WHEN ISNULL(E.PracticasPreprofesionalesCumple, 0) = 0 THEN N'Practicas; ' ELSE N'' END,
                CASE WHEN ISNULL(E.VinculacionCumple, 0) = 0 THEN N'Vinculacion; ' ELSE N'' END,
                CASE WHEN ISNULL(E.MallaCurricularCumple, 0) = 0 THEN N'Malla; ' ELSE N'' END,
                CASE WHEN ISNULL(E.NoAdeudaFinanciero, 0) = 0 THEN N'Financiero; ' ELSE N'' END,
                CASE WHEN ISNULL(E.AptoSustentacion, 0) = 0 THEN N'Sustentacion; ' ELSE N'' END,
                CASE WHEN E.PromedioAsignaturas IS NULL THEN N'Promedio; ' ELSE N'' END
            ) AS MotivoNoApto,
            COALESCE(E.EstadoExpediente, N'') AS Estado,
            COALESCE(E.MecanismoTitulacionId, N'') AS MecanismoSugerido
        FROM tit.ExpedienteTitulacion E
        LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
        """;
}
