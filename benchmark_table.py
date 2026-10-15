#!/usr/bin/env python3
"""Summarize saved spectroscopy benchmarks as a LaTeX table."""

import argparse
from pathlib import Path

from compare_results import load_report_details
from csv_to_aut import parse_csv
from example import SUITE_DATASETS, directed_pairs, resolve_input
from run_suite import TOOLS


DATASET_GROUPS = (
    ("LTBTS1", (("ltbts1", False),)),
    ("LTBTS2", (("ltbts2", False),)),
    ("LTBTS2", (("ltbts2", False), ("ltbts2", True))),
    ("Peterson", (("peterson-silent", False), ("peterson-silent", True))),
    ("Edgecases", (("edgecases", False), ("edgecases", True))),
)


def latex_escape(text):
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def generate_latex(results_dir, examples_dir, groups=DATASET_GROUPS):
    inputs = {}
    reports = {}
    for _, tracks in groups:
        for stem, divergent in tracks:
            if stem not in inputs:
                source, pairs = resolve_input(examples_dir / f"{stem}.csv")
                transitions, metadata = parse_csv(source)
                states = {entry["state_id"] for entry in metadata}
                states.update(edge[key] for edge in transitions for key in ("src", "tar"))
                inputs[stem] = (set(directed_pairs(pairs)), len(states))
            for tool in TOOLS:
                key = (stem, divergent, tool)
                if key not in reports:
                    suffix = "-divergences" if divergent else ""
                    path = results_dir / f"{stem}-{tool}{suffix}.csv"
                    reports[key] = load_report_details(path) if path.is_file() else None

    lines = [
        r"\begin{longtable}{lrr rr rr rr}",
        r"\hline",
        r"\multicolumn{3}{c}{Dataset} & \multicolumn{2}{c}{equiv.io} & \multicolumn{2}{c}{mCRL2} & \multicolumn{2}{c}{CADP} \\",
        r"\cline{1-3}\cline{4-5}\cline{6-7}\cline{8-9}",
        r"Name & Pairs & $\states$ & $\notions$ & time (s) & $\notions$ & time (s) & $\notions$ & time (s) \\",
        r"\hline",
        r"\endhead",
    ]
    notes = []
    weak_datasets = {stem for stem, _, weak, _ in SUITE_DATASETS if weak}
    for label, tracks in groups:
        stems = dict.fromkeys(stem for stem, _ in tracks)
        pair_count = sum(len(inputs[stem][0]) for stem in stems)
        states = sum(inputs[stem][1] for stem in stems)
        families = {family for stem, divergent in tracks for tool in TOOLS
                    if reports[(stem, divergent, tool)] is not None
                    for decisions in reports[(stem, divergent, tool)][2].values()
                    for family, _, _ in decisions if family in ("strong", "weak")}
        if any(divergent for _, divergent in tracks):
            mode = "divergence"
        else:
            mode = "/".join(sorted(families)) or (
                "weak" if any(stem in weak_datasets for stem in stems) else "strong")
        name = r"\texttt{" + latex_escape(label.lower()) + "} (" + mode + ")"
        cells = [name, str(pair_count), str(states)]
        for tool in TOOLS:
            supported = set()
            seconds = 0.0
            checked_tasks = 0
            supported_tasks = 0
            incomplete = False
            missing = []
            for stem, divergent in tracks:
                report = reports[(stem, divergent, tool)]
                if report is None or not report[1]:
                    suffix = "-divergences" if divergent else ""
                    missing.append(f"{stem}-{tool}{suffix}.csv")
                    continue
                _, costs, decisions = report
                expected = inputs[stem][0]
                extra = set(costs) - expected
                if extra:
                    raise ValueError(f"Unexpected pairs in {stem}/{tool}: {sorted(extra)}")
                notions = {(family, notion) for pair in expected
                           for family, notion, _ in decisions.get(pair, {})}
                supported.update(notions)
                supported_tasks += len(notions) * len(expected)
                for pair in expected:
                    cost = costs.get(pair)
                    if cost is None:
                        incomplete = True
                        continue
                    seconds += cost.seconds
                    checked_tasks += cost.decided
                    if not cost.complete or cost.supported != len(notions):
                        incomplete = True
            if missing:
                cells.extend(("N/A", "N/A"))
                notes.append(f"- {label}, {tool}: missing or empty reports: {', '.join(missing)}.")
            else:
                marker = "*" if incomplete else ""
                cells.extend((f"{len(supported)}{marker}", f"{seconds:.3f}{marker}"))
                if incomplete:
                    notes.append(f"- {label}, {tool}: {checked_tasks}/{supported_tasks} notion-pair tasks decided; time is only the decided-task subtotal.")
        lines.append(" & ".join(cells) + r" \\")
    lines.extend((
        r"\hline",
        r"\end{longtable}",
        "",
        "% Compared pairs are the configured directed comparisons, counted once even when both ordinary and divergence tracks are included; missing results are marked below.",
        "% States count distinct state IDs (including named isolated states) in the original inputs; combined datasets are disjoint and each input is counted once.",
        "% Notions count distinct supported relations across included tracks, not algorithm variants or relation modes. Strong, weak and divergence-sensitive notions are distinct.",
        "% Times sum per-pair spectroscopy costs: equiv.io uses the median successful call; native tools use the fastest algorithm median per notion, preferring preorder mode when available. Repetitions are not summed. Builds and input preparation are excluded.",
        "% LTBTS1 and LTBTS2 include ordinary strong and weak reports respectively; the other rows include both ordinary weak and divergence-sensitive reports.",
        r"% The containing LaTeX document must load \usepackage{longtable} and define \states and \notions.",
        "% An asterisk marks incomplete coverage and partial time; N/A marks missing or empty reports.",
    ))
    if notes:
        lines.extend(("", *("% " + note for note in notes)))
    return "\n".join(lines) + "\n"


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=root / "results")
    parser.add_argument("--examples-dir", type=Path, default=root / "examples")
    parser.add_argument("--output", type=Path, help="Write LaTeX to this file instead of stdout")
    args = parser.parse_args()
    try:
        latex = generate_latex(args.results_dir.expanduser(), args.examples_dir.expanduser())
        if args.output is None:
            print(latex, end="")
        else:
            args.output.expanduser().write_text(latex)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Benchmark table failed: {error}\n")


if __name__ == "__main__":
    main()