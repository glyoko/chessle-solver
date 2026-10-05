# chessle-solver

An information-theory solver for [Chessle](https://jackli.gg/chessle/), the
Wordle-style game where the hidden "word" is a sequence of chess opening
moves.

## What this is

Chessle gives you 6 guesses to find a secret opening line: 6 plies (3 full
moves) in Normal mode, 10 plies (5 full moves) in Expert. After each guess,
every move is marked green (right move, right place), yellow (in the line,
wrong place), or gray (not in the line), using the same rules as Wordle.

This repo adapts [3Blue1Brown's Wordle entropy analysis](https://www.youtube.com/watch?v=v68zYyaEmEA)
to that game. The idea is to pick each guess so it maximizes the expected
information (entropy) of the feedback, which splits the remaining possible
answers as evenly as possible.

The project has three main parts:

- **A model of Chessle's answer space.** Chessle's answers come from the
  named-opening tree in
  [`lichess-org/chess-openings`](https://github.com/lichess-org/chess-openings)
  (`openings_corpus.tsv`). Some named lines stop before reaching full
  depth, so those gaps are filled with the most common real continuation
  from the [KingBase 2018](https://archive.org/details/KingBase2018)
  master-games database (`kingbase_extensions.tsv`).
- **A faithful reimplementation of Chessle's feedback**, using Wordle's
  duplicate-safe two-pass algorithm on SAN move tokens.
- **An entropy-maximizing solver.** Its guesses don't have to be real named
  openings. Like Wordle's "probe" words (`crane`, `slate`), the best guesses
  are often legal but off-book move sequences that split the candidates
  better than any real opening does. They're found with a beam search over
  the actual game tree, so every candidate is legal.

For the full writeup with methodology, results, and limitations, see
[`ANALYSIS.md`](ANALYSIS.md). For engineering notes on what's been tried
and why the code looks the way it does, see [`AGENTS.md`](AGENTS.md).

## Best opening guesses

### Expert mode (10 plies)

```
1. e4 d5 2. Nf3 e6 3. Nc3 Nf6 4. d4 c5 5. Bc4 Nc6
```

This is the highest-entropy first guess found: **9.19 bits** against the
1,702-candidate Expert pool under a uniform prior. The solver opens with
this guess and needs **~2.6 guesses on average** to find an Expert answer.

### Normal mode (6 plies)

```
1. d4 e5 2. Nf3 Nf6 3. Nc3 d5
```

This guess scores 6.97 bits against the 1,024-candidate Normal pool, and
the solver averages about 3.1 guesses with it.

These numbers depend on the corpus. If the answer data is enriched, rerun
`main.py` to regenerate them.

## Running it

Requires Python 3.10+.

```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # just python-chess
```

Then run the analysis:

```sh
python3 main.py              # both modes (default)
python3 main.py normal       # 6-ply only
python3 main.py expert       # 10-ply only
```

For each mode, it prints the best corpus-restricted opener, the off-book
probe guesses, and the results of simulating the solver against every
candidate answer (average guesses under uniform and popularity-weighted
priors).

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--beam-width N` | 10 | Beam width for the tree-search probe on turns after the first. Larger is slower but can find better guesses. |
| `--probe-budget N` | 20000 | How many combinations the older relaxed probe (shown for comparison only) scans. |

A full `python3 main.py both --beam-width 10` run takes about 5 minutes.

### Rebuilding the KingBase extensions (optional)

`kingbase_extensions.tsv` is checked in, so you don't need to do this to
run the solver. To regenerate it, download the KingBase 2018 PGN zip
(~430 MB) from [Archive.org](https://archive.org/details/KingBase2018)
into `scratch_data/`, which is gitignored, and run:

```sh
python3 scripts/build_kingbase_extensions.py --zip scratch_data/KingBase2018-pgn.zip --depth 10
```

## Layout

```
openings_corpus.tsv       # named ECO opening lines (Chessle's answer source)
kingbase_extensions.tsv   # real-game continuations for lines that end early
chessle_solver/           # corpus loading, feedback matching, entropy, search, solver, simulation
scripts/                  # data-building scripts
main.py                   # CLI entry point
ANALYSIS.md               # full writeup
AGENTS.md                 # engineering context for contributors
```

## License

[MIT](LICENSE.md) © 2026 Adam Braman. The opening data comes from
third-party sources ([lichess-org/chess-openings](https://github.com/lichess-org/chess-openings)
and [KingBase 2018](https://archive.org/details/KingBase2018)) and remains
under those sources' own terms.
