#!/usr/bin/env python3
"""Record strong or weak spectroscopy comparisons for the LTBTS examples."""

import argparse
import csv
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from csv_to_aut import parse_csv
from example import add_input_arguments, directed_pairs, resolve_input


def validate_divergence_input(csv_path):
    transitions, _ = parse_csv(csv_path)
    if any(transition["action"] == "\u03b4" for transition in transitions):
        raise ValueError("Divergence marking reserves the visible delta action")


def prepare_divergence_input(csv_path, output_path):
    validate_divergence_input(csv_path)
    transitions, meta = parse_csv(csv_path)
    graph_states = {
        transition[field] for transition in transitions for field in ("src", "tar")
    }
    sources = {transition["src"] for transition in transitions}
    if graph_states - sources:
        return csv_path
    states = graph_states | {entry["state_id"] for entry in meta}
    sink = max(states, default=-1) + 1
    with output_path.open("w", newline="") as result_file:
        writer = csv.writer(result_file)
        writer.writerows((row["src"], row["tar"], row["action"]) for row in transitions)
        writer.writerows((row["state_id"], row["state_name"], row["state_meta"]) for row in meta)
        writer.writerow((sink + 1, sink, "tau"))
    return output_path


def compare(jar_path, csv_path, left, right, weak=False, divergences=False):
    if divergences and not weak:
        raise ValueError("Divergence marking requires weak spectroscopy")
    command = ["java", "-jar", str(jar_path), "compare", str(csv_path), left, right]
    if not weak:
        command.append("--strong-game")
    if divergences:
        command.append("--divergences")
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
                text=True,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return time.perf_counter() - started, "", "timeout"

    elapsed = time.perf_counter() - started
    if process.returncode:
        print(f"{left},{right}: {output.strip()}", file=sys.stderr)
        return elapsed, "", "error"
    return elapsed, output.strip(), "ok"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak", action="store_true", help="Test weak notions on LTBTS2")
    parser.add_argument("--divergences", action="store_true",
                        help="Mark divergence with visible delta transitions (requires --weak)")
    add_input_arguments(parser)
    args = parser.parse_args()
    if args.divergences and not args.weak:
        parser.error("--divergences requires --weak")
    try:
        csv_path, pairs = resolve_input(args.csv, args.pair, args.weak)
        if args.divergences:
            validate_divergence_input(csv_path)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    root = Path(__file__).resolve().parent
    equiv_io = root / "equivio"
    subprocess.run(["sbt", "shared/assembly"], cwd=equiv_io, check=True)
    jars = list((equiv_io / "shared" / "target").glob("scala-*/shared-assembly-*.jar"))
    if len(jars) != 1:
        raise RuntimeError(f"Expected one shared assembly jar, found: {jars}")
    jar_path = jars[0]

    suffix = "equivio-divergences" if args.divergences else "equivio"
    spectrum = "weak-divergences" if args.divergences else "weak" if args.weak else "strong"
    report = args.output_dir / f"{csv_path.stem}-{suffix}.csv"
    report.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="spectrum-equivio-") as directory, \
            report.open("w", newline="") as result_file:
        compared_csv = prepare_divergence_input(csv_path, Path(directory) / csv_path.name) \
            if args.divergences else csv_path
        writer = csv.writer(result_file)
        writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status"))
        for source, target in directed_pairs(pairs):
            seconds, preorders, status = compare(
                jar_path, compared_csv, source, target, args.weak, args.divergences
            )
            writer.writerow((source, target, spectrum, f"{seconds:.3f}", preorders, status))
            result_file.flush()
            print(f"{source},{target}: {status} ({seconds:.3f}s)", flush=True)


if __name__ == "__main__":
    main()