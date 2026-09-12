"""
CLI entry point: find the best opening guess and simulate full games for
Chessle's Normal (6-ply) and Expert (10-ply) difficulties, both with a
uniform prior over answers (v1) and a popularity-weighted prior (v2).

Also runs a relaxed-then-legal-filtered probe search (chessle_solver.probe)
alongside the corpus-restricted search, since Chessle's real guess space is
"any legal move sequence," not just real named openings -- see ANALYSIS.md
section 8 for what this is and why it matters.

Usage: python3 main.py [normal|expert|both] [--probe-budget N]
"""
from __future__ import annotations

import sys
import time

from chessle_solver import (
    Solver,
    build_prefix_pool,
    find_best_legal_probe,
    load_entries,
    max_possible_entropy,
    simulate,
    weighted_average,
)


def run(depth: int, label: str, probe_budget: int):
    entries = load_entries()
    weighted_pool = build_prefix_pool(depth, entries=entries)
    uniform_pool = {moves: 1 for moves in weighted_pool}
    guess_pool = list(weighted_pool.keys())

    print(f"\n=== {label} ({depth}-ply guesses, {len(guess_pool)} distinct candidates) ===")
    print(f"Max possible entropy at this pool size: {max_possible_entropy(uniform_pool):.2f} bits")

    solvers = {
        "v1 (uniform prior)": (uniform_pool, Solver(guess_pool, uniform_pool)),
        "v2 (weighted prior)": (weighted_pool, Solver(guess_pool, weighted_pool)),
    }

    for name, (pool, solver) in solvers.items():
        t0 = time.time()
        opener, h = solver.opening_guess()
        print(f"\n-- {name} --")
        print(f"Best opening guess (real named openings only): {' '.join(opener)}  (entropy {h:.2f} bits)")

        probe_report = find_best_legal_probe(pool, depth, max_attempts=probe_budget)
        if probe_report.best:
            b = probe_report.best
            is_named = b.moves in weighted_pool
            print(
                f"Best legal probe (any legal sequence, {probe_report.total_attempts} scanned, "
                f"{probe_report.legal_found} legal): {' '.join(b.moves)}  (entropy {b.true_entropy:.2f} bits"
                f"{', a REAL named opening' if is_named else ', NOT a named opening'})"
            )
            if b.true_entropy > h:
                print("  -> probe beats the corpus-restricted opener.")
        else:
            print(f"Best legal probe: none found within budget ({probe_budget} scanned)")

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
    args = sys.argv[1:]
    probe_budget = 20_000
    if "--probe-budget" in args:
        i = args.index("--probe-budget")
        probe_budget = int(args[i + 1])
        del args[i : i + 2]
    which = args[0] if args else "both"
    if which in ("normal", "both"):
        run(6, "Normal", probe_budget)
    if which in ("expert", "both"):
        run(10, "Expert", probe_budget)
