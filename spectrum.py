"""Named observation notions from equivio's strong and weak LTBTS spectra."""

from dataclasses import dataclass


INFTY = 2**31 - 1


@dataclass
class Spectrum:
    coordinates: tuple[str, ...]
    notions: list[tuple[str, tuple[int, ...]]]

    def dominates(self, stronger: str, weaker: str) -> bool:
        notions = dict(self.notions)
        left, right = notions[stronger], notions[weaker]
        if len(left) != len(right) or len(left) != len(self.coordinates):
            raise ValueError("Notion coordinates do not match the spectrum dimensions")
        return all(a >= b for a, b in zip(left, right))

    def pareto_front(self, reported: set[str]) -> set[str]:
        known = {name for name, _ in self.notions}
        return {
            name for name in reported
            if name not in known or not any(
                candidate in known and candidate != name
                and self.dominates(candidate, name) and not self.dominates(name, candidate)
                for candidate in reported
            )
        }

    def unmatched(self, reported: set[str], other: set[str]) -> set[str]:
        reported = self.pareto_front(reported)
        other = self.pareto_front(other)
        known = {name for name, _ in self.notions}
        return {
            name for name in reported - other
            if name not in known or not any(
                candidate in known and self.dominates(candidate, name)
                for candidate in other
            )
        }

    def missing_intermediates(
        self, reported: set[str], other: set[str], supported: set[str]
    ) -> set[str]:
        reported = self.pareto_front(reported)
        other = self.pareto_front(other)
        known = {name for name, _ in self.notions}
        return {
            name for name in supported & known
            if self.unmatched({name}, reported)
            and any(self.dominates(name, weaker) for weaker in reported if weaker in known)
            and any(self.dominates(stronger, name) for stronger in other if stronger in known)
        }


STRONG_SPECTRUM = Spectrum(
    coordinates=(
        "observationHeight", "conjunctionLevels", "revivalHeight",
        "positiveConjHeight", "negativeConjHeight", "negationLevels",
    ),
    notions=[
        ("enabledness", (1, 0, 0, 0, 0, 0)),
        ("trace", (INFTY, 0, 0, 0, 0, 0)),
        ("failure", (INFTY, 1, 0, 0, 1, 1)),
        ("revivals", (INFTY, 1, 1, 0, 1, 1)),
        ("readiness", (INFTY, 1, 1, 1, 1, 1)),
        ("failure-trace", (INFTY, INFTY, INFTY, 0, 1, 1)),
        ("ready-trace", (INFTY, INFTY, INFTY, 1, 1, 1)),
        ("impossible-future", (INFTY, 1, 0, 0, INFTY, 1)),
        ("possible-future", (INFTY, 1, INFTY, INFTY, INFTY, 1)),
        ("simulation", (INFTY, INFTY, INFTY, INFTY, 0, 0)),
        ("ready-simulation", (INFTY, INFTY, INFTY, INFTY, 1, 1)),
        ("2-nested-simulation", (INFTY, INFTY, INFTY, INFTY, INFTY, 1)),
        ("bisimulation", (INFTY, INFTY, INFTY, INFTY, INFTY, INFTY)),
    ],
)


WEAK_SPECTRUM = Spectrum(
    coordinates=(
        "observationHeight", "branchingConjunctionLevels", "unstableConjunctionLevels",
        "stableConjunctionLevels", "immediateConjunctionLevels", "positiveConjHeight",
        "positiveConjSecondaryHeight", "negativeConjHeight", "negationLevels",
    ),
    notions=[
        ("weak-enabledness", (1, 0, 0, 0, 0, 0, 0, 0, 0)),
        ("weak-trace", (INFTY, 0, 0, 0, 0, 0, 0, 0, 0)),
        ("weak-failure", (INFTY, 0, 1, 0, 0, 0, 0, 1, 1)),
        ("stable-failure", (INFTY, 0, 0, 1, 0, 0, 0, 1, 1)),
        ("weak-readiness", (INFTY, 0, 1, 0, 0, 1, 0, 1, 1)),
        ("stable-revivals", (INFTY, 0, 0, 1, 0, 1, 0, 1, 1)),
        ("stable-readiness", (INFTY, 0, 0, 1, 0, 1, 1, 1, 1)),
        ("stable-failure-trace", (INFTY, 0, 0, INFTY, 0, INFTY, 0, 1, 1)),
        ("stable-ready-trace", (INFTY, 0, 0, INFTY, 0, INFTY, 1, 1, 1)),
        ("s-impossible-future", (INFTY, 0, 0, 1, 0, 0, 0, INFTY, 1)),
        ("weak-impossible-future", (INFTY, 0, 1, 0, 0, 0, 0, INFTY, 1)),
        ("weak-possible-future", (INFTY, 0, 1, 0, 0, INFTY, 0, INFTY, 1)),
        ("weak-simulation", (INFTY, 0, INFTY, 0, 0, INFTY, 0, 0, 0)),
        ("eta-simulation", (INFTY, INFTY, INFTY, 0, 0, INFTY, 0, 0, 0)),
        ("weak-ready-simulation", (INFTY, 0, INFTY, 0, 0, INFTY, 0, 1, 1)),
        ("stable-simulation", (INFTY, 0, 0, INFTY, 0, INFTY, INFTY, 0, 1)),
        ("s-ready-simulation", (INFTY, 0, 0, INFTY, 0, INFTY, INFTY, 1, 1)),
        ("2-nested-weak-simulation", (INFTY, 0, INFTY, 0, 0, INFTY, 0, INFTY, 1)),
        ("contrasimulation", (INFTY, 0, INFTY, 0, 0, 0, 0, INFTY, INFTY)),
        ("stable-bisimulation", (INFTY, 0, 0, INFTY, 0, INFTY, INFTY, INFTY, INFTY)),
        ("weak-bisimulation", (INFTY, 0, INFTY, 0, 0, INFTY, 0, INFTY, INFTY)),
        ("delay-bisimulation", (INFTY, 0, INFTY, 0, INFTY, INFTY, 0, INFTY, INFTY)),
        ("sr-delay-bisimulation", (INFTY, 0, INFTY, INFTY, INFTY, INFTY, INFTY, INFTY, INFTY)),
        ("eta-bisimulation", (INFTY, INFTY, INFTY, 0, 0, INFTY, 0, INFTY, INFTY)),
        ("branching-bisimulation", (INFTY, INFTY, INFTY, 0, INFTY, INFTY, 0, INFTY, INFTY)),
        ("sr-branching-bisimulation", (INFTY, INFTY, INFTY, INFTY, INFTY, INFTY, INFTY, INFTY, INFTY)),
    ],
)


WEAK_COMPARISON_SPECTRUM = Spectrum(
    coordinates=("ordinary", "deltaMarked", *WEAK_SPECTRUM.coordinates),
    notions=[
        (name, (1, 0, *coordinates)) for name, coordinates in WEAK_SPECTRUM.notions
    ] + [
        (f"delta-{name}", (0, 1, *coordinates)) for name, coordinates in WEAK_SPECTRUM.notions
    ] + [
        (native, (0, 1, *dict(WEAK_SPECTRUM.notions)[name]))
        for native, name in (
            ("divergence-preserving-branching-bisimulation", "branching-bisimulation"),
            ("divergence-preserving-weak-bisimulation", "weak-bisimulation"),
            ("failures-divergence", "stable-failure"),
        )
    ],
)