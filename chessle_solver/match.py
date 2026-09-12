"""
Chessle's feedback algorithm, reverse-engineered from js/game.min.js
(the `E` class's `compareSequences` method). It is byte-for-byte the same
two-pass duplicate-safe algorithm Wordle uses on letters, just applied to
SAN move tokens instead:

  pass 1: mark exact-position matches green, and remove one copy of that
          move from the answer's remaining-move counts.
  pass 2: for every still-unmarked guess move, mark it yellow if the answer
          still has an unconsumed copy of that move somewhere (and consume
          it), otherwise mark it gray ("b" / black in Chessle's code).

Chessle also supports a "piece-square" notation mode that loosens what
counts as "the same move" (stripping disambiguators/captures/checks). We
only implement "exact" (Chessle's default), since that's what the daily
puzzle uses unless the player changes notation settings.
"""
from __future__ import annotations

from collections import Counter

GREEN = "g"
YELLOW = "y"
GRAY = "b"


def compare_sequences(guess: tuple[str, ...], answer: tuple[str, ...]) -> tuple[str, ...]:
    if len(guess) != len(answer):
        raise ValueError("guess and answer lengths do not match")

    remaining = Counter(answer)
    result = [None] * len(guess)

    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            result[i] = GREEN
            remaining[g] -= 1

    for i, g in enumerate(guess):
        if result[i] is not None:
            continue
        if remaining[g] > 0:
            result[i] = YELLOW
            remaining[g] -= 1
        else:
            result[i] = GRAY

    return tuple(result)
