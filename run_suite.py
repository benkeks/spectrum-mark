#!/usr/bin/env python3
"""Run all tools and compare their freshly generated reports, starting from CSV inputs."""

import argparse
import csv
import subprocess
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

from example import SUITE_DATASETS, add_input_arguments, resolve_input
from run_equivio import validate_divergence_input


TOOLS = ("equivio", "mcrl2", "cadp")


def run_dataset(csv_path, pairs, weak, output_dir, cadp_bin=None, divergences=False):
    if divergences:
        if not weak:
            raise ValueError("Divergence marking requires weak spectroscopy")
        validate_divergence_input(csv_path)
    root = Path(__file__).resolve().parent
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    options = ["--csv", str(csv_path), "--output-dir", str(output_dir)]
    if weak:
        options.append("--weak")
    for left, right in pairs:
        options.extend(("--pair", left, right))
    reports = {False: {}, True: {}}
    runs = [(tool, tool, False) for tool in TOOLS]
    if divergences:
        runs.extend((f"{tool}-divergences", tool, True) for tool in TOOLS)
    for report_name, tool, marked in runs:
        command = [sys.executable, str(root / f"run_{tool}.py"), *options]
        if marked:
            command.append("--divergences")
        if tool == "cadp" and cadp_bin is not None:
            command.extend(("--cadp-bin", str(cadp_bin.expanduser().resolve())))
        print(f"Running {report_name}: {csv_path.name} ({'weak' if weak else 'strong'})", flush=True)
        subprocess.run(command, cwd=root, check=True)
        report = output_dir / f"{csv_path.stem}-{report_name}.csv"
        reports[marked][tool] = report
        with report.open(newline="") as result_file:
            statuses = Counter(row["status"] for row in csv.DictReader(result_file))
        print(f"{report_name}: {dict(statuses)}; {report}", flush=True)
    for marked, group in reports.items():
        suffix = "-divergences" if marked else ""
        for first, second in combinations(group, 2):
            comparison = output_dir / f"{csv_path.stem}-{first}{suffix}-vs-{second}{suffix}.txt"
            command = [sys.executable, str(root / "compare_results.py")]
            if weak:
                command.append("--weak")
            command.extend((str(group[first]), str(group[second])))
            with comparison.open("w") as result_file:
                subprocess.run(command, cwd=root, stdout=result_file, check=True)
            print(f"Comparison: {comparison}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_input_arguments(parser)
    parser.add_argument("--weak", action="store_true", help="Run only weak datasets, or weak notions for --csv")
    parser.add_argument("--divergences", action="store_true",
                        help="Also run the divergence track for all three tools on weak datasets")
    parser.add_argument("--cadp-bin", type=Path, help="Override the CADP binary directory")
    args = parser.parse_args()
    if args.divergences and not args.weak and (args.csv is not None or args.pair is not None):
        parser.error("--divergences requires --weak when selecting an input or pair")
    try:
        if args.csv is not None or args.pair is not None:
            csv_path, pairs = resolve_input(args.csv, args.pair, args.weak)
            datasets = [(csv_path, pairs, args.weak, args.divergences)]
        else:
            examples = Path(__file__).resolve().parent / "examples"
            datasets = [
                (*resolve_input(examples / f"{name}.csv", pairs, weak), weak, divergences)
                for name, pairs, weak, divergences in SUITE_DATASETS
                if not args.weak or weak
            ]
        for csv_path, pairs, weak, divergences in datasets:
            run_dataset(csv_path, pairs, weak, args.output_dir, args.cadp_bin,
                        divergences=divergences or (args.divergences and weak))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Suite failed: {error}\n")


if __name__ == "__main__":
    main()