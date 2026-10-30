#!/usr/bin/env bash
set -euo pipefail

root=${ARTIFACT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
cd "$root"
work=$(mktemp -d)
trap 'rm -f "$work/smoke.csv" "$work/smoke.aut" "$work/benchmark.csv"; rmdir "$work"' EXIT

printf '0,1,a\n2,1,a\n0,P,main\n2,Q,main\n' > "$work/smoke.csv"
printf 'des (0,1,2)\n(0,"a",1)\n' > "$work/smoke.aut"

printf 'Smoke test: equiv.io JVM comparison of two strongly bisimilar processes.\n'
jars=(equivio/shared/target/scala-*/shared-assembly-*.jar)
[[ ${#jars[@]} == 1 && -f "${jars[0]}" ]]
result=$(java -Xmx1g -jar "${jars[0]}" compare "$work/smoke.csv" P Q --strong-game)
printf 'P/Q (strong, JVM): %s\n' "$result"
[[ "$result" == bisimulation ]]
printf 'Smoke test: mCRL2 strong bisimulation check of an LTS against itself.\n'
result=$(build/mcrl2/stage/bin/ltscompare --equivalence=bisim "$work/smoke.aut" "$work/smoke.aut")
[[ "$result" == true ]]

printf 'Smoke test: VLTS benchmark entry point on vasy_0_1 (strong semantics).\n'
jar=$(realpath "${jars[0]}")
(cd equivio && java -Xmx1g -cp "$jar" io.equiv.eqfiddle.artifact.PaperBenchmark \
    strong shared/src/test/assets/vlts/vasy_0_1.csv) > "$work/benchmark.csv"
[[ $(wc -l < "$work/benchmark.csv") == 2 ]]
awk -F ', *' 'NR == 2 {
    printf "vasy_0_1 (strong): %s states, %s transitions, %s quotient states, %s game moves, %.3f s spectroscopy\n",
        $2, $3, $5, $9, $7 / 1000
}' "$work/benchmark.csv"

printf 'Smoke test: browser JavaScript API on the paper running example and directional preorders.\n'
node artifact/examples.js running

printf 'Smoke test passed (JVM, mCRL2 and browser API; CADP is optional).\n'
