"""
CLI entry point: find the best opening guess and simulate full games for
Chessle's Normal (6-ply) and Expert (10-ply) difficulties, both with a
uniform prior over answers (v1) and a popularity-weighted prior (v2).

Usage: python3 main.py [normal|expert|both]
"""
from __future__ import annotations

import sys
import time

from chessle_solver import (
    Solver,
    build_prefix_pool,
    load_entries,
    max_possible_entropy,
    simulate,
    weighted_average,
)


def run(depth: int, label: str):
    entries = load_entries()
    weighted_pool = build_prefix_pool(depth, entries=entries)
    uniform_pool = {moves: 1 for moves in weighted_pool}
    guess_pool = list(weighted_pool.keys())

    print(f"\n=== {label} ({depth}-ply guesses, {len(guess_pool)} distinct candidates) ===")
    print(f"Max possible entropy at this pool size: {max_possible_entropy(uniform_pool):.2f} bits")

    solvers = {
        "v1 (uniform prior)": Solver(guess_pool, uniform_pool),
        "v2 (weighted prior)": Solver(guess_pool, weighted_pool),
    }

    for name, solver in solvers.items():
        t0 = time.time()
        opener, h = solver.opening_guess()
        print(f"\n-- {name} --")
        print(f"Best opening guess: {' '.join(opener)}  (entropy {h:.2f} bits)")

        # Test set is always every distinct candidate; what changes is how
        # much we weight each one when averaging, i.e. what we assume the
        # true answer distribution looks like.
        result = simulate(solver, weighted_pool.keys())
        print(f"Average guesses (secrets equally likely):        {result.average:.3f}")
        print(f"Average guesses (secrets weighted by popularity): {weighted_average(result, weighted_pool):.3f}")
        print(f"Distribution (guesses -> count): {result.distribution}")
        if result.failures:
            print(f"Failures (>6 guesses): {result.failures}")
        print(f"[{time.time() - t0:.1f}s]")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("normal", "both"):
        run(6, "Normal")
    if which in ("expert", "both"):
        run(10, "Expert")
