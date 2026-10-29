#!/usr/bin/env bash
set -euo pipefail

root=${ARTIFACT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
cd "$root"
work=$(mktemp -d)
trap 'rm -f "$work/smoke.csv" "$work/smoke.aut" "$work/benchmark.csv"; rmdir "$work"' EXIT

printf '0,1,a\n2,1,a\n0,P,main\n2,Q,main\n' > "$work/smoke.csv"
printf 'des (0,1,2)\n(0,"a",1)\n' > "$work/smoke.aut"

jars=(equivio/shared/target/scala-*/shared-assembly-*.jar)
[[ ${#jars[@]} == 1 && -f "${jars[0]}" ]]
[[ $(java -Xmx1g -jar "${jars[0]}" compare "$work/smoke.csv" P Q --strong-game) == bisimulation ]]
[[ $(build/mcrl2/stage/bin/ltscompare --equivalence=bisim "$work/smoke.aut" "$work/smoke.aut") == true ]]

jar=$(realpath "${jars[0]}")
(cd equivio && java -Xmx1g -cp "$jar" io.equiv.eqfiddle.artifact.PaperBenchmark \
    strong shared/src/test/assets/vlts/vasy_0_1.csv) > "$work/benchmark.csv"
[[ $(wc -l < "$work/benchmark.csv") == 2 ]]

node artifact/examples.js running

printf 'Smoke test passed (JVM, mCRL2 and browser API; CADP is optional).\n'
