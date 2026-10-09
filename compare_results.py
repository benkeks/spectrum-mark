#!/usr/bin/env python3
"""Compare Pareto fronts of preorders from two result CSV files."""

import argparse
import csv
import sys

from spectrum import STRONG_SPECTRUM, WEAK_SPECTRUM


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
        if {"equivalence", "equivalent"} <= fields:
            return {row.get("mode", "equivalence") for row in reader}
    return set()


def is_equivalence_report(path):
    return "equivalence" in report_modes(path)


def load_results(path):
    results = {}
    algorithms = {}
    outcomes = {}
    with open(path, newline="") as file:
        reader = csv.DictReader(file)
        fields = set(reader.fieldnames or ())
        if not {"left", "right", "status"} <= fields:
            raise ValueError(f"Missing pair or status columns in {path}")
        is_mcrl2 = "preorders" not in fields
        if is_mcrl2 and not {"equivalence", "equivalent"} <= fields:
            raise ValueError(f"Expected preorders or equivalence/equivalent columns in {path}")
        for row in reader:
            pair = (row["left"], row["right"])
            if is_mcrl2:
                equivalence = row["equivalence"]
                mode = row.get("mode", "equivalence")
                if mode not in ("equivalence", "preorder"):
                    raise ValueError(f"Invalid comparison mode {mode!r} in {path}")
                notion = mcrl2_notion(equivalence, mode)
                algorithm_key = (*pair, equivalence, mode)
                if algorithm_key in algorithms:
                    raise ValueError(f"Duplicate algorithm {algorithm_key} in {path}")
                algorithms[algorithm_key] = row["status"]
                notions, status = results.setdefault(pair, (set(), "ok"))
                if row["status"] != "ok":
                    results[pair] = (notions, row["status"] if status == "ok" else status)
                    continue
                equivalent = row["equivalent"].strip().lower()
                if equivalent not in ("true", "false"):
                    raise ValueError(f"Invalid equivalence result {equivalent!r} for {algorithm_key} in {path}")
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
            results[pair] = (notions, row["status"])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak", action="store_true", help="Use the weak spectrum (also detected from weak notion names)")
    parser.add_argument("first", help="First result CSV")
    parser.add_argument("second", help="Second result CSV")
    args = parser.parse_args()

    first = load_results(args.first)
    second = load_results(args.second)
    reported = set().union(*(notions for notions, status in (*first.values(), *second.values())))
    weak_names = {name for name, _ in WEAK_SPECTRUM.notions}
    weak = args.weak or bool(reported & weak_names) or any(
        name.startswith(("divergence-preserving-", "cadp-", "coupled-")) for name in reported
    )
    spectrum = WEAK_SPECTRUM if weak else STRONG_SPECTRUM
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
        if first_only and second_only:
            more_precise = "both"
        elif first_only:
            more_precise = "first"
        elif second_only:
            more_precise = "second"
        else:
            more_precise = "neither"
        print(f"{left},{right}")
        if first_status != "ok" or second_status != "ok":
            print(f"  status: first={first_status}, second={second_status}")
        print(f"  first only: {', '.join(sorted(first_only)) or '(none)'}")
        print(f"  second only: {', '.join(sorted(second_only)) or '(none)'}")
        print(f"  more precise: {more_precise}")
        if first_status == second_status == "ok" and not mixed_relations:
            missing = spectrum.missing_intermediates(
                first_preorders, second_preorders, supported
            )
            if missing:
                warning = f"  INCONSISTENCY: first omitted supported notion(s): {', '.join(sorted(missing))}"
                print(f"\033[31m{warning}\033[0m" if sys.stdout.isatty() else warning)


if __name__ == "__main__":
    main()