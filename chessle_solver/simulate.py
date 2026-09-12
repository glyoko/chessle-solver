"""Run the solver against every answer in the pool and report stats."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .solver import Solver


@dataclass
class SimulationResult:
    scores: dict[tuple[str, ...], int]

    @property
    def average(self) -> float:
        return statistics.mean(self.scores.values())

    @property
    def distribution(self) -> dict[int, int]:
        dist: dict[int, int] = {}
        for n in self.scores.values():
            dist[n] = dist.get(n, 0) + 1
        return dict(sorted(dist.items()))

    @property
    def failures(self) -> int:
        return sum(1 for n in self.scores.values() if n > 6)


def simulate(solver: Solver, secrets) -> SimulationResult:
    scores = {}
    for secret in secrets:
        guesses = solver.play(secret)
        scores[secret] = len(guesses)
    return SimulationResult(scores)


def weighted_average(result: SimulationResult, weights: dict[tuple[str, ...], float]) -> float:
    """Average guesses, weighting each secret by its assumed likelihood of being
    the actual answer (rather than treating every candidate as equally likely)."""
    total_weight = sum(weights.values())
    total_score = sum(weights[secret] * n for secret, n in result.scores.items())
    return total_score / total_weight
