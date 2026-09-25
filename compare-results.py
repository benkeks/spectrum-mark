#!/usr/bin/env python3
"""Show literal preorder differences between two result CSV files."""

import argparse
import csv


def load_results(path):
    results = {}
    with open(path, newline="") as file:
        for row in csv.DictReader(file):
            pair = (row["left"], row["right"])
            if pair in results:
                raise ValueError(f"Duplicate pair {pair} in {path}")
            results[pair] = {name.strip() for name in row["preorders"].split(",") if name.strip()}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", help="First result CSV")
    parser.add_argument("second", help="Second result CSV")
    args = parser.parse_args()

    first = load_results(args.first)
    second = load_results(args.second)
    for left, right in dict.fromkeys((*first, *second)):
        first_only = first.get((left, right), set()) - second.get((left, right), set())
        second_only = second.get((left, right), set()) - first.get((left, right), set())
        print(f"{left},{right}")
        print(f"  first only: {', '.join(sorted(first_only)) or '(none)'}")
        print(f"  second only: {', '.join(sorted(second_only)) or '(none)'}")


if __name__ == "__main__":
    main()