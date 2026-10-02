#!/usr/bin/env python3
"""Record mCRL2 strong-equivalence comparisons for the first LTBTS example."""

import csv
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from csv_to_aut import convert_csv_to_aut


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


def strong_equivalences(executable):
    help_text = subprocess.run(
        [str(executable), "--help-all"], capture_output=True, text=True, check=True
    ).stdout
    equivalence_help = help_text.split("--equivalence=", 1)[1].split("--in1=", 1)[0]
    names = re.findall(r"^\s+'([^']+)'", equivalence_help, re.MULTILINE)
    equivalences = [
        name for name in names
        if name == "bisim" or name.startswith("bisim-")
        or name in ("sim", "ready-sim", "trace")
    ]
    if not equivalences:
        raise RuntimeError("No strong equivalences found in ltscompare --help-all")
    return equivalences


def compare(executable, left_path, right_path, equivalence):
    started = time.perf_counter()
    process = subprocess.Popen(
        [str(executable), f"--equivalence={equivalence}", str(left_path), str(right_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        output, errors = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return time.perf_counter() - started, "", "timeout"

    elapsed = time.perf_counter() - started
    result = output.strip()
    if process.returncode or result not in ("true", "false"):
        print(
            f"{left_path.stem},{right_path.stem},{equivalence}: "
            f"{errors.strip()} {result}",
            file=sys.stderr,
        )
        return elapsed, "", "error"
    return elapsed, result, "ok"


def main():
    root = Path(__file__).resolve().parent
    subprocess.run(["bash", str(root / "build_mcrl2.sh")], cwd=root, check=True)
    csv_path = root / "examples" / "ltbts1.csv"
    convert_csv_to_aut(csv_path)
    executable = root / "build" / "mcrl2" / "stage" / "bin" / "ltscompare"
    equivalences = strong_equivalences(executable)
    aut_dir = csv_path.parent / "aut"
    aut_paths = {
        state: aut_dir / f"{csv_path.stem}_{state}.aut"
        for pair in PAIRS for state in pair
    }
    for aut_path in aut_paths.values():
        if not aut_path.is_file():
            raise FileNotFoundError(aut_path)

    report = root / "results" / "ltbts1-mcrl2.csv"
    report.parent.mkdir(exist_ok=True)
    with report.open("w", newline="") as result_file:
        writer = csv.writer(result_file)
        writer.writerow(("left", "right", "equivalence", "seconds", "equivalent", "status"))
        for left, right in PAIRS:
            for source, target in ((left, right), (right, left)):
                for equivalence in equivalences:
                    seconds, equivalent, status = compare(
                        executable, aut_paths[source], aut_paths[target], equivalence
                    )
                    writer.writerow((source, target, equivalence, f"{seconds:.6f}", equivalent, status))
                    result_file.flush()
                    print(
                        f"{source},{target},{equivalence}: {equivalent or status} "
                        f"({seconds:.6f}s)",
                        flush=True,
                    )


if __name__ == "__main__":
    main()