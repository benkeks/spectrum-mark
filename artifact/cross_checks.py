#!/usr/bin/env python3
"""Reproduce the cross-checking table, with optional (possibly older) CADP."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_table import generate_latex
from compare_results import validate_report
from example import SUITE_DATASETS, directed_pairs, resolve_input
from run_cadp import cadp_environment
from run_suite import record_environment, run_dataset


def cadp_directory(mode):
    if mode == "off":
        return None
    directory = Path(os.environ.get("CADP_BIN", str(
        Path(os.environ.get("CADP", str(Path.home() / "Software/cadp"))) / "bin.x64"
    ))).expanduser().resolve()
    if mode == "auto" and not directory.exists() and not any(
        name in os.environ for name in ("CADP", "CADP_BIN")
    ):
        print("CADP not installed: skipping its checks; table cells will be N/A.", flush=True)
        return None
    cadp_environment(directory)
    return directory


def reproduce(output, full=False, cadp="auto"):
    directory = cadp_directory(cadp)
    output.mkdir(parents=True, exist_ok=True)
    warnings = []
    runs = 5 if full else 1
    for stem, selected_pairs, weak, divergences in SUITE_DATASETS:
        source, pairs = resolve_input(ROOT / "examples" / f"{stem}.csv", selected_pairs, weak)
        run_dataset(source, pairs, weak, output, benchmark_performance=full,
                    divergences=divergences, tools=("equivio", "mcrl2"))
        for marked in (False, True) if divergences else (False,):
            suffix = "-divergences" if marked else ""
            for tool in ("equivio", "mcrl2"):
                validate_report(output / f"{stem}-{tool}{suffix}.csv",
                                pairs=directed_pairs(pairs), expected_runs=runs,
                                require_manifest=True, input_path=source)
            if directory is None:
                continue
            command = [sys.executable, str(ROOT / "run_cadp.py"), "--csv", str(source),
                       "--output-dir", str(output), "--cadp-bin", str(directory)]
            for left, right in pairs:
                command.extend(("--pair", left, right))
            if weak:
                command.append("--weak")
            if marked:
                command.append("--divergences")
            if full:
                command.append("--benchmark-performance")
            subprocess.run(command, cwd=ROOT, check=True)
            report = output / f"{stem}-cadp{suffix}.csv"
            try:
                validate_report(report, pairs=directed_pairs(pairs), expected_runs=runs,
                                require_manifest=True, input_path=source)
            except ValueError as error:
                warning = f"CADP result is incomplete/inconsistent (older BISIMULATOR?): {error}"
                warnings.append(warning)
                print(warning, file=sys.stderr, flush=True)
            for tool in ("equivio", "mcrl2"):
                comparison = output / f"{stem}-{tool}{suffix}-vs-cadp{suffix}.txt"
                compare_command = [sys.executable, str(ROOT / "compare_results.py")]
                if weak:
                    compare_command.append("--weak")
                with comparison.open("w") as result:
                    subprocess.run([*compare_command, str(output / f"{stem}-{tool}{suffix}.csv"),
                                    str(report)], cwd=ROOT, stdout=result, check=True)
    record_environment(output, directory)
    (output / "benchmark.tex").write_text(generate_latex(output, ROOT / "examples"))
    (output / "validation.json").write_text(json.dumps({
        "runs": runs, "validated_tools": ["equivio", "mcrl2"],
        "cadp": "omitted" if directory is None else "warnings" if warnings else "validated",
        "warnings": warnings,
    }, indent=2) + "\n")
    print(f"Cross-check table: {output / 'benchmark.tex'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--full", action="store_true", help="Five shuffled repetitions, as in the paper")
    parser.add_argument("--cadp", choices=("auto", "off", "on"),
                        default=os.environ.get("CADP_MODE", "auto"))
    args = parser.parse_args()
    try:
        reproduce(args.output_dir.expanduser().resolve(), args.full, args.cadp)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Cross-checking failed: {error}\n")


if __name__ == "__main__":
    main()
