"""
Loads the "alphabet" of possible opening move-sequences for Chessle.

Chessle's daily puzzle names each answer by walking a tree of named chess
openings (ECO-style) and taking the name of the longest matching prefix
(confirmed by cross-checking a live puzzle's answer/name pair against this
dataset -- see ANALYSIS.md). This module is intentionally decoupled from any
one dataset file/format: everything downstream (entropy, solver, simulation)
consumes a plain dict of {move_tuple: weight}, so a different corpus (a real
game database, Chessle's own list if it's ever exposed, a different opening
book) can be swapped in just by writing a new loader with the same return
shape.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parent.parent / "openings_corpus.tsv"


@dataclass(frozen=True)
class OpeningEntry:
    eco: str
    name: str
    moves: tuple[str, ...]  # SAN tokens, no move numbers, e.g. ("f4", "d5", "Nf3", ...)


def _pgn_to_moves(pgn: str) -> tuple[str, ...]:
    """Turn "1. f4 d5 2. Nf3 Nf6" into ("f4", "d5", "Nf3", "Nf6")."""
    tokens = pgn.split()
    return tuple(t for t in tokens if not t.endswith("."))


def load_entries(path: Path | str = DEFAULT_CORPUS_PATH) -> list[OpeningEntry]:
    entries = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            entries.append(
                OpeningEntry(
                    eco=row["eco"],
                    name=row["name"],
                    moves=_pgn_to_moves(row["pgn"]),
                )
            )
    return entries


def build_prefix_pool(
    depth: int,
    entries: list[OpeningEntry] | None = None,
    path: Path | str = DEFAULT_CORPUS_PATH,
) -> dict[tuple[str, ...], int]:
    """
    Collapse every opening entry with at least `depth` plies down to its
    first `depth` moves, and count how many entries share that prefix.

    That count is used as a stand-in for "how well-established/likely this
    line is" (a busy branch point in the opening tree = a mainline everyone
    plays through; a prefix with weight 1 = a rare, obscure line) -- the
    direct analog of using English word frequency to weight Wordle answers,
    since we don't have Chessle's real answer-selection frequencies.
    """
    if entries is None:
        entries = load_entries(path)
    pool: dict[tuple[str, ...], int] = defaultdict(int)
    for entry in entries:
        if len(entry.moves) >= depth:
            pool[entry.moves[:depth]] += 1
    return dict(pool)
