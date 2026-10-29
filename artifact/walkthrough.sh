#!/usr/bin/env bash
set -euo pipefail
root=${ARTIFACT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
cd "$root"
mode=${1:-quick}
output=${2:-/results/$mode}
section=${3:-all}
if [[ $# -gt 3 || ! "$mode" =~ ^(quick|full)$ || ! "$section" =~ ^(all|examples|cross-checks|benchmarks)$ ]]; then
    printf 'Usage: bash artifact/walkthrough.sh [quick|full] [output-directory] [all|examples|cross-checks|benchmarks]\n' >&2
    exit 2
fi
mkdir -p "$output"
output=$(cd -- "$output" && pwd)
log="$output/walkthrough.log"
exec 3>&1
exec >> "$log" 2>&1

show() {
    "$@" 2>&1 | tee -a /dev/fd/3
}

report() {
    show printf "$@"
}

test_summary() {
    "$@" 2>&1 | tee -a "$log" | awk '
        /^\[info\] (Run completed in |Total number of tests run: |Suites: |Tests: |All tests passed\.)/ {
            print
            fflush()
        }
    ' >&3
}

finish() {
    status=$?
    if (( status != 0 )); then
        tail -n 20 "$log" >&3
        report '\nWalkthrough failed (exit %s). Full console output: %s\n' "$status" "$log"
    fi
}
trap finish EXIT

pause() {
    [[ ${WALKTHROUGH_NONINTERACTIVE:-0} != 1 ]] || return 0
    report '\nPress any key to continue...'
    if ! IFS= read -r -s -n 1; then
        report '\nNo input available. Use docker run -it, or set WALKTHROUGH_NONINTERACTIVE=1 for unattended runs.\n'
        return 1
    fi
    report '\n'
}

report 'Full console output: %s\n' "$log"
full=()
[[ "$mode" != full ]] || full=(--full)

if [[ "$section" == all || "$section" == examples ]]; then
    report '\n== Section 2: running example and directional preorders ==\n'
    report '(as found by equiv.io)\n'
    show node artifact/examples.js running "$output/examples"
    pause
    report '\n== Section 3: using equiv.io ==\n'
    report '\n-- Peterson: Pe/Mx, then Pe/MxIC --\n'
    show node artifact/examples.js peterson "$output/examples"
    report '\n-- Hiding: weak failures are not a congruence --\n'
    show node artifact/examples.js hiding "$output/examples"
    pause
    report '\n== Section 4: backend tests ==\n'
    report 'Scala backend tests:\n'
    (cd equivio && test_summary sbt -batch -J-Xmx8G "shared/test")
    pause
fi
if [[ "$section" == all || "$section" == cross-checks ]]; then
    report '\n== Section 5: cross-checks (Table 1) ==\n'
    python3 artifact/cross_checks.py --output-dir "$output/cross-checks" "${full[@]}"
    show awk -F ' & ' '
        BEGIN {
            printf "%-30s %5s %6s %8s %9s %6s %9s %5s %9s\n",
                "Dataset", "Pairs", "States", "equiv.io", "time (s)", "mCRL2", "time (s)", "CADP", "time (s)"
        }
        /^\\texttt\{/ {
            sub(/^\\texttt\{/, "", $1)
            sub(/\}/, "", $1)
            sub(/ *\\\\$/, "", $NF)
            printf "%-30s %5s %6s %8s %9s %6s %9s %5s %9s\n", $1,$2,$3,$4,$5,$6,$7,$8,$9
        }
    ' "$output/cross-checks/benchmark.tex"
    report 'Tool columns count notions; * marks incomplete results, N/A marks omitted tools.\n'
    report 'Validation summary:\n'
    show cat "$output/cross-checks/validation.json"
    report 'Detailed comparisons: %s/cross-checks/*-vs-*.txt\n' "$output"
    pause
fi
if [[ "$section" == all || "$section" == benchmarks ]]; then
    report '\n== Section 5: strong, then weak VLTS spectroscopy (Tables 2 and 3) ==\n'
    python3 artifact/benchmarks.py --output-dir "$output/vlts" "${full[@]}"
    for family in strong weak; do
        report '\n-- %s spectroscopy --\n' "$family"
        show awk -F, '
            NR == 1 {
                printf "%-14s %7s %8s %10s %9s %7s %7s %7s %s\n",
                    "System", "States", "Quotient", "Game moves", "time (s)", "E", "T", "S", "Status"
                next
            }
            {
                sub(/\r$/, "", $NF)
                printf "%-14s %7s %8s %10s %9s %7s %7s %7s %s\n",
                    $1,$2,$3,$4,($(NF-1) == "" ? "-" : $(NF-1)),$5,$6,$7,$NF
            }
        ' "$output/vlts/table-$family.csv"
    done
    report 'Quotient: strong bisimilarity / stability-respecting branching bisimilarity.\n'
    report 'E/T/S: enabledness, trace and simulation quotient sizes (weak variants in the weak table).\n'
    pause
fi
report '\nWalkthrough finished. Results: %s\nFull console output: %s\n' "$output" "$log"
