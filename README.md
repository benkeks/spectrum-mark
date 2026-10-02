# Spectrum Mark

## Setup

Install Python 3, a JDK, and [sbt](https://www.scala-sbt.org/download/). The first time you run sbt, it will download Scala dependencies, so network access is needed. Clone with `git clone --recurse-submodules`, or initialize an existing checkout:

```sh
git submodule update --init equivio
```

## Run

```sh
python3 run-equivio.py
```

The script builds the submodule's `shared` assembly jar once with sbt, then launches each of the ten state pairs in both directions directly with Java. Each `--strong-game` comparison has a 30-second limit. It writes elapsed wall-clock seconds (including Java startup), equiv.io's preorder names, and an `ok`, `timeout`, or `error` status to `results/ltbts1-equivio.csv`.

## Build mCRL2

The `mcrl2` submodule is pinned to a specific revision and configured for shallow checkouts. For a headless Linux build, install CMake (3.14 or newer), a C++20 compiler, Make, and Boost headers (1.71 or newer). On Debian/Ubuntu:

```sh
sudo apt install build-essential cmake libboost-dev
bash build-mcrl2.sh
```

The script initializes the submodule with `--depth 1`, configures a Release build in `build/mcrl2`, and builds only `ltscompare` and its dependencies. GUI tools, documentation, tests, and the unrelated symbolic tools are disabled. No system installation is needed. Re-running the script uses the existing build.

Run a first strong-bisimulation comparison of two existing AUT examples:

```sh
build/mcrl2/stage/bin/ltscompare --equivalence=bisim \
	examples/aut/ltbts1_L13.aut examples/aut/ltbts1_R13.aut
```

Use `build/mcrl2/stage/bin/ltscompare --help` for other equivalences and preorders.
mCRL2 benchmark automation is not yet included.