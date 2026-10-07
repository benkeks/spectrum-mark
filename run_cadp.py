#!/usr/bin/env python3
"""Record CADP strong-equivalence comparisons for the first LTBTS example."""

import argparse
import csv
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from csv_to_aut import convert_csv_to_aut, generate_aut, parse_csv
from run_equivio import PAIRS


EQUIVALENCES = ("bisim-bcg-cmp", "bisim-bisimulator", "trace")


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


def compare(bin_dir, left_path, right_path, equivalence, environment, work_dir):
    if equivalence == "bisim-bcg-cmp":
        command = [str(bin_dir / "bcg_cmp"), "-strong", str(left_path), str(right_path)]
    else:
        relation = "-trace" if equivalence == "trace" else "-strong"
        command = [
            str(bin_dir.parent / "com" / "bcg_open"), str(left_path),
            str(bin_dir / "bisimulator.a"), relation, "-equal", str(right_path),
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
    default_root = Path(os.environ.get("CADP", str(Path.home() / "Software" / "cadp")))
    parser.add_argument(
        "--cadp-bin", type=Path,
        default=Path(os.environ.get("CADP_BIN", str(default_root / "bin.x64"))),
        help="CADP binary directory (default: CADP_BIN, $CADP/bin.x64, or ~/Software/cadp/bin.x64)",
    )
    args = parser.parse_args()
    bin_dir = args.cadp_bin.expanduser().resolve()
    try:
        environment = cadp_environment(bin_dir)
    except ValueError as error:
        parser.error(str(error))

    root = Path(__file__).resolve().parent
    csv_path = root / "examples" / "ltbts1.csv"
    convert_csv_to_aut(csv_path)
    transitions, meta = parse_csv(csv_path)
    initial_states = {entry["state_name"]: entry["state_id"] for entry in meta}
    with tempfile.TemporaryDirectory(prefix="spectrum-cadp-") as directory:
        work_dir = Path(directory)
        bcg_paths = {}
        for state in dict.fromkeys(state for pair in PAIRS for state in pair):
            aut_path = csv_path.parent / "aut" / f"{csv_path.stem}_{state}.aut"
            if not aut_path.is_file():
                raise FileNotFoundError(aut_path)
            cadp_aut_path = work_dir / aut_path.name
            write_cadp_aut(cadp_aut_path, transitions, initial_states[state])
            bcg_path = work_dir / f"{csv_path.stem}_{state}.bcg"
            subprocess.run(
                [str(bin_dir / "bcg_io"), "-aldebaran", str(cadp_aut_path), "-bcg", str(bcg_path)],
                cwd=work_dir, env=environment, check=True, timeout=30,
            )
            bcg_paths[state] = bcg_path

        report = root / "results" / "ltbts1-cadp.csv"
        report.parent.mkdir(exist_ok=True)
        with report.open("w", newline="") as result_file:
            writer = csv.writer(result_file)
            writer.writerow(("left", "right", "equivalence", "seconds", "equivalent", "status"))
            for left, right in PAIRS:
                for source, target in ((left, right), (right, left)):
                    for equivalence in EQUIVALENCES:
                        seconds, equivalent, status = compare(
                            bin_dir, bcg_paths[source], bcg_paths[target],
                            equivalence, environment, work_dir,
                        )
                        writer.writerow((source, target, equivalence, f"{seconds:.6f}", equivalent, status))
                        result_file.flush()
                        print(
                            f"{source},{target},{equivalence}: {equivalent or status} "
                            f"({seconds:.6f}s)", flush=True,
                        )


if __name__ == "__main__":
    main()