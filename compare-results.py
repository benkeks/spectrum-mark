#!/usr/bin/env python3
"""Compare Pareto fronts of preorders from two result CSV files."""

import argparse
import csv
import sys

from spectrum import STRONG_SPECTRUM


def load_results(path):
    results = {}
    with open(path, newline="") as file:
        for row in csv.DictReader(file):
            pair = (row["left"], row["right"])
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
        print(f"  first only: {', '.join(sorted(first_only)) or '(none)'}")
        print(f"  second only: {', '.join(sorted(second_only)) or '(none)'}")
        print(f"  more precise: {more_precise}")
        if first_status == second_status == "ok":
            missing = STRONG_SPECTRUM.missing_intermediates(
                first_preorders, second_preorders, supported
            )
            if missing:
                warning = f"  INCONSISTENCY: first omitted supported notion(s): {', '.join(sorted(missing))}"
                print(f"\033[31m{warning}\033[0m" if sys.stdout.isatty() else warning)


if __name__ == "__main__":
    main()