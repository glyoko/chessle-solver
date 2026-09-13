"""
Legal-by-construction guess search (beam search over the real game tree).

`probe.py` takes a different approach: rank moves per ply independently
(ignoring legality entirely), enumerate combinations of those rankings, and
filter for legality after the fact. That turns out to fail structurally,
not just occasionally -- the top of that ranking systematically reuses the
same popular developing moves (e.g. "Nf3") across multiple plies, which is
illegal (a knight can't be on f3 twice), so the overwhelming majority of
combinations checked are wasted work, with no guarantee a bigger budget
ever finds the true best legal sequence.

This module fixes that by construction: build the guess move by move,
branching only into moves that are actually legal in the current
position (via python-chess), so every candidate ever scored is legal.
At each ply, score every candidate extension with the REAL entropy
formula against the answer pool truncated to that same length (not the
per-slot binary proxy `probe.py` uses -- this captures the green/yellow
cross-referencing between positions that the proxy drops), then keep only
the top `beam_width` candidates before extending further. This is a beam
search: it's bounded and reproducible, but it's still a heuristic --
narrowing to `beam_width` candidates at ply k can discard a prefix that
would have led to the best full-depth sequence. A wider beam trades more
computation for a better chance of finding the true optimum; it does not
guarantee finding it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import chess

from .entropy import entropy


def truncate_pool(
    answers: dict[tuple[str, ...], float], length: int
) -> dict[tuple[str, ...], float]:
    """Collapse a full-depth answer pool down to its first `length` moves,
    summing weight for prefixes that collide -- the same operation
    corpus.build_prefix_pool does, just starting from an in-memory pool
    instead of raw corpus entries."""
    truncated: dict[tuple[str, ...], float] = defaultdict(float)
    for moves, weight in answers.items():
        truncated[moves[:length]] += weight
    return dict(truncated)


@dataclass
class BeamCandidate:
    board: chess.Board
    moves: tuple[str, ...]
    score: float  # true entropy of `moves` against the length-matched answer pool


@dataclass
class TreeProbeResult:
    moves: tuple[str, ...]
    true_entropy: float


@dataclass
class TreeProbeReport:
    best: TreeProbeResult | None
    beam_width: int
    nodes_expanded: int  # total legal (board, move) extensions scored across all plies
    per_ply_survivors: list[int] = field(default_factory=list)


def find_best_legal_probe_tree(
    answers: dict[tuple[str, ...], float],
    depth: int,
    beam_width: int = 200,
) -> TreeProbeReport:
    """
    Beam search over legal move sequences, depth plies deep, maximizing true
    Chessle entropy against `answers` (a {move_tuple: weight} pool of the
    same depth). Every sequence ever scored is legal by construction: at
    each ply we only ever branch into `board.legal_moves`.
    """
    prefix_pools = [truncate_pool(answers, length) for length in range(1, depth + 1)]

    beam = [BeamCandidate(board=chess.Board(), moves=(), score=0.0)]
    nodes_expanded = 0
    per_ply_survivors: list[int] = []

    for ply in range(depth):
        pool = prefix_pools[ply]
        expanded: list[BeamCandidate] = []
        for cand in beam:
            for move in cand.board.legal_moves:
                san = cand.board.san(move)
                new_moves = cand.moves + (san,)
                new_board = cand.board.copy(stack=False)
                new_board.push(move)
                score = entropy(new_moves, pool)
                expanded.append(BeamCandidate(board=new_board, moves=new_moves, score=score))
        nodes_expanded += len(expanded)
        expanded.sort(key=lambda c: c.score, reverse=True)
        beam = expanded[:beam_width]
        per_ply_survivors.append(len(beam))
        if not beam:
            return TreeProbeReport(
                best=None,
                beam_width=beam_width,
                nodes_expanded=nodes_expanded,
                per_ply_survivors=per_ply_survivors,
            )

    best_cand = beam[0]
    return TreeProbeReport(
        best=TreeProbeResult(moves=best_cand.moves, true_entropy=best_cand.score),
        beam_width=beam_width,
        nodes_expanded=nodes_expanded,
        per_ply_survivors=per_ply_survivors,
    )
