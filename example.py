"""Shared LTBTS datasets, comparison pairs, and AUT preparation."""

from csv_to_aut import convert_csv_to_aut


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


def get_example(weak=False):
    return ("ltbts2", WEAK_PAIRS) if weak else ("ltbts1", PAIRS)


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