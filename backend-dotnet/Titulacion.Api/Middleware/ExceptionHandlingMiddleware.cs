using Microsoft.AspNetCore.Mvc;
using Microsoft.Data.SqlClient;
using Titulacion.Domain;

namespace Titulacion.Api.Middleware;

public sealed class ExceptionHandlingMiddleware(RequestDelegate next, ILogger<ExceptionHandlingMiddleware> logger)
{
    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await next(context);
        }
        catch (TitulacionException exc)
        {
            await WriteProblemAsync(context, exc.StatusCode, exc.Code, exc.Message);
        }
        catch (SqlException exc)
        {
            logger.LogError(exc, "SQL error en titulacion");
            var (code, message, status) = MapSql(exc);
            await WriteProblemAsync(context, status, code, message);
        }
        catch (FileNotFoundException exc)
        {
            await WriteProblemAsync(context, StatusCodes.Status404NotFound, "ARCHIVO_NO_ENCONTRADO", exc.Message);
        }
        catch (Exception exc)
        {
            logger.LogError(exc, "Error no controlado en titulacion");
            await WriteProblemAsync(context, StatusCodes.Status500InternalServerError, "ERROR_INTERNO", "Error interno del servidor.");
        }
    }

    private static Task WriteProblemAsync(HttpContext context, int statusCode, string code, string message)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/problem+json";
        var problem = new ProblemDetails
        {
            Status = statusCode,
            Title = code,
            Detail = message,
            Type = $"https://intec.local/errors/{code}"
        };
        problem.Extensions["code"] = code;
        return context.Response.WriteAsJsonAsync(problem);
    }

    private static (string Code, string Message, int Status) MapSql(SqlException exc)
    {
        var message = exc.Errors.Count > 0 ? exc.Errors[0].Message : exc.Message;
        return exc.Number switch
        {
            59701 or 59702 => (TitulacionErrorCodes.DefensaMaximoDosEstudiantes, message, 400),
            59710 => (TitulacionErrorCodes.MecanismoInvalido, message, 400),
            59711 => (TitulacionErrorCodes.EstudianteNoApto, message, 400),
            59732 => (TitulacionErrorCodes.TribunalIncompleto, message, 400),
            59740 or 59741 => (TitulacionErrorCodes.NotasIncompletas, message, 400),
            59750 => (TitulacionErrorCodes.EstudianteNoApto, message, 400),
            59751 => (TitulacionErrorCodes.ActaYaGenerada, message, 409),
            59753 => (TitulacionErrorCodes.DocumentosObligatoriosPendientes, message, 400),
            59754 => (TitulacionErrorCodes.FaltanTresEvaluadores, message, 400),
            59760 => (TitulacionErrorCodes.TituloRegistroRequiereActa, message, 400),
            59770 => (TitulacionErrorCodes.TituloIntecRequiereActa, message, 400),
            59801 => ("NUMERACION_ACTA_INVALIDA", message, 400),
            59820 => (TitulacionErrorCodes.TituloRegistroRequiereActa, message, 400),
            59830 => (TitulacionErrorCodes.TituloIntecRequiereActa, message, 400),
            _ => ("SQL_SERVER_ERROR", message, 400)
        };
    }
}
