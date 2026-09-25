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

The script compiles the submodule's `shared` subproject and runs its `compare` command with `--strong-game`. The comparison result is printed by equiv.io.