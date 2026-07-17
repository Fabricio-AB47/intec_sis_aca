using System.Globalization;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;
using Titulacion.Application;
using Titulacion.Contracts;
using Titulacion.Domain;

namespace Titulacion.Infrastructure;

public sealed class GraphTeamsCalendarService(
    HttpClient httpClient,
    IOptions<TitulacionTeamsOptions> options,
    IConfiguration configuration) : ITeamsCalendarService
{
    private const string GraphScope = "https://graph.microsoft.com/.default";
    private readonly JsonSerializerOptions jsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<TeamsCalendarEventDto> CreateTeamsEventAsync(TeamsCalendarEventRequest request, CancellationToken cancellationToken)
    {
        var settings = ResolveSettings(request.OrganizerUser);
        var token = await GetAccessTokenAsync(settings, cancellationToken);
        var organizer = Uri.EscapeDataString(settings.OrganizerUser);
        var url = $"https://graph.microsoft.com/v1.0/users/{organizer}/events";

        using var httpRequest = new HttpRequestMessage(HttpMethod.Post, url);
        httpRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        httpRequest.Headers.Add("Prefer", $"outlook.timezone=\"{settings.TimeZone}\"");
        httpRequest.Content = JsonContent.Create(BuildEventPayload(request, settings.TimeZone), options: jsonOptions);

        using var response = await httpClient.SendAsync(httpRequest, cancellationToken);
        var content = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new TitulacionException(
                TitulacionErrorCodes.TeamsEventoNoCreado,
                $"No se pudo crear el evento en Teams. Microsoft Graph devolvio {(int)response.StatusCode}: {TrimForClient(content)}",
                502);
        }

        using var document = JsonDocument.Parse(content);
        var root = document.RootElement;
        var joinUrl = TryGetString(root, "onlineMeeting", "joinUrl");
        return new TeamsCalendarEventDto
        {
            EventId = TryGetString(root, "id") ?? string.Empty,
            WebLink = TryGetString(root, "webLink"),
            JoinUrl = joinUrl
        };
    }

    private async Task<string> GetAccessTokenAsync(ResolvedTeamsSettings settings, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, $"https://login.microsoftonline.com/{Uri.EscapeDataString(settings.TenantId)}/oauth2/v2.0/token");
        request.Content = new FormUrlEncodedContent(new Dictionary<string, string>
        {
            ["client_id"] = settings.ClientId,
            ["client_secret"] = settings.ClientSecret,
            ["scope"] = GraphScope,
            ["grant_type"] = "client_credentials"
        });

        using var response = await httpClient.SendAsync(request, cancellationToken);
        var content = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new TitulacionException(
                TitulacionErrorCodes.TeamsEventoNoCreado,
                $"No se pudo autenticar con Microsoft Graph. Entra ID devolvio {(int)response.StatusCode}: {TrimForClient(content)}",
                502);
        }

        using var document = JsonDocument.Parse(content);
        var token = TryGetString(document.RootElement, "access_token");
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new TitulacionException(TitulacionErrorCodes.TeamsEventoNoCreado, "Entra ID no devolvio access_token para Microsoft Graph.", 502);
        }

        return token;
    }

    private object BuildEventPayload(TeamsCalendarEventRequest request, string timeZone)
    {
        var start = FormatGraphDateTime(request.Fecha, request.HoraInicio);
        var end = FormatGraphDateTime(request.Fecha, request.HoraFin);
        var attendees = request.AttendeeEmails
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .Select(x => x.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Select(email => new
            {
                emailAddress = new { address = email },
                type = "required"
            })
            .ToArray();

        return new
        {
            subject = request.Subject,
            body = new
            {
                contentType = "HTML",
                content = request.BodyHtml ?? "Examen complexivo INTEC"
            },
            start = new
            {
                dateTime = start,
                timeZone
            },
            end = new
            {
                dateTime = end,
                timeZone
            },
            location = new
            {
                displayName = "Microsoft Teams"
            },
            attendees,
            allowNewTimeProposals = false,
            isOnlineMeeting = true,
            onlineMeetingProvider = "teamsForBusiness"
        };
    }

    private ResolvedTeamsSettings ResolveSettings(string? organizerOverride)
    {
        var configured = options.Value;
        var tenantId = FirstValue(configured.TenantId, configuration["Titulacion:Teams:TenantId"], configuration["TENANT_ID"], configuration["AZURE_TENANT_ID"]);
        var clientId = FirstValue(configured.ClientId, configuration["Titulacion:Teams:ClientId"], configuration["CLIENT_ID"], configuration["AZURE_CLIENT_ID"]);
        var clientSecret = FirstValue(configured.ClientSecret, configuration["Titulacion:Teams:ClientSecret"], configuration["CLIENT_SECRET"], configuration["AZURE_CLIENT_SECRET"]);
        var organizer = FirstValue(organizerOverride, configured.OrganizerUser, configuration["Titulacion:Teams:OrganizerUser"], configuration["TEAMS_ORGANIZER_USER"], configuration["SENDER_EMAIL"]);
        var timeZone = FirstValue(configured.TimeZone, configuration["Titulacion:Teams:TimeZone"], configuration["TEAMS_TIME_ZONE"]) ?? "SA Pacific Standard Time";

        if (string.IsNullOrWhiteSpace(tenantId) || string.IsNullOrWhiteSpace(clientId) || string.IsNullOrWhiteSpace(clientSecret) || string.IsNullOrWhiteSpace(organizer))
        {
            throw new TitulacionException(
                TitulacionErrorCodes.TeamsConfigIncompleta,
                "Configure TenantId, ClientId, ClientSecret y OrganizerUser para crear eventos de Teams.",
                500);
        }

        return new ResolvedTeamsSettings(tenantId.Trim(), clientId.Trim(), clientSecret.Trim(), organizer.Trim(), timeZone.Trim());
    }

    private static string FormatGraphDateTime(DateOnly date, TimeOnly time) =>
        date.ToDateTime(time).ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);

    private static string? FirstValue(params string?[] values) =>
        values.FirstOrDefault(x => !string.IsNullOrWhiteSpace(x));

    private static string TrimForClient(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "sin detalle";
        }

        value = value.Replace(Environment.NewLine, " ", StringComparison.Ordinal).Trim();
        return value.Length <= 400 ? value : value[..400];
    }

    private static string? TryGetString(JsonElement root, string propertyName)
    {
        return root.TryGetProperty(propertyName, out var property) && property.ValueKind == JsonValueKind.String
            ? property.GetString()
            : null;
    }

    private static string? TryGetString(JsonElement root, string objectName, string propertyName)
    {
        return root.TryGetProperty(objectName, out var parent)
            && parent.ValueKind == JsonValueKind.Object
            && parent.TryGetProperty(propertyName, out var property)
            && property.ValueKind == JsonValueKind.String
                ? property.GetString()
                : null;
    }

    private sealed record ResolvedTeamsSettings(
        string TenantId,
        string ClientId,
        string ClientSecret,
        string OrganizerUser,
        string TimeZone);
}
