#!/usr/bin/env python3
"""Record strong-game comparisons for the first LTBTS example."""

import csv
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


PAIRS = (
    ("L13", "R13"),
    ("L16", "R16"),
    ("L21", "R21"),
    ("L24", "R24"),
    ("L27", "R27"),
    ("L31", "R31"),
    ("L34", "R31"),
    ("L38", "R24"),
    ("L42", "R42"),
    ("L50", "R50"),
)


def compare(jar_path, csv_path, left, right):
    started = time.perf_counter()
    process = subprocess.Popen(
        ["java", "-jar", str(jar_path), "compare", str(csv_path), left, right, "--strong-game"],
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
    root = Path(__file__).resolve().parent
    csv_path = root / "examples" / "ltbts1.csv"
    equiv_io = root / "equiv-io"
    subprocess.run(["sbt", "shared/assembly"], cwd=equiv_io, check=True)
    jars = list((equiv_io / "shared" / "target").glob("scala-*/shared-assembly-*.jar"))
    if len(jars) != 1:
        raise RuntimeError(f"Expected one shared assembly jar, found: {jars}")
    jar_path = jars[0]

    report = root / "results" / "ltbts1-equivio.csv"
    report.parent.mkdir(exist_ok=True)
    with report.open("w", newline="") as result_file:
        writer = csv.writer(result_file)
        writer.writerow(("left", "right", "seconds", "preorders", "status"))
        for left, right in PAIRS:
            for source, target in ((left, right), (right, left)):
                seconds, preorders, status = compare(jar_path, csv_path, source, target)
                writer.writerow((source, target, f"{seconds:.3f}", preorders, status))
                result_file.flush()
                print(f"{source},{target}: {status} ({seconds:.3f}s)", flush=True)


if __name__ == "__main__":
    main()