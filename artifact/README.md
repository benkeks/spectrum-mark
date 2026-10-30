# equiv.io paper artifact

Docker reproduction of **equiv.io: Easily Survey Behavioral Equivalences**.
Sources of equivio and patched mCRL2, separating examples, VLTS inputs and scripts are included. (For CADP, licensed installation from https://cadp.inria.fr/ would be required.)

- Artifact source: <https://github.com/benkeks/spectrum-mark/tree/main/artifact>
- Artifact with Docker image: <https://doi.org/10.5281/zenodo.23778646>

## Directory layout

The unpacked release contains:

```text
README.md                This guide
LICENSE                  License for the artifact scripts
equivio-artifact.tar     Prebuilt Docker image
SOURCE-REVISIONS         Repository and submodule commit IDs
SHA256SUMS               Checksums of the packaged files
spectrum-mark/           Sources, runner scripts and reference results
  artifact/              Dockerfile, walkthrough and benchmark scripts
  equivio/               equiv.io sources and VLTS inputs
  mcrl2/                 Patched mCRL2 sources
  examples/              Cross-check inputs
```

## Setup and smoke test

From the unpacked release directory of the [full artifact](https://doi.org/10.5281/zenodo.23778646) with Docker installed, run:

```sh
docker load -i equivio-artifact.tar
docker run --rm equivio-artifact bash artifact/smoke-test.sh
```

Expect `Smoke test passed` after JVM, mCRL2 and browser-API assertions (a few seconds).
The remaining commands run from the `spectrum-mark` source directory. For a Git checkout instead of a packaged release, build the image as described below first.

## Build the Docker image (optional)

If not starting from the prebuilt Docker image `equivio-artifact.tar`, use the following command from the root:

```sh
docker build --build-arg JOBS=2 -f artifact/Dockerfile -t equivio-artifact .
```

The build compiles the **included** equiv.io and mCRL2 sources, including the coupled-simulation fix used in the paper; it does not fetch newer tool sources.

Allow **12 GB RAM**, 2 CPU cores and approximately **15 GB free disk** for building, and good internet connection (roughly 10-30 minutes on a laptop).

## Walkthrough (in paper order)

```sh
mkdir -p artifact-results
docker run --rm -it --memory=10g --cpus=2 \
  -v "$PWD/artifact-results:/results" equivio-artifact \
  bash artifact/walkthrough.sh quick /results/quick
```

The quick walkthrough takes approximately **5-15 minutes**: all cross-check datasets once, plus eight easier VLTS systems once with a 10-second limit.
Every example asserts the claimed semantic results. Outputs and the transcript remain in `artifact-results/quick`. Press any key after each section!
The console shows key results and tables; `walkthrough.log` retains full stdout and stderr, including build and test output.
For unattended runs, omit `-it` and add `-e WALKTHROUGH_NONINTERACTIVE=1` before the image name. Failures print the last log lines and exit with a nonzero status.

1. **Section 2, behavioral equivalences.**
   The paper's `P = tau.a + tau.b`, `Q = tau.(a + b)` are strongly trace-equivalent, simulation-preordered only left-to-right, failure-preordered only right-to-left, and not bisimilar.
2. **Section 3, using equiv.io.**
   Peterson `Pe/Mx` are weakly trace-equivalent and weakly similar, but not weakly bisimilar. Relaxing to `MxIC` additionally preserves stable readiness, eta-simulation and weak ready simulation.
   The hiding counterexample first equates `P_e/P_l` under weak failures, then distinguishes `P_te/P_tl` only left-to-right; stable failures still equate them.
   JSON outputs include directional relations and distinguishing formulas.
   Accompanying CCS files can be pasted into the browser.
3. **Section 4, implementation.**
   Removes prebuilt equiv.io outputs with `sbt clean`, then rebuilds the JVM backend, JavaScript API and web client from the bundled sources.
   Runs the Scala and JavaScript API regression tests and repeats the smoke test. Dependencies may be downloaded, but no newer tool sources.
4. **Section 5, cross-checking (Table 1).**
   Runs `ltbts1`, `ltbts2`, `peterson-silent` and `edgecases`, including both weak tracks. `cross-checks/benchmark.tex` reproduces the table layout.
   Without CADP its cells are **N/A**, not copied paper numbers.
5. **Section 5, benchmarks (Tables 2 and 3).**
   Strong, then weak spectroscopy. `vlts/benchmarking_{strong,weak}_game.csv` contains raw measurements; `vlts/table-{strong,weak}.csv` gives the paper's columns and aggregation.

For the interactive walkthrough, start the bundled web tool separately:

```sh
docker run --rm --init \
  -p 127.0.0.1:8080:8080 \
  --name equivio-artifact-web equivio-artifact
```

Open <http://127.0.0.1:8080/#peterson-mutex-silent>, then <http://127.0.0.1:8080/#stable-unstable-abstraction>. Click the gutter next to `@check` or `@compareSilent` in the order above. Stop with Ctrl+C.

## Full paper measurements and individual steps

```sh
docker run --rm -it \
  -v "$PWD/artifact-results:/results" equivio-artifact \
  bash artifact/walkthrough.sh full /results/full
```

This keeps the same paper order, with **five shuffled repetitions** for every cross-tool query,
but runs all **11** VLTS models **once per semantics**, each with a **500-second** limit.
For five repetitions of every benchmark, as in the paper, use:

```sh
docker run --rm -it \
  -v "$PWD/artifact-results:/results" equivio-artifact \
  bash artifact/walkthrough.sh full-5 /results/full-5
```

The worst-case VLTS timeout budget is about **3.1 hours** for `full` (22 calls), or **15.3 hours** for `full-5` (110 calls); timings depend on CPU and container limits.
The paper used an Intel Core Ultra 7 155H and 8 GB heap.
Cross-check times sum per-query medians using the fastest algorithm median per notion; they include JVM startup and CADP linking.
VLTS times exclude pre-minimization: `full` reports the single measurement, while `full-5` reports the mean of the middle three of five successful runs.
A timeout leaves time blank, with `Status=timeout` and a raw log. Compare that to the paper's `>500.00`.

Append `examples` (including the clean rebuild and backend tests), `cross-checks` or `benchmarks` to any walkthrough command to run just that step. For one model:

```sh
docker run --rm \
  -v "$PWD/artifact-results:/results" equivio-artifact \
  python3 artifact/benchmarks.py --full --system vasy_8_24 \
  --semantics weak --output-dir /results/one-model
```

For new cross-check inputs, use `python3 run_suite.py --tools equivio mcrl2 --csv examples/ltbts2.csv --weak --pair P55 P56 --output-dir /results/custom` inside the image, replacing the CSV and named states as needed. Inputs and output formats are documented in the [main README](spectrum-mark/README.md).

## Own CADP installation

If you want to also execute cross-checks with CADP, you need your own copy.

You can obtain it and executables from [CADP's official site](https://cadp.inria.fr/).

You can then either add `-v "/absolute/path/to/cadp:/opt/cadp:ro" --network=host --hostname "$(hostname)" -e CADP=/opt/cadp` before `equivio-artifact` in `docker run`; provide a valid license for the container's (!) host.

If you have installed CADP in the host system, the easier approach will be to just run the cross check suite directly on the host without Docker. (Full Instructions in <https://github.com/benkeks/spectrum-mark/blob/main/README.md>.) If all dependencies are present, the following should suffice:

```sh
CADP="$HOME/Software/cadp" \
  python3 -u artifact/cross_checks.py --cadp on \
  --output-dir "$PWD/artifact-results/host-cross-checks"
```

As each CADP invocation takes more than half a second, expect the reproduction to take way longer than just with mCRL2 or equiv.io alone.

Without CADP, everything else still runs. With older CADP, contradictory answers or failed calls are retained, reported prominently in `validation.json` and marked `*`/incomplete in the table. Cross-tool disagreements (differing divergence semantics) remain visible in comparison reports even with patched CADP.

## Evaluation and distribution

Intended badges: **Available, Functional, Reusable**.

The artifact scripts use the repository's [MIT license](LICENSE); bundled equiv.io and mCRL2 retain their respective license files. The image contains `/opt/source-sha256.txt` to fingerprint the included sources.

Validated on **Linux amd64**, Debian forky/sid host, Docker 28.5.2: build and smoke test, complete quick walkthrough (~3.3 minutes with two CPUs), all five-run equiv.io/mCRL2 cross-checks (~7 minutes), strong/weak five-run VLTS aggregation for `vasy_0_1`, forced timeouts, **57 Python tests** and **951 Scala tests**. Offline runs were checked with `--network=none`.
