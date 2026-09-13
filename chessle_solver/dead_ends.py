"""
Identify opening families whose named theory in openings_corpus.tsv dead-ends
before reaching a target depth -- i.e. no entry of any length continues that
exact move prefix that far. Confirmed against a real live Chessle puzzle
(see ANALYSIS.md) that Chessle still generates full-depth puzzles for such
families, drawing on some continuation source our named-opening corpus
doesn't have.
"""
from __future__ import annotations

from .corpus import OpeningEntry


def compute_dead_ends(
    entries: list[OpeningEntry], target_depth: int
) -> dict[tuple[str, ...], int]:
    """
    Return {short_move_tuple: weight} for every distinct move sequence that
    is too short for `target_depth` and that no entry extends up to
    `target_depth` plies. `weight` is how many original entries collapse
    onto that same short, dead-end prefix (the same popularity proxy
    build_prefix_pool uses).
    """
    long_prefixes = {e.moves[:target_depth] for e in entries if len(e.moves) >= target_depth}
    covered_shorter = set()
    for full in long_prefixes:
        for k in range(1, target_depth):
            covered_shorter.add(full[:k])

    dead: dict[tuple[str, ...], int] = {}
    for e in entries:
        if len(e.moves) < target_depth and e.moves not in covered_shorter:
            dead[e.moves] = dead.get(e.moves, 0) + 1
    return dead
