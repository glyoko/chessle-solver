"""
CLI entry point: find the best opening guess and simulate full games for
Chessle's Normal (6-ply) and Expert (10-ply) difficulties, both with a
uniform prior over answers (v1) and a popularity-weighted prior (v2).

Since Chessle's real guess space is "any legal move sequence," not just
real named openings (see ANALYSIS.md section 8), Solver never restricts
itself to the corpus alone:
  - Turn 1 uses a hardcoded off-book guess per depth (chessle_solver.solver.
    HARDCODED_OPENERS), found once offline via a wide (beam=300) tree-search
    probe -- see ANALYSIS.md section 8b. Turn 1 is guess-independent of any
    particular secret, so that expensive search only ever needed to run
    once, not on every Solver construction.
  - Every later turn re-runs the same legal-by-construction tree-search
    probe (chessle_solver.tree_probe) live, against the shrinking remaining-
    candidates pool, at a much smaller `--beam-width` (default 10, since
    this now runs on every turn of every simulated game).
  - chessle_solver.probe (the older relaxed-ranking-then-filter approach)
    is kept only for side-by-side comparison in this script's output --
    Solver itself never uses it, since the tree-search probe strictly
    dominates it (every candidate it scores is legal by construction).

Usage: python3 main.py [normal|expert|both] [--probe-budget N] [--beam-width N]
"""
from __future__ import annotations

import sys
import time

from chessle_solver import (
    Solver,
    build_prefix_pool,
    find_best_legal_probe,
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
        "v1 (uniform prior)": (
            uniform_pool,
            Solver(guess_pool, uniform_pool, subsequent_beam_width=beam_width),
        ),
        "v2 (weighted prior)": (
            weighted_pool,
            Solver(guess_pool, weighted_pool, subsequent_beam_width=beam_width),
        ),
    }

    for name, (pool, solver) in solvers.items():
        t0 = time.time()
        corpus_opener, corpus_h = solver.corpus_only_opener()
        opener, h = solver.opening_guess()
        is_probe = solver.opener_is_off_book_probe()

        print(f"\n-- {name} --")
        print(
            f"Best opening guess (real named openings only): {' '.join(corpus_opener)}"
            f"  (entropy {corpus_h:.2f} bits)"
        )

        probe_report = find_best_legal_probe(pool, depth, max_attempts=probe_budget)
        if probe_report.best:
            b = probe_report.best
            is_named = b.moves in weighted_pool
            print(
                f"Best legal probe (any legal sequence, {probe_report.total_attempts} scanned, "
                f"{probe_report.legal_found} legal): {' '.join(b.moves)}  (entropy {b.true_entropy:.2f} bits"
                f"{', a REAL named opening' if is_named else ', NOT a named opening'})"
            )
            if b.true_entropy > corpus_h:
                print("  -> relaxed probe beats the corpus-restricted opener.")
        else:
            print(f"Best legal probe: none found within budget ({probe_budget} scanned)")

        print(
            f"Solver's actual turn-1 guess (hardcoded off-book opener): {' '.join(opener)}"
            f"  (entropy {h:.2f} bits"
            f"{', OFF-BOOK -- beats every real opening in the corpus' if is_probe else ', same as the corpus opener above'})"
        )

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
    beam_width = 10
    if "--beam-width" in args:
        i = args.index("--beam-width")
        beam_width = int(args[i + 1])
        del args[i : i + 2]
    which = args[0] if args else "both"
    if which in ("normal", "both"):
        run(6, "Normal", probe_budget, beam_width)
    if which in ("expert", "both"):
        run(10, "Expert", probe_budget, beam_width)
