"""
CLI entry point: find the best opening guess and simulate full games for
Chessle's Normal (6-ply) and Expert (10-ply) difficulties, both with a
uniform prior over answers (v1) and a popularity-weighted prior (v2).

Also runs two off-book probe searches alongside the corpus-restricted
search, since Chessle's real guess space is "any legal move sequence," not
just real named openings -- see ANALYSIS.md section 8:
  - chessle_solver.probe: relaxed per-ply ranking, filtered for legality
    after the fact (fast, but wastes most of its budget on illegal
    sequences since the ranking has no notion of chess legality).
  - chessle_solver.tree_probe: beam search over the real game tree, legal
    by construction (every candidate scored is actually legal).

Usage: python3 main.py [normal|expert|both] [--probe-budget N] [--beam-width N]
"""
from __future__ import annotations

import sys
import time

from chessle_solver import (
    Solver,
    build_prefix_pool,
    find_best_legal_probe,
    find_best_legal_probe_tree,
    load_all_entries,
    max_possible_entropy,
    simulate,
    weighted_average,
)


def run(depth: int, label: str, probe_budget: int, beam_width: int):
    entries = load_all_entries()
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

        tree_report = find_best_legal_probe_tree(pool, depth, beam_width=beam_width)
        if tree_report.best:
            tb = tree_report.best
            is_named = tb.moves in weighted_pool
            print(
                f"Best tree-search probe (beam={beam_width}, {tree_report.nodes_expanded} legal "
                f"nodes scored): {' '.join(tb.moves)}  (entropy {tb.true_entropy:.2f} bits"
                f"{', a REAL named opening' if is_named else ', NOT a named opening'})"
            )
            if tb.true_entropy > h:
                print("  -> tree probe beats the corpus-restricted opener.")
            if probe_report.best and tb.true_entropy > probe_report.best.true_entropy:
                print("  -> tree probe beats the relaxed-ranking probe too.")
        else:
            print("Best tree-search probe: beam died out before reaching full depth")

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
    beam_width = 200
    if "--beam-width" in args:
        i = args.index("--beam-width")
        beam_width = int(args[i + 1])
        del args[i : i + 2]
    which = args[0] if args else "both"
    if which in ("normal", "both"):
        run(6, "Normal", probe_budget, beam_width)
    if which in ("expert", "both"):
        run(10, "Expert", probe_budget, beam_width)
