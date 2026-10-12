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
python3 run_suite.py
```

This starts from the registered CSV datasets, builds the tools as needed, generates AUT/BCG inputs, runs Equivio, mCRL2 and CADP, and writes pairwise result comparisons. All selected pairs are checked in both directions:

- `examples/ltbts1.csv`: ten curated strong LTBTS1 pairs.
- `examples/ltbts2.csv`: 16 weak LTBTS2 pairs (ending with P57-P58).
- `examples/peterson-silent.csv`: Peterson implementation `Pe` versus specifications `Mx` and `MxIC`, with ordinary and delta-marked weak Equivio spectroscopy. mCRL2 and CADP also check their native divergence-sensitive relations.

Run only the weak datasets, select a smaller comparison, or provide another CSV:

```sh
python3 run_suite.py --weak
python3 run_suite.py --pair L13 R13
python3 run_suite.py --csv examples/ltbts2.csv --weak --pair P55 P56
python3 run_suite.py --csv examples/peterson-silent.csv --weak --divergences
python3 run_suite.py --csv path/to/input.csv --pair P Q --pair R S --output-dir results/custom
```

Input CSVs contain transition rows `source_id,target_id,action` and named initial-state rows `state_id,state_name,main` or `state_id,state_name,implicit-main`. Registered CSVs use their curated pairs; other CSVs without `--pair` use all distinct named-state pairs in both directions. Use `--weak` to select weak semantics for custom inputs. Default datasets, pairs and divergence-marking settings are defined in `example.py`.

The individual `run_equivio.py`, `run_mcrl2.py` and `run_cadp.py` commands accept the same `--csv`, `--pair`, `--weak` and `--output-dir` options. Without input options they select the strong example, or the weak example with `--weak`.

Silent AUT labels become `i`; CADP inputs are temporarily remapped to initial state zero. CADP's path defaults to `CADP_BIN`, `$CADP/bin.x64`, then `~/Software/cadp/bin.x64`; `--cadp-bin` overrides it for the suite or CADP runner.

## Results

Each run writes fresh `<input-stem>-{equivio,mcrl2,cadp}.csv` reports and `<input-stem>-<first>-vs-<second>.txt` comparisons under `results/`, or `--output-dir`. Existing files with those names are overwritten. Use separate output directories for different semantic runs of the same CSV. Comparisons have a 30-second limit per individual tool call and record elapsed time plus `ok`, `timeout`, or `error`. Timing excludes input generation and tool builds but includes process startup and CADP compilation/linking.

Equivio reports directional preorder frontiers. CADP and mCRL2 record individual boolean checks with a `mode` column: `equivalent=true` means left-to-right inclusion in preorder mode. Both modes are measured separately whenever available, even when equivalence could be inferred from two preorder answers. Every selected check is executed for every directed pair, with no adaptive scheduling or skipped calls; the individual timings remain available for later spectroscopy cost analysis.

- **mCRL2:** runs all advertised nontrivial equivalences and preorders in the selected strong or weak family, retaining every algorithm variant. Strong runs include simulation, ready simulation, trace (including antichains), failures, impossible futures, and bisimulation. Weak runs include weak trace (including antichains), stable failures (`weak-failures`), failures-divergence, coupled simulation, weak/branching bisimulation and their divergence-preserving variants.
- **CADP:** retains all configured `bcg_cmp` and BISIMULATOR equivalence checks, and adds `-smaller` for every BISIMULATOR relation. Since both pair directions are run, separate `-greater` calls would duplicate the same inclusion tasks. Strong inclusion checks cover simulation and trace; weak checks cover observational/weak simulation, branching simulation, tau*.a/safety simulation and weak trace.

CADP's `-strong -smaller` is simulation, not bisimulation; `-observational -smaller` is weak simulation. Tau*.a and safety have the same associated preorder and are still timed separately. CADP branching simulation and tau*.a simulation remain separately named outside the configured Equivio spectrum rather than assuming an unverified ordering. mCRL2's `weak-failures` maps to `stable-failure`, not `weak-failure`.

```sh
python3 compare_results.py results/ltbts1-equivio.csv results/ltbts1-mcrl2.csv
python3 compare_results.py --weak results/ltbts2-equivio.csv results/ltbts2-mcrl2.csv
```

Mixed equivalence/preorder reports are not directly equivalent. Checker disagreements are flagged as `conflict` and excluded from aggregation. Relations outside the configured spectrum are compared by name without assumed ordering.

Run the focused input, suite and runner tests with `python3 -m unittest -v test_runners`.