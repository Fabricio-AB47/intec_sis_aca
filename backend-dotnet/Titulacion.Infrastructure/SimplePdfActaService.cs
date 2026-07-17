using System.Text;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Infrastructure;

public sealed class SimplePdfActaService : IPdfActaGradoService
{
    public Task<byte[]> GenerateAsync(ActaGradoPdfDto dto, CancellationToken cancellationToken)
    {
        var lines = new List<string>
        {
            dto.NombreInstitucion,
            "ACTA DE GRADO",
            $"Numero de acta: {dto.NumeroActa}",
            $"Escuela: {dto.Escuela}",
            $"Ciudad y fecha: {dto.Ciudad}, {dto.FechaActa:yyyy-MM-dd} {dto.HoraActa:HH\\:mm}",
            $"Carrera: {dto.Carrera}",
            $"Modalidad: {dto.Modalidad}",
            dto.TextoVariable,
            $"Nota promedio asignaturas: {dto.NotaAsignaturas:N2} / Equivalencia 80%: {dto.EquivalenciaAsignaturas80:N2}",
            $"Nota proceso titulacion: {dto.NotaProcesoTitulacion:N2} / Equivalencia 20%: {dto.EquivalenciaTitulacion20:N2}",
            $"Nota final de grado: {dto.NotaFinalGrado:N2}",
            $"Autoridad academica: {dto.AutoridadAcademica}",
            $"Coordinador academico: {dto.CoordinadorAcademico}",
            $"Docente evaluador: {dto.DocenteEvaluador}",
            "Firmas:"
        };
        lines.AddRange(dto.Firmas.Select(f => $"{f.Cargo}: {f.Nombre}"));

        var content = new StringBuilder();
        content.AppendLine("BT");
        content.AppendLine("/F1 16 Tf");
        content.AppendLine("72 760 Td");
        foreach (var line in lines)
        {
            foreach (var segment in Wrap(RemoveDiacritics(line), 92))
            {
                content.Append('(').Append(Escape(segment)).AppendLine(") Tj");
                content.AppendLine("0 -18 Td");
            }
            content.AppendLine("0 -24 Td");
        }
        content.AppendLine("ET");

        var stream = content.ToString();
        var objects = new List<string>
        {
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            $"<< /Length {Encoding.ASCII.GetByteCount(stream)} >>\nstream\n{stream}endstream"
        };

        var pdf = new StringBuilder("%PDF-1.4\n");
        var offsets = new List<int> { 0 };
        foreach (var obj in objects.Select((value, index) => new { value, number = index + 1 }))
        {
            offsets.Add(Encoding.ASCII.GetByteCount(pdf.ToString()));
            pdf.Append(obj.number).Append(" 0 obj\n").Append(obj.value).Append("\nendobj\n");
        }

        var xref = Encoding.ASCII.GetByteCount(pdf.ToString());
        pdf.Append("xref\n0 ").Append(objects.Count + 1).Append('\n');
        pdf.Append("0000000000 65535 f \n");
        foreach (var offset in offsets.Skip(1))
        {
            pdf.Append(offset.ToString("0000000000")).Append(" 00000 n \n");
        }

        pdf.Append("trailer\n<< /Size ").Append(objects.Count + 1).Append(" /Root 1 0 R >>\n");
        pdf.Append("startxref\n").Append(xref).Append("\n%%EOF");
        return Task.FromResult(Encoding.ASCII.GetBytes(pdf.ToString()));
    }

    private static string Escape(string value) =>
        value.Replace("\\", "\\\\").Replace("(", "\\(").Replace(")", "\\)");

    private static IEnumerable<string> Wrap(string value, int length)
    {
        if (value.Length <= length)
        {
            yield return value;
            yield break;
        }

        var words = value.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var line = new StringBuilder();
        foreach (var word in words)
        {
            if (line.Length + word.Length + 1 > length)
            {
                yield return line.ToString();
                line.Clear();
            }
            if (line.Length > 0) line.Append(' ');
            line.Append(word);
        }
        if (line.Length > 0) yield return line.ToString();
    }

    private static string RemoveDiacritics(string value)
    {
        var normalized = value.Normalize(NormalizationForm.FormD);
        var builder = new StringBuilder();
        foreach (var ch in normalized)
        {
            var category = System.Globalization.CharUnicodeInfo.GetUnicodeCategory(ch);
            if (category != System.Globalization.UnicodeCategory.NonSpacingMark && ch <= 127)
            {
                builder.Append(ch);
            }
        }
        return builder.ToString();
    }
}
