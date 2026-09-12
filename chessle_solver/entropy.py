"""
Entropy/information-theory core, mirroring the 3Blue1Brown Wordle video:

  information(pattern) = -log2(P(pattern))
  entropy(guess)        = E[information] = sum_pattern P(pattern) * information(pattern)

`answers` is a weighted pool: {move_tuple: weight}. Weight is treated as
"probability mass" (normalized internally), the same role that word
frequency plays for Wordle -- pass every weight = 1 to reproduce the
"assume every candidate is equally likely" first-pass version.
"""
from __future__ import annotations

import math
from collections import defaultdict

from .match import compare_sequences


def pattern_distribution(
    guess: tuple[str, ...], answers: dict[tuple[str, ...], float]
) -> dict[tuple[str, ...], float]:
    total_weight = sum(answers.values())
    buckets: dict[tuple[str, ...], float] = defaultdict(float)
    for answer, weight in answers.items():
        pattern = compare_sequences(guess, answer)
        buckets[pattern] += weight
    return {pattern: w / total_weight for pattern, w in buckets.items()}


def entropy(guess: tuple[str, ...], answers: dict[tuple[str, ...], float]) -> float:
    dist = pattern_distribution(guess, answers)
    return -sum(p * math.log2(p) for p in dist.values() if p > 0)


def max_possible_entropy(answers: dict[tuple[str, ...], float]) -> float:
    """Entropy of a hypothetical guess that maps every answer to its own pattern."""
    total_weight = sum(answers.values())
    return -sum(
        (w / total_weight) * math.log2(w / total_weight) for w in answers.values()
    )
