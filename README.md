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
- `examples/ltbts2.csv`: 16 weak LTBTS2 pairs (ending with P57-P58), with ordinary and divergence-sensitive checks.
- `examples/peterson-silent.csv`: Peterson implementation `Pe` versus specifications `Mx` and `MxIC`, with ordinary and delta-marked weak Equivio spectroscopy. mCRL2 and CADP also check their native divergence-sensitive relations.

Run only the weak datasets, select a smaller comparison, or provide another CSV:

```sh
python3 run_suite.py --weak
python3 run_suite.py --weak --benchmark-performance --output-dir results/performance
python3 run_suite.py --pair L13 R13
python3 run_suite.py --csv examples/ltbts2.csv --weak --pair P55 P56
python3 run_suite.py --csv examples/peterson-silent.csv --weak
python3 run_suite.py --csv path/to/input.csv --pair P Q --pair R S --output-dir results/custom
```

Input CSVs contain transition rows `source_id,target_id,action` and named initial-state rows `state_id,state_name,main` or `state_id,state_name,implicit-main`. Registered CSVs use their curated pairs; other CSVs without `--pair` use all distinct named-state pairs in both directions. Use `--weak` to select weak semantics for custom inputs. Every weak suite run includes both ordinary and divergence-sensitive tracks for all three tools, with separate reports and within-track comparisons. The `--divergences` suite option remains accepted but is no longer needed. Default datasets and pairs are defined in `example.py`.

The individual `run_equivio.py`, `run_mcrl2.py` and `run_cadp.py` commands accept the same `--csv`, `--pair`, `--weak` and `--output-dir` options. Without input options they select the strong example, or the weak example with `--weak`.

Silent AUT labels become `i`; CADP inputs are temporarily remapped to initial state zero. CADP's path defaults to `CADP_BIN`, `$CADP/bin.x64`, then `~/Software/cadp/bin.x64`; `--cadp-bin` overrides it for the suite or CADP runner.

## Results

Each run writes fresh `<input-stem>-{equivio,mcrl2,cadp}.csv` reports and `<input-stem>-<first>-vs-<second>.txt` comparisons under `results/`, or `--output-dir`. Existing files with those names are overwritten. Use separate output directories for different semantic runs of the same CSV. Comparisons have a 30-second limit per individual tool call and record elapsed time plus `ok`, `timeout`, or `error`. Timing excludes input generation and tool builds but includes process startup and CADP compilation/linking.

Equivio reports directional preorder frontiers. CADP and mCRL2 record individual boolean checks with a `mode` column: `equivalent=true` means left-to-right inclusion in preorder mode. Both modes are measured separately whenever available, even when equivalence could be inferred from two preorder answers. Every selected check is executed for every directed pair, with no adaptive scheduling or skipped calls; the individual timings remain available for later spectroscopy cost analysis.

Use `--benchmark-performance` on the suite or an individual runner to execute each query five times. Each round uses a reproducibly shuffled order of directed examples and, for native tools, relation/algorithm checks. Builds and input preparation happen once, outside the timed rounds. Every call is retained in the CSV with a `run` identifier from 1 to 5; ordinary runs use 1. CSV row order records execution order. Existing CSVs without a `run` column remain supported as single-run reports.

Comparison timings use the median of successful repetitions for each exact query. Native spectroscopy costs then select the fastest algorithm median for each notion in its required relation mode, rather than selecting the fastest individual repetition. Errors and timeouts remain visible but are excluded from timing samples; contradictory answers are reported as conflicts and excluded from costs. A separate `--output-dir` keeps performance measurements from overwriting normal results.

- **mCRL2:** runs all advertised nontrivial equivalences and preorders in the selected strong or weak family, retaining every algorithm variant. Strong runs include simulation, ready simulation, trace (including antichains), failures, impossible futures, and bisimulation. Weak runs include weak trace (including antichains), stable failures (`weak-failures`), failures-divergence, coupled simulation, weak/branching bisimulation and their divergence-preserving variants.
- **CADP:** retains all configured `bcg_cmp` and BISIMULATOR equivalence checks, and adds `-smaller` for every BISIMULATOR relation. Since both pair directions are run, separate `-greater` calls would duplicate the same inclusion tasks. Strong inclusion checks cover simulation and trace; weak checks cover observational/weak simulation, branching simulation, tau*.a/safety simulation and weak trace.

CADP's `-strong -smaller` is simulation, not bisimulation; `-observational -smaller` is weak simulation. Tau*.a and safety have the same associated preorder and are still timed separately. CADP branching simulation and tau*.a simulation remain separately named outside the configured Equivio spectrum rather than assuming an unverified ordering. mCRL2's `weak-failures` maps to `stable-failure`, not `weak-failure`.

```sh
python3 compare_results.py results/ltbts1-equivio.csv results/ltbts1-mcrl2.csv
python3 compare_results.py --weak results/ltbts2-equivio.csv results/ltbts2-mcrl2.csv
```

Mixed equivalence/preorder reports are not directly equivalent. Checker disagreements are flagged as `conflict` and excluded from aggregation. Relations outside the configured spectrum are compared by name without assumed ordering.

### Benchmark Table

Generate a nine-column LaTeX longtable from existing reports without rerunning tools. The containing document must load `\usepackage{longtable}` and define the math macros `\states` and `\notions`:

```sh
python3 benchmark_table.py
python3 benchmark_table.py --results-dir results/performance --output results/performance/benchmark.tex
```

Rows cover `\texttt{ltbts1} (strong)`, `\texttt{ltbts2} (weak)`, `\texttt{ltbts2} (divergence)`, `\texttt{peterson} (divergence)` and `\texttt{edgecases} (divergence)`. Divergence rows retain both ordinary and divergence-sensitive weak tracks in their totals. Two-level headings group Name / Pairs / $\states$ under Dataset, and $\notions$ / time (s) under each of equiv.io, mCRL2 and CADP. The headings repeat on subsequent pages. Transition counts are omitted. `--examples-dir` selects another directory containing the dataset input CSVs. The emitted `longtable` environment can be included using `\input{benchmark.tex}` directly, not inside a floating `table`; aggregation rules and missing-data details appear as LaTeX comments after the table.

Inputs and pair counts are counted once per row, even when both tracks are included. State counts include transition endpoints and named isolated states; combined inputs have separate state-ID namespaces. Notion counts distinguish strong, weak and divergence-sensitive families but do not count algorithm variants or equivalence/preorder modes separately.

Times sum the comparator's per-pair costs, using successful-run medians and the fastest algorithm median per native notion, preferring preorder mode when available. They are not the sum of every recorded algorithm call or repetition, nor total suite wall-clock time. Missing/empty reports produce `N/A`; incomplete notion coverage produces an asterisk and an explained decided-task timing subtotal. Pair counts refer to the configured benchmark selection; reports containing unexpected pairs are rejected.

Run the focused input, suite and runner tests with `python3 -m unittest -v test_runners`.