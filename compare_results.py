#!/usr/bin/env python3
"""Compare Pareto fronts of preorders from two result CSV files."""

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from statistics import median

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


def notion_family(notion):
    if notion.startswith(("delta-", "divergence-preserving-")) or notion == "failures-divergence":
        return "weak-divergences"
    if notion in dict(STRONG_SPECTRUM.notions):
        return "strong"
    return "weak"


def decision_mode(notion, mode):
    if notion == "bisimulation" or notion.endswith("-bisimulation"):
        return "equivalence"
    return mode


def notion_implies(stronger, weaker, family):
    if stronger == weaker:
        return True
    if family == "strong":
        spectrum = STRONG_SPECTRUM
    elif family in ("weak", "weak-divergences"):
        spectrum = WEAK_COMPARISON_SPECTRUM
    else:
        return False
    known = dict(spectrum.notions)
    return stronger in known and weaker in known and spectrum.dominates(stronger, weaker)


def load_report_details(path):
    results = {}
    costs = {}
    decisions = {}
    algorithms = {}
    outcomes = {}
    checks = {}
    equivio_rows = {}
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
            try:
                run = int(row.get("run", "1"))
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid run identifier for {pair} in {path}") from error
            if not 1 <= run <= 5:
                raise ValueError(f"Invalid run identifier {run} for {pair} in {path}")
            seconds = float(row["seconds"])
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError(f"Invalid elapsed time {row['seconds']!r} for {pair} in {path}")
            if is_mcrl2:
                equivalence = row["equivalence"]
                mode = row["mode"]
                if mode not in ("equivalence", "preorder"):
                    raise ValueError(f"Invalid comparison mode {mode!r} in {path}")
                notion = mcrl2_notion(equivalence, mode)
                algorithm_key = (*pair, equivalence, mode, run)
                if algorithm_key in algorithms:
                    raise ValueError(f"Duplicate algorithm {algorithm_key} in {path}")
                algorithms[algorithm_key] = row["status"]
                notion_checks = checks.setdefault(pair, {}).setdefault(notion, {})
                mode_checks = notion_checks.setdefault(mode, {})
                samples = mode_checks.setdefault(equivalence, [])
                notions, status = results.setdefault(pair, (set(), "ok"))
                if row["status"] != "ok":
                    results[pair] = (notions, row["status"] if status == "ok" else status)
                    continue
                equivalent = row["equivalent"].strip().lower()
                if equivalent not in ("true", "false"):
                    raise ValueError(f"Invalid equivalence result {equivalent!r} for {algorithm_key} in {path}")
                samples.append(seconds)
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
            notions = {name.strip() for name in row["preorders"].split(",") if name.strip()}
            if row["spectrum"] not in ("strong", "weak", "weak-divergences"):
                raise ValueError(f"Invalid spectrum {row['spectrum']!r} in {path}")
            algorithm_key = (*pair, row["spectrum"], run)
            if algorithm_key in algorithms:
                raise ValueError(f"Duplicate pair/run {algorithm_key} in {path}")
            algorithms[algorithm_key] = row["status"]
            rows = equivio_rows.setdefault(pair, [])
            if rows and rows[0][0]["spectrum"] != row["spectrum"]:
                raise ValueError(f"Different spectrum families for {pair} in {path}")
            if row["spectrum"] == "weak-divergences":
                notions = {f"delta-{name}" for name in notions}
            rows.append((row, seconds, notions))
    for pair, rows in equivio_rows.items():
        family = rows[0][0]["spectrum"]
        spectrum = STRONG_SPECTRUM if family == "strong" else WEAK_SPECTRUM
        supported = len(spectrum.notions)
        names = {name for name, _ in spectrum.notions}
        if family == "weak-divergences":
            names = {f"delta-{name}" for name in names}
        names.update(name for _, _, notions in rows for name in notions)
        answers = {name: set() for name in names}
        frontier = set()
        samples = []
        status = next((row["status"] for row, _, _ in rows if row["status"] != "ok"), "ok")
        for row, seconds, notions in rows:
            if row["status"] != "ok":
                continue
            samples.append(seconds)
            frontier.update(notions)
            for name in names:
                answers[name].add(any(notion_implies(stronger, name, family) for stronger in notions))
        conflicting = any(len(values) > 1 for values in answers.values())
        if conflicting:
            status = "conflict"
            frontier.clear()
            print(f"Conflicting spectroscopy results for {pair} in {path}", file=sys.stderr)
        results[pair] = (frontier, status)
        costs[pair] = SpectroscopyCost(supported, supported if samples and not conflicting else 0,
                                      median(samples) if samples and not conflicting else 0.0)
        decisions[pair] = {
            (family, name, decision_mode(name, "preorder")):
                next(iter(values)) if len(values) == 1 and not conflicting else None
            for name, values in answers.items()
        }
    for pair, notion_checks in checks.items():
        decided = 0
        seconds = 0.0
        pair_decisions = decisions.setdefault(pair, {})
        for notion, modes in notion_checks.items():
            conflicting = any(len(outcomes.get((*pair, notion, mode), set())) > 1 for mode in modes)
            for mode in modes:
                answers = outcomes.get((*pair, notion, mode), set())
                key = (notion_family(notion), notion, decision_mode(notion, mode))
                answer = next(iter(answers)) == "true" if len(answers) == 1 and not conflicting else None
                if key in pair_decisions and pair_decisions[key] != answer:
                    pair_decisions[key] = None
                else:
                    pair_decisions[key] = answer
            if conflicting:
                results[pair][0].discard(notion)
                continue
            mode = "preorder" if "preorder" in modes else "equivalence"
            timings = [median(samples) for samples in modes[mode].values() if samples]
            if timings:
                decided += 1
                seconds += min(timings)
        costs[pair] = SpectroscopyCost(len(notion_checks), decided, seconds)
    for (left, right), pair_decisions in decisions.items():
        reverse = decisions.get((right, left), {})
        for (family, notion, mode), answer in list(pair_decisions.items()):
            key = (family, notion, "equivalence")
            if mode != "preorder" or answer is None or key in pair_decisions:
                continue
            if notion not in dict(
                STRONG_SPECTRUM.notions if family == "strong" else WEAK_COMPARISON_SPECTRUM.notions
            ):
                continue
            reverse_answer = reverse.get((family, notion, mode))
            if answer is False or reverse_answer is False:
                pair_decisions[key] = False
            elif answer is True and reverse_answer is True:
                pair_decisions[key] = True
    return results, costs, decisions


def load_report(path):
    results, costs, _ = load_report_details(path)
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


def find_inconsistencies(decisions, other):
    inconsistencies = []
    for (family, notion, mode), answer in sorted(decisions.items()):
        if answer is not False:
            continue
        for (other_family, stronger, other_mode), other_answer in sorted(other.items()):
            if other_answer is not True or family != other_family:
                continue
            if mode != other_mode and (mode, other_mode) != ("preorder", "equivalence"):
                continue
            if notion_implies(stronger, notion, family):
                inconsistencies.append((notion, mode, stronger, other_mode))
                break
    return inconsistencies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak", action="store_true", help="Use the weak spectrum (also detected from weak notion names)")
    parser.add_argument("first", help="First result CSV")
    parser.add_argument("second", help="Second result CSV")
    args = parser.parse_args()

    first, first_costs, first_decisions = load_report_details(args.first)
    second, second_costs, second_decisions = load_report_details(args.second)
    first_spectra, second_spectra = report_spectra(args.first), report_spectra(args.second)
    first_families = {family for pair in first_decisions.values() for family, _, _ in pair}
    second_families = {family for pair in second_decisions.values() for family, _, _ in pair}
    different_families = bool(first_families and second_families and first_families != second_families)
    reported = set().union(*(notions for notions, status in (*first.values(), *second.values())))
    weak_names = {name for name, _ in WEAK_SPECTRUM.notions}
    weak = args.weak or bool((first_families | second_families) & {"weak", "weak-divergences"}) or bool(reported & weak_names) or any(
        name.startswith(("divergence-preserving-", "cadp-", "coupled-", "delta-")) for name in reported
    )
    spectrum = WEAK_COMPARISON_SPECTRUM if weak else STRONG_SPECTRUM
    if "weak-divergences" in first_families | second_families:
          print("Note: marked and native divergence-preserving bisimulations share notions "
              "under Spectrum II; ordinary weak notions and failures-divergence remain separate.")
    mixed_relations = (report_modes(args.first) | report_modes(args.second)) == {"equivalence", "preorder"}
    for left, right in dict.fromkeys((*first, *second)):
        first_preorders, first_status = first.get((left, right), (set(), "missing"))
        second_preorders, second_status = second.get((left, right), (set(), "missing"))
        first_only = spectrum.unmatched(first_preorders, second_preorders)
        second_only = spectrum.unmatched(second_preorders, first_preorders)
        if first_status == "missing" or second_status == "missing":
            more_precise = "not comparable (missing results)"
        elif different_families:
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
        pair = (left, right)
        for side, other_side, decisions, other in (
            ("first", "second", first_decisions.get(pair, {}), second_decisions.get(pair, {})),
            ("second", "first", second_decisions.get(pair, {}), first_decisions.get(pair, {})),
        ):
            for notion, mode, stronger, other_mode in find_inconsistencies(decisions, other):
                warning = (f"  INCONSISTENCY: {side} reports {notion} ({mode}) false, "
                           f"but {other_side} implies it via {stronger} ({other_mode})")
                print(f"\033[31m{warning}\033[0m" if sys.stdout.isatty() else warning)


if __name__ == "__main__":
    main()