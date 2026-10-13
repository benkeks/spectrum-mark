"""Shared CSV inputs, comparison pairs, and AUT preparation."""

from itertools import combinations
from pathlib import Path

from csv_to_aut import convert_csv_to_aut, parse_csv


PAIRS = (
    ("L13", "R13"),
    ("L16", "R16"),
    ("L21", "R21"),
    ("L24", "R24"),
    ("L27", "R27"),
    ("L31", "R31"),
    ("L34", "R31"),
    ("L38", "R24"),
    ("L42", "R42"),
    ("L50", "R50"),
)

WEAK_PAIRS = (
    ("P11", "P12"), ("P13", "P14"), ("P15", "P16"),
    ("P21", "P22"), ("P22", "P23"), ("P24", "P25"),
    ("P31", "P32"), ("P33", "P34"),
    ("P41", "P42"), ("P42", "P43"), ("P44", "P45"),
    ("P51", "P52"), ("P53", "P54"), ("P55", "P56"),
    ("P56", "P57"), ("P57", "P58"),
)


PETERSON_PAIRS = (("Pe", "Mx"), ("Pe", "MxIC"))

SUITE_DATASETS = (
    ("ltbts1", PAIRS, False, False),
    ("ltbts2", WEAK_PAIRS, True, True),
    ("peterson-silent", PETERSON_PAIRS, True, True),
)


def get_example(weak=False):
    return ("ltbts2", WEAK_PAIRS) if weak else ("ltbts1", PAIRS)


def add_input_arguments(parser):
    parser.add_argument("--csv", type=Path, help="Input LTS CSV (default: selected LTBTS example)")
    parser.add_argument("--pair", nargs=2, action="append", metavar=("LEFT", "RIGHT"),
                        help="Compare these named states in both directions; repeat for more pairs")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parent / "results",
                        help="Directory for generated reports")


def resolve_input(csv_path=None, pairs=None, weak=False):
    dataset = get_example(weak)[0]
    default_path = Path(__file__).resolve().parent / "examples" / f"{dataset}.csv"
    csv_path = (csv_path or default_path).expanduser().resolve()
    _, meta = parse_csv(csv_path)
    states = [entry["state_name"] for entry in meta]
    if not states or len(states) != len(set(states)):
        raise ValueError(f"Expected unique named initial states in {csv_path}")
    if pairs is None:
        examples = Path(__file__).resolve().parent / "examples"
        registered_pairs = {
            examples / f"{name}.csv": example_pairs
            for name, example_pairs, _, _ in SUITE_DATASETS
        }
        pairs = registered_pairs.get(csv_path, list(combinations(states, 2)))
    pairs = [tuple(pair) for pair in pairs]
    if not pairs:
        raise ValueError(f"No comparison pairs selected for {csv_path}")
    seen = set()
    for left, right in pairs:
        if left not in states or right not in states or left == right:
            raise ValueError(f"Invalid comparison pair {left!r}, {right!r} in {csv_path}")
        key = frozenset((left, right))
        if key in seen:
            raise ValueError(f"Duplicate comparison pair {left!r}, {right!r}")
        seen.add(key)
    return csv_path, pairs


def directed_pairs(pairs):
    for left, right in pairs:
        yield left, right
        yield right, left


def prepare_auts(csv_path, pairs):
    convert_csv_to_aut(csv_path)
    paths = {
        state: csv_path.parent / "aut" / f"{csv_path.stem}_{state}.aut"
        for pair in pairs for state in pair
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    return paths