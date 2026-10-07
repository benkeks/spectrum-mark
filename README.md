# Spectrum Mark

## Setup

Install Python 3, a JDK, and [sbt](https://www.scala-sbt.org/download/). The first time you run sbt, it will download Scala dependencies, so network access is needed. Clone with `git clone --recurse-submodules`, or initialize an existing checkout:

```sh
git submodule update --init equivio
```

## Run

```sh
python3 run_equivio.py
```

The script builds the submodule's `shared` assembly jar once with sbt, then launches each of the ten state pairs in both directions directly with Java. Each `--strong-game` comparison has a 30-second limit. It writes elapsed wall-clock seconds (including Java startup), equiv.io's preorder names, and an `ok`, `timeout`, or `error` status to `results/ltbts1-equivio.csv`.

## Build mCRL2

The `mcrl2` submodule is pinned to a specific revision and configured for shallow checkouts. For a headless Linux build, install CMake (3.14 or newer), a C++20 compiler, Make, and Boost headers (1.71 or newer). On Debian/Ubuntu:

```sh
sudo apt install build-essential cmake libboost-dev
bash build_mcrl2.sh
```

The script initializes the submodule with `--depth 1`, configures a Release build in `build/mcrl2`, and builds only `ltscompare` and its dependencies. GUI tools, documentation, tests, and the unrelated symbolic tools are disabled. No system installation is needed. Re-running the script uses the existing build.

Run a first strong-bisimulation comparison of two existing AUT examples:

```sh
build/mcrl2/stage/bin/ltscompare --equivalence=bisim \
	examples/aut/ltbts1_L13.aut examples/aut/ltbts1_R13.aut
```

Use `build/mcrl2/stage/bin/ltscompare --help` for other equivalences and preorders.

## Run mCRL2

```sh
python3 run_mcrl2.py
```

The script runs the incremental mCRL2 build and regenerates the LTBTS1 AUT files before comparing. It discovers all strong equivalence options from `ltscompare --help-all`: strong bisimulation (including alternative and experimental algorithms), simulation, ready simulation, and trace equivalence.

Each comparison has a 30-second limit. Results go to `results/ltbts1-mcrl2.csv`, with one row per directed pair and algorithm: `left`, `right`, `equivalence`, `seconds`, `equivalent` (`true` or `false`), and `status` (`ok`, `timeout`, or `error`). Timing includes process startup, but not building or AUT generation; unsuccessful comparisons leave `equivalent` empty. Each run overwrites the report.

## Run CADP

CADP requires a separately installed, licensed local copy; nothing is downloaded or added as a submodule.

```sh
python3 run_cadp.py --cadp-bin /home/ben/Software/cadp/bin.x64
```

The binary directory defaults to `CADP_BIN`, then `$CADP/bin.x64`, then `~/Software/cadp/bin.x64`. `--cadp-bin` overrides these defaults. The script sets `CADP` and the subprocess search path from the selected installation, which must also contain `com/bcg_open` and the BISIMULATOR archive.

The runner regenerates the LTBTS1 AUT files and converts the selected inputs to BCG with `bcg_io`. CADP requires initial state zero, so state IDs are remapped in temporary AUT copies without changing the original AUT files. It compares the same ten pairs as equivio in both directions: strong bisimulation with `bcg_cmp` (`bisim-bcg-cmp`) and BISIMULATOR (`bisim-bisimulator`), and strong trace equivalence with BISIMULATOR (`trace`). Weak relations are excluded. See the [CADP tools](https://cadp.inria.fr/tools.html), [BCG_CMP](https://cadp.inria.fr/man/bcg_cmp.html), and[BISIMULATOR](https://cadp.inria.fr/man/bisimulator.html) documentation.

Results overwrite `results/ltbts1-cadp.csv` using the same columns as mCRL2, with 30-second comparison limits and `ok`, `timeout`, or `error` statuses. Timing includes process startup and CADP's library generation/compilation/linking (including BISIMULATOR's `bcg_open` wrapper), but excludes AUT generation and BCG conversion. Temporary AUT/BCG files and generated executables are removed when the run finishes. The report can be read by `compare_results.py`.