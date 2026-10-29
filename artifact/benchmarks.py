#!/usr/bin/env python3
"""Run paper VLTS measurements in isolated JVMs and emit raw and summarized CSVs."""

import argparse
import csv
import io
import json
import random
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EQUIVIO = ROOT / "equivio"
SYSTEMS = ("peterson", "vasy_0_1", "cwi_1_2", "vasy_1_4", "cwi_3_14", "vasy_5_9",
           "vasy_8_24", "vasy_8_38", "vasy_10_56", "vasy_18_73", "vasy_25_25")
EASY = tuple(name for name in SYSTEMS if name not in ("cwi_1_2", "vasy_10_56", "vasy_18_73"))
COLUMNS = ("System", "States", "Transitions", "Bisim pre-minimization time",
           "Bisim pre-minimized size", "Initial pairs", "Spectroscopy time",
           "Game positions", "Game moves")


def input_path(system):
    return ("shared/src/test/assets/other/peterson_mutex.csv" if system == "peterson"
            else f"shared/src/test/assets/vlts/{system}.csv")


def notions(semantics):
    return (("enabledness", "trace", "simulation") if semantics == "strong"
            else ("weak-enabledness", "weak-trace", "weak-simulation", "sr-branching-bisimulation"))


def measurement(jar, semantics, system, timeout, log):
    command = ["java", "-Xmx8g", "-XX:ActiveProcessorCount=1", "-cp", str(jar),
               "io.equiv.eqfiddle.artifact.PaperBenchmark", semantics, input_path(system)]
    fields = (*COLUMNS, *notions(semantics))
    try:
        result = subprocess.run(command, cwd=EQUIVIO, capture_output=True, text=True,
                                timeout=timeout, check=True)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        log.write_bytes(stdout + b"\n" + stderr)
        return {"System": input_path(system), "Status": "timeout"}
    except subprocess.CalledProcessError as error:
        log.write_text(error.stdout + error.stderr)
        raise ValueError(f"Benchmark JVM exited with {error.returncode}; see {log}") from error
    log.write_text(result.stdout + result.stderr)
    rows = list(csv.DictReader(io.StringIO(result.stdout), skipinitialspace=True))
    if len(rows) != 1 or tuple(rows[0]) != fields:
        raise ValueError(f"Unexpected benchmark output; see {log}")
    row = rows[0]
    if row["System"] != input_path(system) or any(
        row[name] is None or not row[name].strip().isdigit() for name in fields[1:]
    ):
        raise ValueError(f"Incomplete/non-numeric benchmark output; see {log}")
    return {**row, "Status": "ok"}


def summarize(rows, systems, runs, semantics):
    result = []
    for system in systems:
        samples = [row for row in rows if row["System"] == input_path(system)]
        successful = [row for row in samples if row["Status"] == "ok"]
        row = {"System": system}
        for name in ("States", "Bisim pre-minimized size", "Game moves", *notions(semantics)):
            values = {sample[name].strip() for sample in successful}
            if len(values) > 1:
                raise ValueError(f"Non-deterministic {name} for {semantics}/{system}: {values}")
            row[name] = next(iter(values)) if values else ""
        times = sorted(int(sample["Spectroscopy time"]) for sample in successful)
        row["time (s)"] = (f"{statistics.mean(times[1:-1] if runs > 2 else times) / 1000:.2f}"
                           if len(times) == runs else "")
        row["Status"] = "ok" if len(times) == runs else "timeout"
        result.append(row)
    return result


def reproduce(output, systems, runs, timeout, semantics):
    jars = list((EQUIVIO / "shared/target").glob("scala-*/shared-assembly-*.jar"))
    if len(jars) != 1:
        raise ValueError(f"Expected one built assembly jar, found {jars}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "configuration.json").write_text(json.dumps({
        "systems": systems, "runs": runs, "timeout_seconds": timeout,
        "heap": "8g", "active_processors": 1, "semantics": semantics,
        "timing": "mean of middle runs (discard min and max when runs > 2)",
    }, indent=2) + "\n")
    for family in semantics:
        fields = (*COLUMNS, *notions(family), "Run", "Status")
        rows = []
        with (output / f"benchmarking_{family}_game.csv").open("w", newline="") as raw:
            writer = csv.DictWriter(raw, fieldnames=fields)
            writer.writeheader()
            for run in range(1, runs + 1):
                ordered = list(systems)
                random.Random(run).shuffle(ordered)
                for system in ordered:
                    log = output / f"{family}-{system}-{run}.log"
                    row = measurement(jars[0], family, system, timeout, log)
                    row["Run"] = run
                    rows.append(row)
                    writer.writerow(row)
                    raw.flush()
                    print(f"{family}, run {run}, {system}: {row['Status']}", flush=True)
        summary = summarize(rows, systems, runs, family)
        with (output / f"table-{family}.csv").open("w", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--full", action="store_true", help="All 11 systems, five runs, 500 s limit")
    parser.add_argument("--system", action="append", choices=SYSTEMS, help="Select individual systems")
    parser.add_argument("--runs", type=int, help="Override the number of repetitions")
    parser.add_argument("--timeout", type=float, help="Override seconds per isolated JVM")
    parser.add_argument("--semantics", choices=("strong", "weak", "both"), default="both")
    args = parser.parse_args()
    runs = args.runs if args.runs is not None else 5 if args.full else 1
    timeout = args.timeout if args.timeout is not None else 500 if args.full else 10
    if runs < 1 or timeout <= 0 or timeout == float("inf") or timeout != timeout:
        parser.error("--runs and --timeout must be positive finite values")
    systems = tuple(dict.fromkeys(args.system)) if args.system else SYSTEMS if args.full else EASY
    semantics = ("strong", "weak") if args.semantics == "both" else (args.semantics,)
    try:
        reproduce(args.output_dir.expanduser().resolve(), systems, runs, timeout, semantics)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"VLTS benchmarking failed: {error}\n")


if __name__ == "__main__":
    main()
