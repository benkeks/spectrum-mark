# Spectrum Mark

## Setup

Python 3 is required. Tool-specific dependencies:

- **Equivio:** a JDK and [sbt](https://www.scala-sbt.org/download/).
- **mCRL2:** CMake >= 3.14, a C++20 compiler, Make, and Boost >= 1.71.
- **CADP:** a licensed local installation and a C compiler; see [CADP tools](https://cadp.inria.fr/tools.html).

```sh
git submodule update --init equivio
sudo apt install build-essential cmake libboost-dev  # Debian/Ubuntu
bash build_mcrl2.sh
```

The mCRL2 build initializes a shallow checkout if missing, preserves existing local edits, and builds only `ltscompare` under `build/mcrl2/stage/bin`. No system installation is needed.

## Run

```sh
python3 run_equivio.py
python3 run_mcrl2.py
python3 run_cadp.py --cadp-bin ~/Software/cadp/bin.x64
```

Defaults test ten strong LTBTS1 pairs in both directions. Add `--weak` for the 16 weak LTBTS2 pairs (ending with P57-P58):

```sh
python3 run_equivio.py --weak
python3 run_mcrl2.py --weak
python3 run_cadp.py --weak
```

Runners build/generate inputs as needed. Silent AUT labels become `i`; CADP inputs are temporarily remapped to initial state zero. CADP's path defaults to `CADP_BIN`, `$CADP/bin.x64`, then `~/Software/cadp/bin.x64`; `--cadp-bin` overrides it.

## Results

Each run overwrites `results/ltbts{1,2}-{equivio,mcrl2,cadp}.csv`. Comparisons have a 30-second limit and record elapsed time plus `ok`, `timeout`, or `error`. Timing excludes input generation but includes process startup and CADP compilation/linking.

Equivio reports directional preorders; CADP reports boolean equivalences. mCRL2 prefers supported preorders and records `mode`: `equivalent=true` means left-to-right inclusion in preorder mode.

```sh
python3 compare_results.py results/ltbts1-equivio.csv results/ltbts1-mcrl2.csv
python3 compare_results.py --weak results/ltbts2-equivio.csv results/ltbts2-mcrl2.csv
```

Mixed equivalence/preorder reports are not directly equivalent. Checker disagreements are flagged as `conflict` and excluded from aggregation; notably, CADP's branching checkers disagree on P55-P56. Relations outside the configured spectrum are compared by name without assumed ordering.