#!/usr/bin/env python3
"""Run all tools and compare their freshly generated reports, starting from CSV inputs."""

import argparse
import csv
import subprocess
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

from example import add_input_arguments, resolve_input


TOOLS = ("equivio", "mcrl2", "cadp")


def run_dataset(csv_path, pairs, weak, output_dir, cadp_bin=None):
    root = Path(__file__).resolve().parent
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    options = ["--csv", str(csv_path), "--output-dir", str(output_dir)]
    if weak:
        options.append("--weak")
    for left, right in pairs:
        options.extend(("--pair", left, right))
    reports = {}
    for tool in TOOLS:
        command = [sys.executable, str(root / f"run_{tool}.py"), *options]
        if tool == "cadp" and cadp_bin is not None:
            command.extend(("--cadp-bin", str(cadp_bin.expanduser().resolve())))
        print(f"Running {tool}: {csv_path.name} ({'weak' if weak else 'strong'})", flush=True)
        subprocess.run(command, cwd=root, check=True)
        report = output_dir / f"{csv_path.stem}-{tool}.csv"
        reports[tool] = report
        with report.open(newline="") as result_file:
            statuses = Counter(row["status"] for row in csv.DictReader(result_file))
        print(f"{tool}: {dict(statuses)}; {report}", flush=True)
    for first, second in combinations(TOOLS, 2):
        comparison = output_dir / f"{csv_path.stem}-{first}-vs-{second}.txt"
        command = [sys.executable, str(root / "compare_results.py")]
        if weak:
            command.append("--weak")
        command.extend((str(reports[first]), str(reports[second])))
        with comparison.open("w") as result_file:
            subprocess.run(command, cwd=root, stdout=result_file, check=True)
        print(f"Comparison: {comparison}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_input_arguments(parser)
    parser.add_argument("--weak", action="store_true", help="Run only the weak example, or weak notions for --csv")
    parser.add_argument("--cadp-bin", type=Path, help="Override the CADP binary directory")
    args = parser.parse_args()
    try:
        if args.csv is not None or args.pair is not None or args.weak:
            csv_path, pairs = resolve_input(args.csv, args.pair, args.weak)
            datasets = [(csv_path, pairs, args.weak)]
        else:
            datasets = [(*resolve_input(weak=weak), weak) for weak in (False, True)]
        for csv_path, pairs, weak in datasets:
            run_dataset(csv_path, pairs, weak, args.output_dir, args.cadp_bin)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Suite failed: {error}\n")


if __name__ == "__main__":
    main()