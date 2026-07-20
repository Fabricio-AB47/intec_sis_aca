using Titulacion.Domain;

namespace Titulacion.Tests;

public sealed class CalculoNotasTitulacionTests
{
    [Fact]
    public void Defensa_calcula_equivalencias_y_nota_final()
    {
        var result = CalculoNotasTitulacion.CalcularDefensa(
            notaAsignaturas: 8.50m,
            promedioTrabajoEscrito: 8.00m,
            promedioDefensaOral: 9.00m);

        Assert.Equal(6.80m, result.EquivalenciaAsignaturas80);
        Assert.Equal(17.00m, result.NotaTitulacionSobre20);
        Assert.Equal(1.70m, result.EquivalenciaTitulacion20);
        Assert.Equal(8.50m, result.NotaFinal);
    }

    [Fact]
    public void Defensa_conserva_precision_y_redondea_nota_final_a_dos_decimales()
    {
        var result = CalculoNotasTitulacion.CalcularDefensa(
            notaAsignaturas: 9.47m,
            promedioTrabajoEscrito: 9.75m,
            promedioDefensaOral: 9.75m);

        Assert.Equal(7.576m, result.EquivalenciaAsignaturas80);
        Assert.Equal(19.50m, result.NotaTitulacionSobre20);
        Assert.Equal(1.950m, result.EquivalenciaTitulacion20);
        Assert.Equal(9.53m, result.NotaFinal);
    }

    [Fact]
    public void Defensa_promedia_tres_evaluadores_por_componente()
    {
        var trabajos = new[] { 9.50m, 9.75m, 10.00m };
        var defensas = new[] { 9.50m, 9.75m, 10.00m };

        var result = CalculoNotasTitulacion.CalcularDefensa(
            notaAsignaturas: 9.47m,
            promedioTrabajoEscrito: decimal.Round(trabajos.Average(), 2),
            promedioDefensaOral: decimal.Round(defensas.Average(), 2));

        Assert.Equal(9.75m, decimal.Round(trabajos.Average(), 2));
        Assert.Equal(19.50m, result.NotaTitulacionSobre20);
        Assert.Equal(9.53m, result.NotaFinal);
    }

    [Fact]
    public void Consolidacion_debe_bloquear_si_falta_un_evaluador()
    {
        var evaluadores = new[] { 1, 2 };

        Assert.False(TieneTresEvaluadores(evaluadores));
    }

    [Fact]
    public void Complexivo_convierte_nota_sobre_diez_a_sobre_veinte()
    {
        var result = CalculoNotasTitulacion.CalcularComplexivo(
            notaAsignaturas: 9.00m,
            promedioExamenComplexivo: 8.25m);

        Assert.Equal(7.20m, result.EquivalenciaAsignaturas80);
        Assert.Equal(16.50m, result.NotaTitulacionSobre20);
        Assert.Equal(1.65m, result.EquivalenciaTitulacion20);
        Assert.Equal(8.85m, result.NotaFinal);
    }

    [Fact]
    public void Complexivo_con_componente_oral_suma_componentes_sobre_veinte()
    {
        var result = CalculoNotasTitulacion.CalcularComplexivo(
            notaAsignaturas: 9.00m,
            promedioExamenComplexivo: 9.00m,
            promedioComponenteOral: 8.50m);

        Assert.Equal(7.20m, result.EquivalenciaAsignaturas80);
        Assert.Equal(17.50m, result.NotaTitulacionSobre20);
        Assert.Equal(1.75m, result.EquivalenciaTitulacion20);
        Assert.Equal(8.95m, result.NotaFinal);
    }

    [Fact]
    public void Rechaza_notas_fuera_de_rango()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            CalculoNotasTitulacion.CalcularComplexivo(10.50m, 8.00m));

        Assert.Throws<ArgumentOutOfRangeException>(() =>
            CalculoNotasTitulacion.CalcularComplexivo(9.00m, 8.00m, promedioComponenteOral: 10.50m));
    }

    private static bool TieneTresEvaluadores(IEnumerable<int> evaluadores) =>
        evaluadores.Distinct().Count() == 3;
}
