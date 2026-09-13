# Solving Chessle with information theory

An adaptation of [3Blue1Brown's Wordle/entropy analysis](https://www.youtube.com/watch?v=v68zYyaEmEA)
to [Chessle](https://jackli.gg/chessle/), a Wordle clone where you guess an
opening's move sequence instead of a five-letter word.

## 1. How Chessle actually works

Reverse-engineered from its client bundle (`js/game.min.js`) and its puzzle
API, since the page ships no written rules:

- **The guess.** You play out a sequence of legal chess moves from the
  starting position (dragging pieces on a real board). "Normal" difficulty
  wants 6 plies (3 full moves); "Expert" wants 10 plies (5 full moves).
- **The answer.** A fixed move sequence for that day, drawn from a named
  chess opening, e.g. today's (2026-09-12) answer is
  `f4 d5 Nf3 Nf6 g3 g6 Bg2 Bg7 O-O O-O`, named **"Bird Opening: Dutch
  Variation."**
- **Feedback.** Chessle's `compareSequences` function is, move-for-move,
  Wordle's two-pass duplicate-safe letter-matching algorithm:
  1. mark exact-position matches green, consuming one copy from the
     answer's move-count bag;
  2. for every remaining guess move, mark it yellow if the answer still has
     an unconsumed copy anywhere, else gray.

  It's implemented in `chessle_solver/match.py:compare_sequences`, copied
  faithfully from the minified source.
- **6 guesses**, exactly like Wordle.
- There's also an "Exact" vs. "Piece-Square" notation-matching toggle
  (whether `Nf3` must match `Nf3` exactly, or a looser piece+destination
  match is accepted). We implement only "Exact," Chessle's default.

## 2. Where the answers come from

This was the open question going in: does Chessle draw from a curated list
of *named openings* (ECO-style), or from real historical games truncated to
N plies?

Querying the puzzle API (`https://d1vwq1uqg5c4bn.cloudfront.net/`) confirmed
today's answer/name pair above. Cross-checking that against the public
[`lichess-org/chess-openings`](https://github.com/lichess-org/chess-openings)
dataset finds an **exact match**: ECO code A03, name "Bird Opening: Dutch
Variation," PGN `1. f4 d5`. Chessle's answer continues 8 plies past where
that entry's name last changes (into unnamed, further book theory), so its
naming scheme is clearly "walk the opening tree and report the name of the
longest matching prefix" — which is exactly the structure of this ECO
dataset (many entries share a prefix and only diverge in name at a specific
branch point).

This is strong evidence Chessle's answers are drawn from a named-opening
tree, not raw game history — a real historical game reaching this exact
position wouldn't reliably carry a clean ECO-style name at every depth.

I could *not* recover Chessle's actual internal list: the puzzle API sits
behind CloudFront, which caches the daily response regardless of query
string (`?id=`), so every request just returns today's puzzle. So this
isn't proof Chessle uses *this specific* dataset byte-for-byte — only that
whatever it uses has this same tree structure and at least one identical
entry. Good enough to build on, not good enough to claim certainty.

**The alphabet**, i.e. the combined corpus used as the stand-in for
Chessle's answer-generation tree, is saved as
[`openings_corpus.tsv`](./openings_corpus.tsv) in this directory (3,810
named opening lines, ECO codes A–E, concatenated from the five upstream
TSV files).

### Swappability

Nothing downstream depends on that specific file. `chessle_solver/corpus.py`
loads it into a plain `{move_tuple: weight}` dict, and every other module
(`entropy.py`, `solver.py`, `simulate.py`) only ever consumes that shape. If
Chessle's real list is ever recovered, or a real-game-frequency database is
preferred instead, swap in a new loader that returns the same dict shape —
nothing else changes.

### Closing a real corpus gap with real-game data

Testing the solver against a live puzzle exposed a genuine hole: some named
opening lines (e.g. the Bird Opening family, ECO A03) have no entry that
reaches 10 plies at all under any name — the named theory tree "dead-ends"
early — yet Chessle still generated a full 10-ply puzzle from that family.
So Chessle's answer tree extends past where ECO naming stops.

The first fix attempted was Stockfish: extend each dead-end with the
engine's own top move. This *didn't* reproduce the real puzzle's
continuation (the engine chose `3. e3` where the actual Chessle answer
played `3. g3`) — good evidence Chessle's tree isn't engine-generated, and
this approach was abandoned.

The fix that worked: mine the [KingBase 2018](https://archive.org/details/KingBase2018)
database (~2M real games by 2000+ ELO players, 1990–2018) for the single
most common real continuation actually played from each dead-end prefix
(`scripts/build_kingbase_extensions.py`, output saved to
`kingbase_extensions.tsv`, same shape as the main corpus plus a `weight`
column). This exactly reproduced the live puzzle's answer (matched against
175 real KingBase games), and the full solver now wins that live puzzle in
2 guesses. `chessle_solver/corpus.py:load_all_entries()` transparently
concatenates both files — `kingbase_extensions.tsv` is optional and
silently skipped if absent, so this is a genuine example of the swap-in
architecture paying off, not a special case bolted on top of it.

## 3. The entropy math (unchanged from Wordle)

Same definitions as the video, just with "move" standing in for "letter"
and "opening line" for "word":

- A guess produces one of a fixed set of feedback patterns (green/yellow/
  gray per ply — `3^N` possible patterns for an N-ply guess).
- Each candidate answer's *prior probability* of being the real answer
  induces a probability distribution over those patterns for a given guess.
- **Information** of an observed pattern = `-log2(P(pattern))`.
- **Entropy** of a guess = the expected information over that whole
  distribution = `sum(P(pattern) * -log2(P(pattern)))`.
- The best guess at any point is the one that maximizes entropy — the one
  whose outcome is, on average, most surprising, because "surprising" is
  exactly "cuts the remaining possibility space down the most."

This is implemented directly in `chessle_solver/entropy.py`, structurally
identical to the video's formula.

## 4. The one real structural difference from Wordle: the guess space

Wordle's guess dictionary (~13,000 words) is small enough to brute-force
directly. Chessle's isn't: you can drag any legal piece to any legal
square, so the true guess space is every legal N-ply move sequence from the
starting position — computationally unbounded for our purposes, and mostly
made of guesses no rational player would ever try (nobody's opening guess
is `a4 a5 a3 a6 h4 h5`).

**Initial simplification (later revisited in §8):** guesses were first
restricted to prefixes that appear in the same opening corpus, the same
kind of simplification Wordle solvers already make (a "valid guess" is
still restricted to an actual dictionary, not literally any 5-letter
string). But this analogy breaks down in one important way: Wordle's
guess dictionary (~13,000 words) is *deliberately larger* than its answer
list (~2,315), specifically so a guess can be a good letter-splitter
without needing to be a plausible answer itself (`slate`, `crane`, `tares`
are guesses precisely *because* they split information well, not because
they're likely Wordle answers). Restricting Chessle's guesses to the
answer corpus collapses that distinction entirely — it rules out exactly
the kind of high-information "probe" move Wordle relies on. §8 fixes this.

## 5. Version 1 vs Version 2, exactly like the video

- **v1 — uniform prior.** Every distinct N-ply prefix in the corpus is
  treated as equally likely to be the answer. Pure entropy-maximization,
  no notion of "some openings are more likely than others."
- **v2 — popularity-weighted prior.** Chessle's actual answer-selection
  frequencies aren't available (see §2), so as a proxy we weight each
  distinct N-ply prefix by **how many named entries in the corpus share it**
  — a busy branch point in the opening tree (lots of deeper named
  variations hang off it) reads as "well-established mainline," a
  weight-1 prefix reads as "obscure, rarely-seen line." This plays the same
  role Google Ngram word frequency played for Wordle. It's a genuine
  approximation and the weakest link in this analysis — flagged, not
  hidden.

Both share one solver (`chessle_solver/solver.py`): search the guess pool,
maximize entropy against the current (possibly re-weighted) candidate set,
repeat. No separate endgame heuristic was added (the video's "expected
score" refinement, which trades pure information gain for probability of
just winning soon, would be a natural next step here too — see §7).

## 6. Results (corpus-restricted guesses)

Run via `python3 main.py both`. Two metrics are reported per run because
the two solvers optimize for *different* assumed worlds: "secrets equally
likely" tests every candidate line once, unweighted; "secrets weighted by
popularity" re-scores the same games under the v2 popularity prior — the
fairer test of what the popularity weighting actually buys you.

### Normal (6-ply guesses, 1,024 distinct candidates)

Max possible entropy at this pool size: 10.00 bits.

| Solver | Best opening guess | Opener entropy | Avg guesses (uniform test) | Avg guesses (weighted test) |
|---|---|---|---|---|
| v1 (uniform prior) | `e4 e5 Nf3 Nf6 d4 d5` | 6.83 bits | 3.227 | 3.486 |
| v2 (weighted prior) | `d4 Nf6 Nf3 e6 Nc3 d5` | 6.10 bits | 3.245 | **2.853** |

### Expert (10-ply guesses, 1,702 distinct candidates)

Max possible entropy at this pool size: 10.73 bits.

| Solver | Best opening guess | Opener entropy | Avg guesses (uniform test) | Avg guesses (weighted test) |
|---|---|---|---|---|
| v1 (uniform prior) | `c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5` | 9.06 bits | 2.612 | 2.825 |
| v2 (weighted prior) | `c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5` | 8.41 bits | 2.621 | **2.611** |

This is the same pattern the video found: v1 has slightly *better* raw
average against a uniform test set (it's purpose-built to maximize entropy
under exactly that assumption), but under the popularity-weighted world —
the one that's actually supposed to resemble how Chessle picks answers — v2
wins clearly.

(These numbers reflect the KingBase-enriched corpus — see §2 — which grew
the candidate pools considerably from an earlier ECO-only pass: Normal
652→1,024, Expert 682→1,702. Real answers that used to fall outside the
corpus, like today's Bird Opening puzzle, are now reachable.)

These openers are, however, only optimal *among real named openings* —
see §8, which lifts that restriction, though the picture there has changed
too now that the corpus is richer.

## 8. Beating "real openings only": probing with off-book legal moves

§4 flagged a real gap: restricting guesses to the answer corpus throws
away exactly the kind of information-maximizing "probe" move Wordle relies
on (`slate`/`crane`/`tares` aren't likely Wordle answers — they're guesses
*because* they split letters well). Chessle's true guess space is "any
legal move sequence," which is far too large to brute-force directly
(~30 legal moves per ply → roughly `30^6` to `30^10` sequences).

**The workaround** (`chessle_solver/probe.py`): solve an easier, *relaxed*
version of the problem first, then filter for the real constraint.

1. For each ply position independently, ignore both legality and
   cross-position correlation. Look at the answer pool's marginal
   distribution of moves at just that one slot, and rank candidate moves
   by how close to a 50/50 split they produce there (binary entropy
   `-[p·log2(p) + (1-p)·log2(1-p))]`). This is *not* the real Chessle
   objective — it drops the yellow/duplicate cross-referencing that ties
   positions together (which matters more here than in Wordle, since
   opening theory transposes constantly: the same move often appears at
   different plies across different move-orders) — but it's cheap.
2. Enumerate *combinations* of per-position picks in strictly
   non-increasing order of their relaxed total score (a standard
   best-first search over sorted per-position candidate lists — same
   family of technique as k-shortest-path search).
3. For each combination, in that order, check real chess legality (via
   `python-chess`). Whenever one is legal, score it with the *real* entropy
   function (not the relaxed proxy that generated it) and keep whichever
   legal sequence scores highest. The relaxed ranking only decides search
   order; it never picks the winner.

Because step 1 optimizes a different, easier objective than true entropy,
this is a strong *candidate*, not a proof of the global optimum — a bigger
search budget can (and did) turn up something better.

**Results**, `python3 main.py normal --probe-budget 20000` and
`python3 main.py expert --probe-budget 300000` (larger Expert budget since
legal sequences get much rarer at 10 plies — see caveats below), run
against the **KingBase-enriched corpus** (§2):

| Mode | Solver | Corpus-restricted opener (entropy) | Best legal probe found (entropy) | Named opening? | Combos scanned / legal |
|---|---|---|---|---|---|
| Normal | v1 | `e4 e5 Nf3 Nf6 d4 d5` (6.83 bits) | `d4 e5 Nf3 Nf6 Nc3 d5` (**6.97 bits**) | No | 20,000 / 4,339 |
| Normal | v2 | `d4 Nf6 Nf3 e6 Nc3 d5` (6.10 bits) | `d4 e5 Nf3 Nf6 Nc3 d5` (**6.15 bits**) | No | 20,000 / 4,306 |
| Expert | v1 | `c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5` (**9.06 bits**) | `e4 e5 c4 d5 Nc3 Nf6 d4 g6 Nf3 Nc6` (9.01 bits) | No | 300,000 / 159 |
| Expert | v2 | `c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5` (**8.41 bits**) | `d4 e5 c4 Nc6 Nc3 d5 e3 Nf6 Nf3 g6` (8.39 bits) | No | 300,000 / 332 |

**At Expert depth, this relaxed approach turned out to have a structural
flaw, not just a budget problem.** Because step 1 scores each ply position
completely independently, its top-ranked combinations systematically
collide: the single most popular move at ply 2, 6, *and* 8 all turned out
to be `Nf3` — asking White to move the same knight to the same square three
separate times, which is illegal for a reason no per-ply ranking can see.
That's why only ~1 in 1,900–5,000 combinations checked was legal at all
(159–332 legal out of 300,000 scanned), and it's why the relaxed probe
appeared to lose to the corpus-restricted opener at Expert depth in an
earlier pass (9.01 vs. 9.06 bits) — not because off-book guessing stopped
helping, but because this search method couldn't reliably reach the legal
sequences that would have shown it still does.

### 8b. Fixing it: a legal-by-construction tree search

`chessle_solver/tree_probe.py` replaces the relaxed-then-filter design with
a **beam search over the real game tree**: build the guess move by move,
branching at each ply only into moves `python-chess` confirms are actually
legal from the current position. Every candidate ever scored is legal —
there's no filtering step because there's nothing to filter. It's scored
with the same true entropy function throughout (against the answer pool
truncated to the guess's current length), which also captures the
green/yellow cross-referencing between plies that the relaxed ranking's
per-position proxy drops. The one heuristic left is `beam_width`: how many
of the best partial sequences to keep before extending further at each ply
— a real, bounded approximation (a narrow beam can discard a prefix that
would've led somewhere better), but a fundamentally different kind of
approximation than "hope the legality-blind top-of-ranking happens to be
legal."

**Results**, `python3 main.py both --beam-width 300`:

| Mode | Solver | Corpus opener | Relaxed probe (§8, 20,000 scanned) | **Tree probe (beam=300)** | Legal nodes scored |
|---|---|---|---|---|---|
| Normal | v1 | 6.83 bits | `d4 e5 Nf3 Nf6 Nc3 d5` (6.97 bits) | `d4 e5 Nf3 Nf6 Nc3 d5` (**6.97 bits**, tied) | 32,828 |
| Normal | v2 | 6.10 bits | `d4 e5 Nf3 Nf6 Nc3 d5` (6.15 bits) | `d4 e5 Nf3 Nf6 Nc3 d5` (**6.15 bits**, tied) | 32,325 |
| Expert | v1 | 9.06 bits | `e4 e5 c4 d5 Nc3 Nf6 d4 g6 Nf3 Nc6` (9.01 bits) | `e4 d5 Nf3 e6 Nc3 Nf6 d4 c5 Bc4 Nc6` (**9.19 bits**) | 73,010 |
| Expert | v2 | 8.41 bits | `d4 e5 c4 Nc6 Nc3 d5 e3 Nf6 Nf3 g6` (8.39 bits) | `e4 d5 Nf3 e6 Nc3 Nf6 d4 c5 Bc4 Nc6` (**8.51 bits**) | 72,051

**This restores the original finding and sharpens it.** At Expert depth,
off-book guessing *does* still beat every real named opening — the earlier
"corpus wins at Expert" result was an artifact of the relaxed probe's
legality-blindness, not a real property of the enriched corpus. The tree
probe found a strictly better guess (9.19 vs. 9.06 bits for v1) while
scoring **only ~73,000 candidates, every one of them legal** — a quarter of
the relaxed probe's 300,000 mostly-illegal attempts from the earlier pass,
and it still comes out ahead. At Normal depth, where legal sequences aren't
nearly as rare to begin with, both methods land on the identical answer —
the tree search's advantage is specifically in the legality-scarce regime
(Expert's 10 plies), exactly where the relaxed approach's structural flaw
bites hardest.

Caveats:

- **Beam search is still an approximation**, just a differently-shaped one:
  `beam_width` (300 here) trades search thoroughness for compute the same
  way `probe_budget` did for the relaxed method, and a narrower beam can
  discard a promising early prefix. A wider beam might still find something
  better than 9.19/8.51 bits; there's no proof this is the global optimum.
- This section only re-optimizes the **opening guess**. The full-game
  simulation in §6 still uses the corpus-restricted solver for turns 2+ —
  extending tree-based probing to the (much smaller, rapidly shrinking)
  candidate pools after guess 1 is a natural next step, not yet done.
- `probe.py` (the relaxed method) is kept in the codebase for comparison
  (`main.py` runs both side by side) rather than deleted, since it's a
  useful illustration of why legality-aware search structure matters, not
  just search volume.

## 9. Limitations / natural next steps

- **Popularity weight is a proxy, not real data.** Branch-count in a named
  ECO tree correlates with "well-known" but isn't a real frequency
  estimate. If Chessle's real answer distribution (or a large real-game
  database) ever becomes available, swap it in per §2 — the weighting
  interface (`{move_tuple: weight}`) doesn't change.
- **No endgame heuristic.** The video's v2 also fit an `expected score`
  function (remaining uncertainty → expected additional guesses) so the
  bot could choose to "just go for the win" once a guess was likely
  correct, rather than always chasing maximum information. Not
  implemented here; would slot into `Solver.choose_guess`.
- **No multi-step lookahead.** The video's best result used a two-guess
  lookahead search; this bot only ever optimizes the immediate guess.
- **Probing (§8) is opener-only and beam/budget-limited**, not a full
  replacement for the corpus-restricted solver used at every turn.

## Code layout

```
openings_corpus.tsv          # the "alphabet": 3,810 named opening lines (ECO A-E)
kingbase_extensions.tsv      # real-game continuations for corpus dead-ends (§2)
chessle_solver/
  corpus.py                  # load + collapse the corpus into weighted prefix pools
  dead_ends.py                # find named-opening prefixes with no entry reaching target depth
  match.py                   # Chessle's exact feedback algorithm
  entropy.py                 # information/entropy calculations
  solver.py                  # entropy-maximizing guess selection + game loop (corpus-restricted)
  legal.py                   # real chess-legality check (python-chess)
  probe.py                   # relaxed-then-legal-filtered search for off-book probe guesses (§8)
  tree_probe.py               # legal-by-construction beam search over the real game tree (§8b)
  simulate.py                # run the solver across every candidate answer
main.py                      # CLI: prints best openers (corpus + both probes) + simulation results
```

Run it: `python3 main.py both` (or `normal` / `expert`), optionally with
`--probe-budget N` (default 20,000; the relaxed probe, §8) and
`--beam-width N` (default 200; the tree probe, §8b — 300 was used for the
results above and took ~11 minutes total for both modes).
