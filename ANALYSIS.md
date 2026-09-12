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

**Simplification:** guesses (like answers) are restricted to prefixes that
appear in the same opening corpus. This is the same kind of simplification
Wordle solvers already make (a "valid guess" is still restricted to an
actual dictionary, not literally any 5-letter string) — it just needed to
be stated explicitly here because unlike Wordle, Chessle's real UI doesn't
enforce this restriction on the player. It means the bot below can only
ever recommend openings that are themselves book theory, which in practice
is exactly what a strong human player would do too.

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

## 6. Results

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

**The "slate"/"crane" answer:** for Normal difficulty, the recommended
opener is **`d4 Nf6 Nf3 e6 Nc3 d5`** (a Queen's Gambit / Nimzo-ish setup) —
under the v1 uniform model it's instead **`e4 e5 Nf3 Nf6 d4 d5`** (a
symmetric open-game mainline). Interestingly, at Expert (10-ply) depth both
models agree on the same opener: **`c4 c5 Nf3 Nc6 Nc3 Nf6 e3 e6 d4 d5`**
(a Symmetrical English) — likely because at that depth the corpus itself
is sparser and dominated by a few very well-attested long mainlines, so
"most informative" and "most popular" converge on the same line.

## 7. Limitations / natural next steps

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
- **Guess space still corpus-restricted** (§4) — a truly unrestricted
  legal-move guesser is a different (much larger) search problem.

## Code layout

```
openings_corpus.tsv          # the "alphabet": 3,810 named opening lines (ECO A-E)
chessle_solver/
  corpus.py                  # load + collapse the corpus into weighted prefix pools
  match.py                   # Chessle's exact feedback algorithm
  entropy.py                 # information/entropy calculations
  solver.py                  # entropy-maximizing guess selection + game loop
  simulate.py                # run the solver across every candidate answer
main.py                      # CLI: prints best openers + simulation results
```

Run it: `python3 main.py both` (or `normal` / `expert`).
