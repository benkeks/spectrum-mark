#!/usr/bin/env python3
"""Record strong or weak spectroscopy comparisons for the LTBTS examples."""

import argparse
import csv
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from example import add_input_arguments, directed_pairs, resolve_input


def compare(jar_path, csv_path, left, right, weak=False):
    command = ["java", "-jar", str(jar_path), "compare", str(csv_path), left, right]
    if not weak:
        command.append("--strong-game")
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
    add_input_arguments(parser)
    args = parser.parse_args()
    try:
        csv_path, pairs = resolve_input(args.csv, args.pair, args.weak)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    root = Path(__file__).resolve().parent
    equiv_io = root / "equivio"
    subprocess.run(["sbt", "shared/assembly"], cwd=equiv_io, check=True)
    jars = list((equiv_io / "shared" / "target").glob("scala-*/shared-assembly-*.jar"))
    if len(jars) != 1:
        raise RuntimeError(f"Expected one shared assembly jar, found: {jars}")
    jar_path = jars[0]

    report = args.output_dir / f"{csv_path.stem}-equivio.csv"
    report.parent.mkdir(exist_ok=True)
    with report.open("w", newline="") as result_file:
        writer = csv.writer(result_file)
        writer.writerow(("left", "right", "seconds", "preorders", "status"))
        for source, target in directed_pairs(pairs):
            seconds, preorders, status = compare(jar_path, csv_path, source, target, args.weak)
            writer.writerow((source, target, f"{seconds:.3f}", preorders, status))
            result_file.flush()
            print(f"{source},{target}: {status} ({seconds:.3f}s)", flush=True)


if __name__ == "__main__":
    main()