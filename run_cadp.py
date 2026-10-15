#!/usr/bin/env python3
"""Record CADP strong or weak relation comparisons for the LTBTS examples."""

import argparse
import csv
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from csv_to_aut import generate_aut, parse_csv
from example import add_input_arguments, comparison_runs, prepare_auts, resolve_input, write_report_manifest


EQUIVALENCES = ("bisim-bcg-cmp", "bisim-bisimulator", "trace")
WEAK_EQUIVALENCES = (
    "branching-bisim-bcg-cmp", "dpbranching-bisim-bcg-cmp", "weak-bisim-bcg-cmp",
    "branching-bisim-bisimulator", "weak-bisim-bisimulator",
    "cadp-taustar", "cadp-safety", "weak-trace",
)
CHECKERS = {
    "bisim-bcg-cmp": ("bcg_cmp", "-strong"),
    "bisim-bisimulator": ("bisimulator", "-strong"),
    "trace": ("bisimulator", "-trace"),
    "branching-bisim-bcg-cmp": ("bcg_cmp", "-branching"),
    "dpbranching-bisim-bcg-cmp": ("bcg_cmp", "-divbranching"),
    "weak-bisim-bcg-cmp": ("bcg_cmp", "-observational"),
    "branching-bisim-bisimulator": ("bisimulator", "-branching"),
    "weak-bisim-bisimulator": ("bisimulator", "-observational"),
    "cadp-taustar": ("bisimulator", "-taustar"),
    "cadp-safety": ("bisimulator", "-safety"),
    "weak-trace": ("bisimulator", "-weaktrace"),
}


def available_comparisons(weak=False, divergences=False):
    if divergences and not weak:
        raise ValueError("Divergence comparisons require weak mode")
    equivalences = WEAK_EQUIVALENCES if weak else EQUIVALENCES
    equivalences = [name for name in equivalences if name.startswith("dpbranching-bisim") == divergences]
    return [(name, "equivalence") for name in equivalences] + [
        (name, "preorder") for name in equivalences
        if CHECKERS[name][0] == "bisimulator"
    ]


def write_cadp_aut(path, transitions, initial_state):
    states = {transition[field] for transition in transitions for field in ("src", "tar")}
    state_ids = {
        state: index for index, state in enumerate(
            [initial_state, *sorted(states - {initial_state})]
        )
    }
    remapped = [
        {"src": state_ids[transition["src"]], "tar": state_ids[transition["tar"]],
         "action": transition["action"]}
        for transition in transitions
    ]
    path.write_text(generate_aut(
        remapped, {"state_id": 0, "state_name": path.stem}, path.stem
    ))


def cadp_environment(bin_dir):
    cadp_dir = bin_dir.parent
    required = (bin_dir / "bcg_io", bin_dir / "bcg_cmp", cadp_dir / "com" / "bcg_open")
    for executable in required:
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"CADP executable not found or not executable: {executable}")
    if not (bin_dir / "bisimulator.a").is_file():
        raise ValueError(f"CADP BISIMULATOR archive not found: {bin_dir / 'bisimulator.a'}")
    environment = os.environ.copy()
    environment["CADP"] = str(cadp_dir)
    environment["PATH"] = os.pathsep.join(
        (str(bin_dir), str(cadp_dir / "com"), environment.get("PATH", ""))
    )
    return environment


def compare(bin_dir, left_path, right_path, equivalence, environment, work_dir, mode="equivalence"):
    if mode not in ("equivalence", "preorder"):
        raise ValueError(f"Unknown comparison mode: {mode}")
    checker, relation = CHECKERS[equivalence]
    if checker == "bcg_cmp":
        if mode != "equivalence":
            raise ValueError("bcg_cmp supports equivalence comparisons only")
        command = [str(bin_dir / "bcg_cmp"), relation, str(left_path), str(right_path)]
    else:
        command = [
            str(bin_dir.parent / "com" / "bcg_open"), str(left_path),
            str(bin_dir / "bisimulator.a"), relation,
            "-smaller" if mode == "preorder" else "-equal", str(right_path),
        ]
    started = time.perf_counter()
    process = subprocess.Popen(
        command, cwd=work_dir, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        output, errors = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return time.perf_counter() - started, "", "timeout"

    elapsed = time.perf_counter() - started
    answers = [line.strip().lower() for line in output.splitlines()
               if line.strip().lower() in ("true", "false")]
    if process.returncode or len(answers) != 1:
        print(
            f"{left_path.stem},{right_path.stem},{equivalence}: "
            f"{errors.strip()} {output.strip()}", file=sys.stderr,
        )
        return elapsed, "", "error"
    return elapsed, answers[0], "ok"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak", action="store_true", help="Test weak notions on LTBTS2")
    parser.add_argument("--divergences", action="store_true",
                        help="Run only divergence-sensitive relations (requires --weak)")
    add_input_arguments(parser)
    default_root = Path(os.environ.get("CADP", str(Path.home() / "Software" / "cadp")))
    parser.add_argument(
        "--cadp-bin", type=Path,
        default=Path(os.environ.get("CADP_BIN", str(default_root / "bin.x64"))),
        help="CADP binary directory (default: CADP_BIN, $CADP/bin.x64, or ~/Software/cadp/bin.x64)",
    )
    args = parser.parse_args()
    if args.divergences and not args.weak:
        parser.error("--divergences requires --weak")
    try:
        csv_path, pairs = resolve_input(args.csv, args.pair, args.weak)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    comparisons = available_comparisons(args.weak, args.divergences)
    bin_dir = args.cadp_bin.expanduser().resolve()
    try:
        environment = cadp_environment(bin_dir)
    except ValueError as error:
        parser.error(str(error))

    root = Path(__file__).resolve().parent
    aut_paths = prepare_auts(csv_path, pairs)
    transitions, meta = parse_csv(csv_path)
    initial_states = {entry["state_name"]: entry["state_id"] for entry in meta}
    with tempfile.TemporaryDirectory(prefix="spectrum-cadp-") as directory:
        work_dir = Path(directory)
        bcg_paths = {}
        for state, aut_path in aut_paths.items():
            cadp_aut_path = work_dir / aut_path.name
            write_cadp_aut(cadp_aut_path, transitions, initial_states[state])
            bcg_path = work_dir / f"{csv_path.stem}_{state}.bcg"
            subprocess.run(
                [str(bin_dir / "bcg_io"), "-aldebaran", str(cadp_aut_path), "-bcg", str(bcg_path)],
                cwd=work_dir, env=environment, check=True, timeout=30,
            )
            bcg_paths[state] = bcg_path

        suffix = "cadp-divergences" if args.divergences else "cadp"
        report = args.output_dir / f"{csv_path.stem}-{suffix}.csv"
        report.parent.mkdir(exist_ok=True)
        write_report_manifest(report, csv_path, pairs, args.weak, args.divergences,
                      args.benchmark_performance, comparisons)
        with report.open("w", newline="") as result_file:
            writer = csv.writer(result_file)
            writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status", "run"))
            for run, source, target, comparison in comparison_runs(pairs, comparisons, args.benchmark_performance):
                equivalence, mode = comparison
                seconds, equivalent, status = compare(
                    bin_dir, bcg_paths[source], bcg_paths[target],
                    equivalence, environment, work_dir, mode,
                )
                writer.writerow((source, target, equivalence, mode, f"{seconds:.6f}", equivalent, status, run))
                result_file.flush()
                print(
                    f"run {run}: {source},{target},{equivalence},{mode}: {equivalent or status} "
                    f"({seconds:.6f}s)", flush=True,
                )


if __name__ == "__main__":
    main()