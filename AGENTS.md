# AGENTS.md

Context for anyone (human or agent) picking up work on this repo.

## What this project is

An adaptation of [3Blue1Brown's Wordle/entropy analysis](https://www.youtube.com/watch?v=v68zYyaEmEA)
to [Chessle](https://jackli.gg/chessle/), a Wordle clone where the "word"
is a sequence of chess opening moves. Full writeup: `ANALYSIS.md`. This
file is about the *engineering* context that isn't already in there:
what's been tried, what didn't work, and why the code is shaped the way
it is.

## How Chessle actually works (reverse-engineered, not documented)

- Guess a full move sequence from the starting position: 6 plies for
  Normal, 10 for Expert.
- Feedback is Wordle's exact two-pass duplicate-safe algorithm
  (green/yellow/gray), applied to SAN move tokens instead of letters.
  Implemented faithfully in `chessle_solver/match.py`.
- 6 guesses total. "Exact" notation matching only (not the looser
  "piece-square" mode) is implemented, since that's Chessle's default.
- The daily puzzle API (`https://d1vwq1uqg5c4bn.cloudfront.net/`) sits
  behind CloudFront caching that ignores query strings (`?id=`) — every
  request returns the same puzzle regardless of parameters. There is no
  way to enumerate past/future puzzles or discover Chessle's real internal
  answer list this way. Accept this as a permanent limitation.

## Where Chessle's answers come from

Confirmed (by exact match between a live puzzle and this dataset) that
Chessle draws from a named-opening tree structure, not raw historical
games: [`lichess-org/chess-openings`](https://github.com/lichess-org/chess-openings)
(`openings_corpus.tsv`, 3,810 entries, ECO A–E). Chessle's naming
convention is "longest matching prefix" against this kind of tree.

**But this corpus has real gaps**: some named lines (e.g. the Bird Opening
family, ECO A03) dead-end before reaching 10 plies under any name, yet
Chessle still generates full-depth puzzles for them — it draws on some
continuation source beyond ECO naming. Confirmed and fixed:

- **First attempt (abandoned): Stockfish.** Extended dead-ends with the
  engine's own best move. This did NOT reproduce the real Chessle answer
  for a live test case (engine chose `3. e3`, Chessle's real answer used
  `3. g3`) — good evidence the answers aren't engine-generated. All of
  this work (`chessle_solver/extend.py`, `scripts/build_engine_extensions.py`)
  was written, tested, found wrong, and fully deleted. If you're tempted
  to try engine analysis again for corpus gaps: don't, this was already
  tried and falsified against real data.
- **What worked: KingBase 2018.** Mined the [KingBase 2018 database](https://archive.org/details/KingBase2018)
  (~2M real games, 2000+ ELO players, 1990–2018, free public PGN download)
  for the single most common real continuation of each dead-end prefix.
  This exactly reproduced the live test puzzle. Output lives in
  `kingbase_extensions.tsv`, built by `scripts/build_kingbase_extensions.py`.
  The 429MB source zip (`scratch_data/KingBase2018-pgn.zip`) is gitignored
  — don't commit it; re-download from Archive.org if you need to rebuild.
- **Considered, not used: Lichess Opening Explorer API.** Both
  `/lichess` and `/masters` endpoints now require OAuth2 (confirmed via
  the official `lichess-org/api` OpenAPI spec, not just an observed 401).
  Deliberately avoided to sidestep any account-risk tradeoff, even though
  the user had an oauth token available. If this ever becomes worth
  revisiting, that tradeoff needs re-raising with the user first.

## Corpus architecture: built to be swappable

`chessle_solver/corpus.py` loads any TSV (`eco`, `name`, `pgn`, optional
`weight` columns) into `OpeningEntry` objects; `load_all_entries()`
concatenates `openings_corpus.tsv` + `kingbase_extensions.tsv` (silently
skipping either if missing); `build_prefix_pool(depth)` collapses that
into the `{move_tuple: weight}` dict shape every downstream module
consumes. Nothing past `corpus.py` knows or cares where the data came
from — swap in a new loader with the same dict-of-tuples-to-weight return
shape and everything else (entropy, solver, simulate) keeps working
unchanged. This was an explicit requirement from the start of the project
and has already paid off once (ECO-only → ECO+KingBase without touching
any other module).

## The core insight that shaped most of this project

Wordle's guess dictionary (~13,000 words) is deliberately *larger* than
its answer list (~2,315) specifically so a guess can be a good
letter-splitter without needing to be a plausible answer (`slate`,
`crane` are guesses *because* they split information well). Chessle has
no such distinction if you restrict guesses to the corpus — that
restriction throws away exactly the kind of high-information "probe"
move Wordle relies on. Chessle's *true* guess space is "any legal move
sequence," which is intractably large to brute-force (~30 legal moves per
ply → ~30^10 sequences at Expert depth).

Confirmed empirically, twice, that this actually matters (not just a
theoretical concern): off-book guesses beat every real named opening in
the corpus, at both Normal and Expert depth, once the search was good
enough to find them.

## Two probe-search implementations exist — know which one is used where

- **`chessle_solver/probe.py` (relaxed-then-filter).** Ranks moves per ply
  independently by a binary-entropy proxy, ignoring chess legality
  entirely, then enumerates combinations in that order checking legality
  after the fact. **This has a structural flaw, not just an efficiency
  one**: the top of the per-ply ranking systematically reuses the same
  popular moves across different plies (e.g. picks `Nf3` as the top move
  at three different plies), which is illegal by construction (a knight
  can't be on f3 three times) — so the vast majority of "top" candidates
  collide, and no amount of extra budget fixes that, it just burns through
  more near-duplicate collisions. At Expert depth, only ~1 in 1,000–2,000
  scanned combinations turns out legal. Kept in the codebase only for
  side-by-side comparison printing in `main.py`; the actual `Solver` never
  uses it.
- **`chessle_solver/tree_probe.py` (beam search over the real game tree,
  legal by construction).** Builds the guess move-by-move, at each ply
  branching only into `board.legal_moves` (via `python-chess`), scoring
  each partial sequence with the *real* entropy formula against the
  length-truncated answer pool, and keeping only the top `beam_width`
  candidates before extending further. Every candidate ever scored is
  legal. This is what `Solver` actually uses. It's still a heuristic (a
  narrow beam can prune away a prefix that would've led somewhere better),
  but it's a bounded, principled approximation instead of hoping a
  legality-blind ranking stumbles into legal territory.

If asked to improve probe search further, extend `tree_probe.py`, not
`probe.py`.

## How `Solver` actually picks guesses (see `chessle_solver/solver.py`)

- **Turn 1**: a hardcoded off-book opener per depth (`HARDCODED_OPENERS`,
  found once offline via a wide beam=300 tree-search probe — both priors
  converged on the same sequence per depth, so it's keyed by depth, not
  by prior). `opening_guess()` still recomputes this guess's *true*
  entropy against whatever answer pool it's given and compares it against
  the cheap corpus-only search before trusting it, so it never silently
  regresses if the corpus changes. A live search (`tree_probe_beam_width`)
  is the fallback for any depth without a hardcoded entry.
- **Every later turn**: re-runs the same tree-search probe against the
  *remaining* candidates, at a much smaller `subsequent_beam_width`
  (default 10) — this now runs on every turn of every simulated game, so
  it needs to stay cheap. Only used if it beats the corpus-restricted
  guess for that remaining pool.

This wiring took two passes to get right: an easy mistake to make (and one
this project actually made) is computing a great off-book opener via the
probe search and only ever *printing* it, while the `Solver` object used
for `simulate()`/real play still only searches the corpus pool
underneath. If average-guesses numbers ever look suspiciously unaffected
by a probe-search change, check whether the probe result is actually
wired into `Solver.opening_guess()`/`choose_guess()`, not just printed.

## Current headline numbers (KingBase-enriched corpus, off-book solver)

From `python3 main.py both --beam-width 10` (~4.9 min total):

| Mode | Candidates | Total entropy (uniform) | Solver's actual turn-1 guess | Avg guesses (uniform) |
|---|---|---|---|---|
| Normal (6-ply) | 1,024 | 10.00 bits | `d4 e5 Nf3 Nf6 Nc3 d5` (off-book) | 3.124 |
| Expert (10-ply) | 1,702 | 10.73 bits | `e4 d5 Nf3 e6 Nc3 Nf6 d4 c5 Bc4 Nc6` (off-book) | 2.596 |

"Total entropy" here = `log2(candidate count)` under a uniform prior =
literally how many bits of information are needed to identify the secret
before any guess is made. These numbers will drift if the corpus is
enriched further — regenerate via `main.py`, don't assume these are
permanent.

`ANALYSIS.md` is **not guaranteed to be in sync** with the current solver
behavior — it was last refreshed after the KingBase enrichment but before
the off-book-opener wiring (`ea6024a`/`c69eae9`) landed. Numbers there for
§6/§8 may reflect the corpus-only solver, not what `Solver` actually plays
now. If accuracy here matters, regenerate and diff before trusting it.

## Process notes for working with this user on this repo

- **Always confirm before running any Python** (`python3 ...` via Bash,
  including inline `-c` snippets) — a standing instruction from earlier in
  this project, not a one-off. Ask, don't just run.
- **Only commit when explicitly asked.** Don't commit proactively even
  after a successful change.
- **New branch when asked for one, but not by default** — some changes in
  this project were explicitly requested on a separate branch, others
  were explicitly requested on the current branch. Follow what's asked
  each time rather than assuming a pattern.
- **Don't gitignore-then-commit large binary artifacts.** `scratch_data/`
  (KingBase zip, ~416MB) is gitignored on purpose — check before adding
  anything in there to a commit.
- This repo has had multiple concurrent sessions/agents working on it at
  once (observed: branches `asdf`, `watch-solver`, and a worktree
  `worktree-watch-solver-updates` with unrelated in-progress work on a
  `scripts/watch_solver.py` demo script, none of which came from this
  conversation's work). Check `git status`/`git branch` before assuming
  you know the full state of the repo, and don't assume `main` is the only
  active branch.

## Code layout

```
openings_corpus.tsv          # base "alphabet": 3,810 named ECO opening lines
kingbase_extensions.tsv      # real-game continuations for corpus dead-ends
chessle_solver/
  corpus.py                  # load + collapse corpus/extensions into weighted prefix pools
  dead_ends.py                # find opening prefixes with no long-enough named continuation
  match.py                   # Chessle's exact feedback algorithm
  entropy.py                 # information/entropy calculations
  legal.py                   # real chess-legality check (python-chess)
  probe.py                   # relaxed-ranking probe (comparison only, NOT used by Solver)
  tree_probe.py               # legal-by-construction beam search (what Solver actually uses)
  solver.py                  # entropy-maximizing guess selection + game loop
  simulate.py                # run the solver across every candidate answer
scripts/
  build_kingbase_extensions.py  # mine KingBase PGNs for dead-end continuations
main.py                      # CLI: prints openers/probes + simulation results
```

Run it: `python3 main.py [normal|expert|both] [--probe-budget N] [--beam-width N]`.
