#!/usr/bin/env python3
"""Compare Pareto fronts of preorders from two result CSV files."""

import argparse
import csv
import math
import sys
from dataclasses import dataclass

from spectrum import STRONG_SPECTRUM, WEAK_COMPARISON_SPECTRUM, WEAK_SPECTRUM


def mcrl2_notion(equivalence, mode="equivalence"):
    cadp_preorders = {
        "bisim-bisimulator": "simulation",
        "weak-bisim-bisimulator": "weak-simulation",
        "branching-bisim-bisimulator": "cadp-branching-simulation",
        "cadp-taustar": "cadp-taustar-simulation",
        "cadp-safety": "cadp-taustar-simulation",
    }
    if mode == "preorder" and equivalence in cadp_preorders:
        return cadp_preorders[equivalence]
    if equivalence == "bisim" or equivalence.startswith("bisim-"):
        return "bisimulation"
    for prefix, notion in (
        ("branching-bisim", "branching-bisimulation"),
        ("dpbranching-bisim", "divergence-preserving-branching-bisimulation"),
        ("weak-bisim", "weak-bisimulation"),
        ("dpweak-bisim", "divergence-preserving-weak-bisimulation"),
    ):
        if equivalence == prefix or equivalence.startswith(prefix + "-"):
            return notion
    names = {
        "sim": "simulation", "ready-sim": "ready-simulation", "trace": "trace",
        "weak-trace": "weak-trace", "coupled-sim": "coupled-simulation",
        "cadp-taustar": "cadp-taustar", "cadp-safety": "cadp-safety",
        "trace-ac": "trace", "weak-trace-ac": "weak-trace",
        "failures": "failure", "weak-failures": "stable-failure",
        "failures-divergence": "failures-divergence",
        "impossible-futures": "impossible-future",
    }
    if equivalence not in names:
        raise ValueError(f"Unsupported equivalence: {equivalence}")
    return names[equivalence]


def report_modes(path):
    with open(path, newline="") as file:
        reader = csv.DictReader(file)
        fields = set(reader.fieldnames or ())
        if "preorders" in fields:
            return {"preorder"}
        if {"equivalence", "mode", "equivalent"} <= fields:
            return {row["mode"] for row in reader}
    return set()


def is_equivalence_report(path):
    return "equivalence" in report_modes(path)


def report_spectra(path):
    with open(path, newline="") as file:
        reader = csv.DictReader(file)
        if "spectrum" in (reader.fieldnames or ()):
            return {row["spectrum"] for row in reader}
    return set()


@dataclass
class SpectroscopyCost:
    supported: int
    decided: int
    seconds: float

    @property
    def complete(self):
        return self.decided == self.supported


def load_report(path):
    results = {}
    costs = {}
    algorithms = {}
    outcomes = {}
    checks = {}
    with open(path, newline="") as file:
        reader = csv.DictReader(file)
        fields = set(reader.fieldnames or ())
        if not {"left", "right", "seconds", "status"} <= fields:
            raise ValueError(f"Missing pair, seconds or status columns in {path}")
        is_mcrl2 = "preorders" not in fields
        if is_mcrl2 and not {"equivalence", "mode", "equivalent"} <= fields:
            raise ValueError(f"Expected preorders or equivalence/mode/equivalent columns in {path}")
        if not is_mcrl2 and "spectrum" not in fields:
            raise ValueError(f"Missing spectrum column in {path}")
        for row in reader:
            pair = (row["left"], row["right"])
            seconds = float(row["seconds"])
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError(f"Invalid elapsed time {row['seconds']!r} for {pair} in {path}")
            if is_mcrl2:
                equivalence = row["equivalence"]
                mode = row["mode"]
                if mode not in ("equivalence", "preorder"):
                    raise ValueError(f"Invalid comparison mode {mode!r} in {path}")
                notion = mcrl2_notion(equivalence, mode)
                algorithm_key = (*pair, equivalence, mode)
                if algorithm_key in algorithms:
                    raise ValueError(f"Duplicate algorithm {algorithm_key} in {path}")
                algorithms[algorithm_key] = row["status"]
                notion_checks = checks.setdefault(pair, {}).setdefault(notion, {})
                mode_checks = notion_checks.setdefault(mode, [])
                notions, status = results.setdefault(pair, (set(), "ok"))
                if row["status"] != "ok":
                    results[pair] = (notions, row["status"] if status == "ok" else status)
                    continue
                equivalent = row["equivalent"].strip().lower()
                if equivalent not in ("true", "false"):
                    raise ValueError(f"Invalid equivalence result {equivalent!r} for {algorithm_key} in {path}")
                mode_checks.append(seconds)
                notion_key = (*pair, notion, mode)
                answers = outcomes.setdefault(notion_key, set())
                answers.add(equivalent)
                if len(answers) > 1:
                    notions.discard(notion)
                    results[pair] = (notions, "conflict")
                    print(f"Conflicting algorithm results for {notion_key} in {path}", file=sys.stderr)
                    continue
                if equivalent == "true":
                    notions.add(notion)
                continue
            if pair in results:
                raise ValueError(f"Duplicate pair {pair} in {path}")
            notions = {name.strip() for name in row["preorders"].split(",") if name.strip()}
            if row["spectrum"] not in ("strong", "weak", "weak-divergences"):
                raise ValueError(f"Invalid spectrum {row['spectrum']!r} in {path}")
            if row["spectrum"] == "weak-divergences":
                notions = {f"delta-{name}" for name in notions}
            results[pair] = (notions, row["status"])
            supported = len(STRONG_SPECTRUM.notions if row["spectrum"] == "strong" else WEAK_SPECTRUM.notions)
            costs[pair] = SpectroscopyCost(supported, supported if row["status"] == "ok" else 0,
                                           seconds if row["status"] == "ok" else 0.0)
    for pair, notion_checks in checks.items():
        decided = 0
        seconds = 0.0
        for notion, modes in notion_checks.items():
            conflicting = any(len(outcomes.get((*pair, notion, mode), set())) > 1 for mode in modes)
            if conflicting:
                results[pair][0].discard(notion)
                continue
            mode = "preorder" if "preorder" in modes else "equivalence"
            if modes[mode]:
                decided += 1
                seconds += min(modes[mode])
        costs[pair] = SpectroscopyCost(len(notion_checks), decided, seconds)
    return results, costs


def load_results(path):
    return load_report(path)[0]


def format_cost(cost):
    if cost is None:
        return "missing"
    if cost.complete:
        return f"{cost.seconds:.6f}s; notions decided: {cost.decided}/{cost.supported}"
    return (f"incomplete; notions decided: {cost.decided}/{cost.supported}; "
            f"decided-notion subtotal: {cost.seconds:.6f}s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak", action="store_true", help="Use the weak spectrum (also detected from weak notion names)")
    parser.add_argument("first", help="First result CSV")
    parser.add_argument("second", help="Second result CSV")
    args = parser.parse_args()

    first, first_costs = load_report(args.first)
    second, second_costs = load_report(args.second)
    first_spectra, second_spectra = report_spectra(args.first), report_spectra(args.second)
    different_families = ("weak-divergences" in first_spectra) != ("weak-divergences" in second_spectra)
    reported = set().union(*(notions for notions, status in (*first.values(), *second.values())))
    weak_names = {name for name, _ in WEAK_SPECTRUM.notions}
    weak = args.weak or bool((first_spectra | second_spectra) & {"weak", "weak-divergences"}) or bool(reported & weak_names) or any(
        name.startswith(("divergence-preserving-", "cadp-", "coupled-", "delta-")) for name in reported
    )
    spectrum = WEAK_COMPARISON_SPECTRUM if weak else STRONG_SPECTRUM
    if "weak-divergences" in first_spectra | second_spectra:
        print("Note: delta-marked weak notions are separate from ordinary weak and native "
              "divergence-preserving notions; no cross-family equivalence is assumed.")
    mixed_relations = (report_modes(args.first) | report_modes(args.second)) == {"equivalence", "preorder"}
    if mixed_relations:
        print("Note: comparing symmetric equivalences with directional preorders; "
              "differences do not necessarily indicate inconsistencies.")
    supported = set().union(*(notions for notions, status in first.values() if status == "ok"))
    for left, right in dict.fromkeys((*first, *second)):
        first_preorders, first_status = first.get((left, right), (set(), "missing"))
        second_preorders, second_status = second.get((left, right), (set(), "missing"))
        first_only = spectrum.unmatched(first_preorders, second_preorders)
        second_only = spectrum.unmatched(second_preorders, first_preorders)
        if different_families:
            more_precise = "not comparable (different spectrum families)"
        elif first_only and second_only:
            more_precise = "both"
        elif first_only:
            more_precise = "first"
        elif second_only:
            more_precise = "second"
        else:
            more_precise = "neither"
        print(f"{left},{right}")
        print(f"  first spectroscopy: {format_cost(first_costs.get((left, right)))}")
        print(f"  second spectroscopy: {format_cost(second_costs.get((left, right)))}")
        if first_status != "ok" or second_status != "ok":
            print(f"  status: first={first_status}, second={second_status}")
        print(f"  first only: {', '.join(sorted(first_only)) or '(none)'}")
        print(f"  second only: {', '.join(sorted(second_only)) or '(none)'}")
        print(f"  more precise: {more_precise}")
        if first_status == second_status == "ok" and not mixed_relations and not different_families:
            missing = spectrum.missing_intermediates(
                first_preorders, second_preorders, supported
            )
            if missing:
                warning = f"  INCONSISTENCY: first omitted supported notion(s): {', '.join(sorted(missing))}"
                print(f"\033[31m{warning}\033[0m" if sys.stdout.isatty() else warning)


if __name__ == "__main__":
    main()