#!/usr/bin/env python3
"""Compare L13 and R13 from the first LTBTS example with equiv.io."""

import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    csv_path = root / "examples" / "ltbts1.csv"
    subprocess.run(
        [
            "sbt",
            "shared/compile",
            f'shared/run compare "{csv_path}" L13 R13 --strong-game',
        ],
        cwd=root / "equiv-io",
        check=True,
    )


if __name__ == "__main__":
    main()