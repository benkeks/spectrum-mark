#!/usr/bin/env python3
"""Record mCRL2 strong or weak relation comparisons for the LTBTS examples."""

import argparse
import csv
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from example import add_input_arguments, directed_pairs, prepare_auts, resolve_input


def available_equivalences(executable, weak=False):
    help_text = subprocess.run(
        [str(executable), "--help-all"], capture_output=True, text=True, check=True
    ).stdout
    equivalence_help = help_text.split("--equivalence=", 1)[1].split("--in1=", 1)[0]
    names = re.findall(r"^\s+'([^']+)'", equivalence_help, re.MULTILINE)
    strong = {
        name for name in names
        if name == "bisim" or name.startswith("bisim-")
        or name in ("sim", "ready-sim", "trace")
    }
    equivalences = [name for name in names if name != "none" and (name not in strong if weak else name in strong)]
    if not equivalences:
        raise RuntimeError("No matching equivalences found in ltscompare --help-all")
    return equivalences


def available_preorders(executable):
    help_text = subprocess.run(
        [str(executable), "--help-all"], capture_output=True, text=True, check=True
    ).stdout
    preorder_help = help_text.split("--preorder=", 1)[1].split("--strategy=", 1)[0]
    return set(re.findall(r"^\s+'([^']+)'", preorder_help, re.MULTILINE)) - {"unknown"}


def available_comparisons(executable, weak=False):
    equivalences = available_equivalences(executable, weak)
    preorders = available_preorders(executable)
    weak_preorders = {
        name for name in preorders
        if name.startswith("weak-") or name in ("failures-divergence", "coupled-sim")
    }
    selected = weak_preorders if weak else preorders - weak_preorders
    return [(name, "equivalence") for name in equivalences] + [
        (name, "preorder") for name in sorted(selected)
    ]


def compare(executable, left_path, right_path, equivalence, weak=False, mode="equivalence"):
    if mode not in ("equivalence", "preorder"):
        raise ValueError(f"Unknown comparison mode: {mode}")
    command = [str(executable), f"--{mode}={equivalence}"]
    if weak:
        command.append("--tau=i")
    command.extend((str(left_path), str(right_path)))
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak", action="store_true", help="Test weak notions on LTBTS2")
    add_input_arguments(parser)
    args = parser.parse_args()
    try:
        csv_path, pairs = resolve_input(args.csv, args.pair, args.weak)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    root = Path(__file__).resolve().parent
    subprocess.run(["bash", str(root / "build_mcrl2.sh")], cwd=root, check=True)
    aut_paths = prepare_auts(csv_path, pairs)
    executable = root / "build" / "mcrl2" / "stage" / "bin" / "ltscompare"
    comparisons = available_comparisons(executable, args.weak)
    report = args.output_dir / f"{csv_path.stem}-mcrl2.csv"
    report.parent.mkdir(exist_ok=True)
    with report.open("w", newline="") as result_file:
        writer = csv.writer(result_file)
        writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status"))
        for source, target in directed_pairs(pairs):
            for equivalence, mode in comparisons:
                seconds, equivalent, status = compare(
                    executable, aut_paths[source], aut_paths[target], equivalence, args.weak, mode
                )
                writer.writerow((source, target, equivalence, mode, f"{seconds:.6f}", equivalent, status))
                result_file.flush()
                print(
                    f"{source},{target},{equivalence},{mode}: {equivalent or status} "
                    f"({seconds:.6f}s)",
                    flush=True,
                )


if __name__ == "__main__":
    main()