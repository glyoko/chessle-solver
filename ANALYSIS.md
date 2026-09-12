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

### Normal (6-ply guesses, 652 distinct candidates)

Max possible entropy at this pool size: 9.35 bits.

| Solver | Best opening guess | Opener entropy | Avg guesses (uniform test) | Avg guesses (weighted test) |
|---|---|---|---|---|
| v1 (uniform prior) | `e4 e5 Nf3 Nf6 d4 d5` | 6.54 bits | 3.193 | 3.540 |
| v2 (weighted prior) | `d4 Nf6 Nf3 e6 Nc3 d5` | 5.74 bits | 3.218 | **2.740** |

### Expert (10-ply guesses, 682 distinct candidates)

Max possible entropy at this pool size: 9.41 bits.

| Solver | Best opening guess | Opener entropy | Avg guesses (uniform test) | Avg guesses (weighted test) |
|---|---|---|---|---|
| v1 (uniform prior) | `c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5` | 8.01 bits | 2.603 | 2.997 |
| v2 (weighted prior) | `c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5` | 7.16 bits | 2.614 | **2.561** |

This is the same pattern the video found: v1 has slightly *better* raw
average against a uniform test set (it's purpose-built to maximize entropy
under exactly that assumption), but under the popularity-weighted world —
the one that's actually supposed to resemble how Chessle picks answers — v2
wins clearly, cutting Normal-mode games from 3.54 to 2.74 average guesses.

These openers are, however, only optimal *among real named openings* —
see §8, which lifts that restriction and finds something better in every
case.

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

**Results**, `python3 main.py both --probe-budget 300000`:

| Mode | Solver | Corpus-restricted opener (entropy) | Best legal probe found (entropy) | Named opening? | Combos scanned / legal |
|---|---|---|---|---|---|
| Normal | v1 | `e4 e5 Nf3 Nf6 d4 d5` (6.54 bits) | `d4 e5 Nf3 Nf6 Nc3 d5` (**6.74 bits**) | No | 20,000 / 4,652 |
| Normal | v2 | `d4 Nf6 Nf3 e6 Nc3 d5` (5.74 bits) | `d4 d5 Nf3 e6 Nc3 Nf6` (**5.78 bits**) | No | 20,000 / 4,419 |
| Expert | v1 | `c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5` (8.01 bits) | `d4 e5 Nf3 Nc6 Nc3 Nf6 e3 Be7 d5 O-O` (**8.05 bits**) | No | 300,000 / 668 |
| Expert | v2 | `c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5` (7.16 bits) | `d4 e5 c4 Nc6 Nc3 Nf6 d5 Be7 Nf3 O-O` (**7.18 bits**) | No | 300,000 / 593 |

**The intuition was right**: in all four cases the winning sequence is
confirmed (checked directly against `openings_corpus.tsv`) to be **not** a
named opening at all — it's a legal splice that no single real line plays,
and it beats every actual named opening in the corpus at maximizing
information. The Wordle analogy holds: the best Chessle opener, like the
best Wordle opener, doesn't need to be a plausible answer.

Two honest caveats on how far this goes:

- **The margins are small** (6.54→6.74, 5.74→5.78, 8.01→8.05, 7.16→7.18
  bits) — a real, confirmed improvement, not a blowout. The corpus of real
  openings turns out to already be quite well information-optimized,
  which makes sense: popular openings are popular partly *because* they
  lead to sharply different resulting positions.
- **Legal sequences get rare fast as depth grows.** At 10 plies, only
  roughly 1 in 500 scanned combinations turned out to be legal at all, and
  the winning one wasn't found until deep into a 300,000-combination scan
  (attempt #194,190 for v1). A larger budget might still find something
  better; this is a budget-limited heuristic search, not an exhaustive
  proof of the true maximum.
- This section only re-optimizes the **opening guess**. The full-game
  simulation in §6 still uses the corpus-restricted solver for turns 2+ —
  extending per-turn probing to the (much smaller, rapidly shrinking)
  candidate pools after guess 1 is a natural next step, not yet done.

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
- **Probing (§8) is opener-only and budget-limited**, not a full
  replacement for the corpus-restricted solver used at every turn.

## Code layout

```
openings_corpus.tsv          # the "alphabet": 3,810 named opening lines (ECO A-E)
chessle_solver/
  corpus.py                  # load + collapse the corpus into weighted prefix pools
  match.py                   # Chessle's exact feedback algorithm
  entropy.py                 # information/entropy calculations
  solver.py                  # entropy-maximizing guess selection + game loop (corpus-restricted)
  legal.py                   # real chess-legality check (python-chess)
  probe.py                   # relaxed-then-legal-filtered search for off-book probe guesses (§8)
  simulate.py                # run the solver across every candidate answer
main.py                      # CLI: prints best openers (corpus + probe) + simulation results
```

Run it: `python3 main.py both` (or `normal` / `expert`, optionally
`--probe-budget N`, default 20,000 — pass a larger budget like 300,000 for
Expert mode, since legal sequences are much rarer at 10 plies).
