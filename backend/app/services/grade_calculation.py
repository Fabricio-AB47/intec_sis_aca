from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


RegularPartial = Sequence[float | None]


@dataclass(frozen=True)
class RegularGradeCalculation:
    partials: tuple[float | None, float | None, float | None]
    final: float | None
    replacement: tuple[int, int] | None


@dataclass(frozen=True)
class HomologationGradeCalculation:
    components: tuple[float | None, float | None]
    final: float | None
    replacement: int | None


def _weighted_partial(partial: RegularPartial) -> float | None:
    if len(partial) != 3:
        raise ValueError("Cada parcial debe contener tareas, proyectos y examen")
    if any(value is None for value in partial):
        return None
    tareas, proyectos, examen = (float(value) for value in partial)
    return round((tareas * 0.30) + (proyectos * 0.30) + (examen * 0.40), 2)


def calculate_regular_grade_with_recovery(
    partials: Sequence[RegularPartial],
    recovery: float | None = None,
) -> RegularGradeCalculation:
    """Replace one lowest component grade, then calculate partials and final.

    Ties are deterministic: only the first lowest component in P1-to-P3 order is
    replaced. Recovery never fills an incomplete grade set or lowers a grade.
    """
    if len(partials) != 3:
        raise ValueError("La calificación regular debe contener tres parciales")

    adjusted = [list(partial) for partial in partials]
    for partial in adjusted:
        if len(partial) != 3:
            raise ValueError("Cada parcial debe contener tareas, proyectos y examen")

    replacement: tuple[int, int] | None = None
    all_components = [value for partial in adjusted for value in partial]
    if recovery is not None and all(value is not None for value in all_components):
        numeric_components = [float(value) for value in all_components]
        lowest_value = min(numeric_components)
        if float(recovery) > lowest_value:
            lowest_index = numeric_components.index(lowest_value)
            partial_index, component_index = divmod(lowest_index, 3)
            adjusted[partial_index][component_index] = float(recovery)
            replacement = (partial_index, component_index)

    calculated_partials = tuple(_weighted_partial(partial) for partial in adjusted)
    typed_partials = (
        calculated_partials[0],
        calculated_partials[1],
        calculated_partials[2],
    )
    if any(partial is None for partial in typed_partials):
        final = None
    else:
        final = round(sum(float(partial) for partial in typed_partials) / 3, 2)

    return RegularGradeCalculation(
        partials=typed_partials,
        final=final,
        replacement=replacement,
    )


def regular_final_with_recovery(
    partials: Sequence[RegularPartial],
    recovery: float | None = None,
) -> float | None:
    return calculate_regular_grade_with_recovery(partials, recovery).final


def calculate_homologation_grade_with_recovery(
    theory: float | None,
    practice: float | None,
    recovery: float | None = None,
) -> HomologationGradeCalculation:
    """Apply recovery to one lowest homologation component and calculate 40/60."""
    adjusted = [theory, practice]
    replacement: int | None = None
    if recovery is not None and all(value is not None for value in adjusted):
        numeric_components = [float(value) for value in adjusted]
        lowest_value = min(numeric_components)
        if float(recovery) > lowest_value:
            replacement = numeric_components.index(lowest_value)
            adjusted[replacement] = float(recovery)

    typed_components = (adjusted[0], adjusted[1])
    if any(value is None for value in typed_components):
        final = None
    else:
        final = round((float(typed_components[0]) * 0.40) + (float(typed_components[1]) * 0.60), 2)

    return HomologationGradeCalculation(
        components=typed_components,
        final=final,
        replacement=replacement,
    )
