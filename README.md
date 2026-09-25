# Spectrum Mark

## Setup

Install Python 3, a JDK, and [sbt](https://www.scala-sbt.org/download/).
The first time you run sbt, it will download Scala dependencies, so network access is needed.
Clone with `git clone --recurse-submodules`, or initialize an existing checkout:

```sh
git submodule update --init equiv-io
```

## Run

```sh
python3 run-equiv-io.py
```

The script builds the submodule's `shared` assembly jar once with sbt, then
launches each of the ten state pairs in both directions directly with Java.
Each `--strong-game` comparison has a 30-second limit. It writes elapsed
wall-clock seconds (including Java startup), equiv.io's preorder names, and an
`ok`, `timeout`, or `error` status to `results/ltbts1-equivio.csv`.