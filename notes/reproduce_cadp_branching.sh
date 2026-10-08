#!/usr/bin/env bash
set -euo pipefail

cadp_bin=${1:-${CADP_BIN:-${CADP:-"$HOME/Software/cadp"}/bin.x64}}
cadp_bin=$(cd -- "$cadp_bin" && pwd)
export CADP
CADP=$(dirname -- "$cadp_bin")
export PATH="$cadp_bin:$CADP/com:$PATH"

work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT
cd -- "$work_dir"

# LTBTS2 P55 and P56; initial state 0, internal action i.
printf '%s\n' 'des (0,3,3)' \
    '(0,"a",1)' '(1,"b",2)' '(1,"i",1)' > P55.aut
printf '%s\n' 'des (0,4,4)' \
    '(3,"b",2)' '(3,"i",1)' '(1,"i",1)' '(0,"a",3)' > P56.aut
"$cadp_bin/bcg_io" P55.aut P55.bcg
"$cadp_bin/bcg_io" P56.aut P56.bcg

set -x

# Observed: FALSE.
"$cadp_bin/bcg_cmp" -branching P55.bcg P56.bcg

# Observed: TRUE, disagreeing with bcg_cmp.
"$CADP/com/bcg_open" P55.bcg "$cadp_bin/bisimulator.a" -branching P56.bcg

# Observed: FALSE when reversing the same equivalence check.
"$CADP/com/bcg_open" P56.bcg "$cadp_bin/bisimulator.a" -branching P55.bcg

# Observed: FALSE in the reverse direction too.
"$cadp_bin/bcg_cmp" -branching P56.bcg P55.bcg