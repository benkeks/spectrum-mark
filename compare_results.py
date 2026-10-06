#!/usr/bin/env python3
"""Compare Pareto fronts of preorders from two result CSV files."""

import argparse
import csv
import sys

from spectrum import STRONG_SPECTRUM


def mcrl2_notion(equivalence):
    if equivalence == "bisim" or equivalence.startswith("bisim-"):
        return "bisimulation"
    names = {"sim": "simulation", "ready-sim": "ready-simulation", "trace": "trace"}
    if equivalence not in names:
        raise ValueError(f"Unsupported mCRL2 equivalence: {equivalence}")
    return names[equivalence]


def is_equivalence_report(path):
    with open(path, newline="") as file:
        fields = set(csv.DictReader(file).fieldnames or ())
    return "preorders" not in fields and {"equivalence", "equivalent"} <= fields


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
                notion = mcrl2_notion(equivalence)
                algorithm_key = (*pair, equivalence)
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
                notion_key = (*pair, notion)
                if notion_key in outcomes and outcomes[notion_key] != equivalent:
                    raise ValueError(f"Conflicting algorithm results for {notion_key} in {path}")
                outcomes[notion_key] = equivalent
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
    parser.add_argument("first", help="First result CSV")
    parser.add_argument("second", help="Second result CSV")
    args = parser.parse_args()

    first = load_results(args.first)
    second = load_results(args.second)
    mixed_relations = is_equivalence_report(args.first) != is_equivalence_report(args.second)
    if mixed_relations:
        print("Note: comparing symmetric mCRL2 equivalences with directional preorders; "
              "differences do not necessarily indicate inconsistencies.")
    supported = set().union(*(notions for notions, status in first.values() if status == "ok"))
    for left, right in dict.fromkeys((*first, *second)):
        first_preorders, first_status = first.get((left, right), (set(), "missing"))
        second_preorders, second_status = second.get((left, right), (set(), "missing"))
        first_only = STRONG_SPECTRUM.unmatched(first_preorders, second_preorders)
        second_only = STRONG_SPECTRUM.unmatched(second_preorders, first_preorders)
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
            missing = STRONG_SPECTRUM.missing_intermediates(
                first_preorders, second_preorders, supported
            )
            if missing:
                warning = f"  INCONSISTENCY: first omitted supported notion(s): {', '.join(sorted(missing))}"
                print(f"\033[31m{warning}\033[0m" if sys.stdout.isatty() else warning)


if __name__ == "__main__":
    main()