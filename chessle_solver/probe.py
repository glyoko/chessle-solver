"""
Relaxed-then-constrained guess search.

The true optimal Chessle guess is drawn from an intractably large space
(every legal N-ply move sequence). Brute-forcing that is infeasible. This
module instead:

  1. Solves an *easier, relaxed* version of the problem: at each ply
     position independently, ignore both legality and cross-position
     correlation, and rank candidate moves purely by how well they split
     the answer pool's marginal distribution at that one slot (binary
     "does the answer play this move here, or not" entropy). This is NOT
     the same objective as true joint Chessle entropy -- it drops the
     yellow/duplicate cross-referencing that makes moves at different
     positions interact -- but it's cheap and tractable.
  2. Enumerates *combinations* of per-position picks in strictly
     non-increasing order of their (relaxed) total score, using a
     best-first search over the sorted per-position candidate lists --
     the standard "k best combinations from n sorted lists" technique.
  3. Tests each combination, in that order, for real chess legality
     (via legal.py) and stops at the first legal one.

Because step 1's objective differs from true entropy, the result is a
strong *candidate*, not a proven-optimal guess -- callers should verify it
against the real entropy calculation (entropy.py) before trusting it.
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass

from .entropy import entropy
from .legal import is_legal_sequence


def per_ply_marginals(
    answers: dict[tuple[str, ...], float], depth: int
) -> list[dict[str, float]]:
    """For each ply 0..depth-1, the weighted probability of each move token
    occurring at that position, across the answer pool."""
    totals = [defaultdict(float) for _ in range(depth)]
    total_weight = sum(answers.values())
    for moves, weight in answers.items():
        for i in range(depth):
            totals[i][moves[i]] += weight
    return [{tok: w / total_weight for tok, w in slot.items()} for slot in totals]


def _binary_entropy(p: float) -> float:
    if p <= 0 or p >= 1:
        return 0.0
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def per_ply_rankings(
    marginals: list[dict[str, float]],
) -> list[list[tuple[str, float]]]:
    """For each position, candidate (token, relaxed_score) pairs sorted best-first."""
    rankings = []
    for slot in marginals:
        scored = [(tok, _binary_entropy(p)) for tok, p in slot.items()]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        rankings.append(scored)
    return rankings


def generate_ranked_combinations(rankings: list[list[tuple[str, float]]]):
    """Yield (move_tuple, relaxed_total_score) in non-increasing score order."""
    depth = len(rankings)

    def score_of(idxs):
        return sum(rankings[i][idxs[i]][1] for i in range(depth))

    start = tuple(0 for _ in range(depth))
    visited = {start}
    heap = [(-score_of(start), start)]
    while heap:
        neg_score, idxs = heapq.heappop(heap)
        tokens = tuple(rankings[i][idxs[i]][0] for i in range(depth))
        yield tokens, -neg_score
        for i in range(depth):
            if idxs[i] + 1 < len(rankings[i]):
                nxt = idxs[:i] + (idxs[i] + 1,) + idxs[i + 1 :]
                if nxt not in visited:
                    visited.add(nxt)
                    heapq.heappush(heap, (-score_of(nxt), nxt))


@dataclass
class ProbeResult:
    moves: tuple[str, ...]
    relaxed_score: float
    true_entropy: float
    attempts_to_find: int  # combinations scanned (legal or not) before this one turned up


@dataclass
class ProbeSearchReport:
    best: ProbeResult | None
    total_attempts: int
    legal_found: int


def find_best_legal_probe(
    answers: dict[tuple[str, ...], float],
    depth: int,
    max_attempts: int = 20_000,
) -> ProbeSearchReport:
    """
    Scan combinations in decreasing relaxed-score order, up to `max_attempts`.
    For every one that turns out to be a legal move sequence, score it with
    the REAL entropy function (not the relaxed per-slot proxy that generated
    it), and keep whichever legal sequence has the highest true entropy --
    the relaxed ranking is only used to decide search order, never to pick
    the winner.
    """
    rankings = per_ply_rankings(per_ply_marginals(answers, depth))
    best: ProbeResult | None = None
    legal_found = 0
    attempts = 0
    for moves, relaxed_score in generate_ranked_combinations(rankings):
        attempts += 1
        if is_legal_sequence(moves):
            legal_found += 1
            true_h = entropy(moves, answers)
            if best is None or true_h > best.true_entropy:
                best = ProbeResult(
                    moves=moves,
                    relaxed_score=relaxed_score,
                    true_entropy=true_h,
                    attempts_to_find=attempts,
                )
        if attempts >= max_attempts:
            break
    return ProbeSearchReport(best=best, total_attempts=attempts, legal_found=legal_found)
