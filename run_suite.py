#!/usr/bin/env python3
"""Run all tools and compare their freshly generated reports, starting from CSV inputs."""

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from compare_results import validate_report
from example import SUITE_DATASETS, add_input_arguments, directed_pairs, resolve_input
from run_equivio import validate_divergence_input


TOOLS = ("equivio", "mcrl2", "cadp")


def record_environment(output_dir, cadp_bin=None):
    root = Path(__file__).resolve().parent

    def capture(command):
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=15)
            return {"returncode": process.returncode, "output": (process.stdout + process.stderr).strip()}
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"error": str(error)}

    cadp_root = Path(os.environ.get("CADP", str(Path.home() / "Software" / "cadp")))
    cadp_bin = (cadp_bin or Path(os.environ.get("CADP_BIN", str(cadp_root / "bin.x64")))).expanduser().resolve()
    artifacts = [root / "build/mcrl2/stage/bin/ltscompare", cadp_bin / "bcg_cmp",
                 cadp_bin / "bcg_io", cadp_bin / "bisimulator.a"]
    artifacts.extend((root / "equivio/shared/target").glob("scala-*/shared-assembly-*.jar"))
    artifacts.extend(root.glob("*.py"))
    artifacts.extend(root.glob("*.sh"))
    hashes = {}
    for path in artifacts:
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[str(path)] = digest.hexdigest()
    cache = root / "build/mcrl2/CMakeCache.txt"
    settings = {}
    if cache.is_file():
        for line in cache.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key.split(":")[0] in {
                "CMAKE_BUILD_TYPE", "CMAKE_CXX_COMPILER", "CMAKE_CXX_FLAGS", "CMAKE_CXX_FLAGS_RELEASE",
            }:
                settings[key] = value
    repositories = {}
    for name, path in (("spectrum-mark", root), ("equivio", root / "equivio"), ("mcrl2", root / "mcrl2")):
        repositories[name] = {
            "revision": capture(["git", "-C", str(path), "rev-parse", "HEAD"]),
            "status": capture(["git", "-C", str(path), "status", "--porcelain"]),
        }
    metadata = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "python": sys.version,
        "repositories": repositories,
        "artifact_sha256": hashes,
        "mcrl2_build_settings": settings,
        "versions": {name: capture([shutil.which(name) or name, flag])
                     for name, flag in (("java", "-version"), ("cc", "--version"),
                                        (str(root / "build/mcrl2/stage/bin/ltscompare"), "--version"))},
    }
    (output_dir / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")


def run_dataset(csv_path, pairs, weak, output_dir, cadp_bin=None, divergences=None, benchmark_performance=False):
    if divergences is None:
        divergences = weak
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
    if benchmark_performance:
        options.append("--benchmark-performance")
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
        if benchmark_performance:
            validate_report(report, pairs=directed_pairs(pairs), expected_runs=5,
                            require_manifest=True, input_path=csv_path)
    record_environment(output_dir, cadp_bin)
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
                        help="Include the divergence track (already standard for weak datasets)")
    parser.add_argument("--cadp-bin", type=Path, help="Override the CADP binary directory")
    args = parser.parse_args()
    if args.divergences and not args.weak and (args.csv is not None or args.pair is not None):
        parser.error("--divergences requires --weak when selecting an input or pair")
    try:
        if args.csv is not None or args.pair is not None:
            csv_path, pairs = resolve_input(args.csv, args.pair, args.weak)
            datasets = [(csv_path, pairs, args.weak, args.weak or args.divergences)]
        else:
            examples = Path(__file__).resolve().parent / "examples"
            datasets = [
                (*resolve_input(examples / f"{name}.csv", pairs, weak), weak, divergences)
                for name, pairs, weak, divergences in SUITE_DATASETS
                if not args.weak or weak
            ]
        for csv_path, pairs, weak, divergences in datasets:
            run_dataset(csv_path, pairs, weak, args.output_dir, args.cadp_bin,
                        divergences=divergences or (args.divergences and weak),
                        benchmark_performance=args.benchmark_performance)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Suite failed: {error}\n")


if __name__ == "__main__":
    main()