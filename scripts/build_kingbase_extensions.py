"""
Extend opening families whose named theory dead-ends before 10 plies (see
chessle_solver/dead_ends.py) using real continuation moves mined from the
KingBase 2018 database (~2M real games, 2000+ ELO players, 1990-2018),
downloaded from https://archive.org/details/KingBase2018.

For each dead-end prefix, find every KingBase game whose opening matches it
and reaches at least 10 plies, and take the SINGLE MOST COMMON full 10-ply
continuation actually played by real players -- rather than an engine's
independently-computed "best" move, which (confirmed against a real live
Chessle puzzle) doesn't reliably match what these openings actually
continue into.

Output: kingbase_extensions.tsv, same eco/name/pgn/weight shape as
openings_corpus.tsv, loaded the same way via chessle_solver.corpus.

Usage: python3 scripts/build_kingbase_extensions.py --zip scratch_data/KingBase2018-pgn.zip --depth 10
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chessle_solver.corpus import DEFAULT_CORPUS_PATH, load_entries
from chessle_solver.dead_ends import compute_dead_ends

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "kingbase_extensions.tsv"

MOVE_NUM_RE = re.compile(r"^\d+\.+")
RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}
COMMENT_RE = re.compile(r"\{[^}]*\}")


def iter_game_movetexts(text: str):
    """PGN games are header-block, blank line, movetext-block, blank line,
    repeating -- splitting on blank lines alternates header/movetext chunks,
    movetext chunks starting second (index 1, 3, 5, ...)."""
    chunks = text.split("\n\n")
    for i in range(1, len(chunks), 2):
        yield chunks[i]


def extract_moves(movetext: str, max_plies: int) -> tuple[str, ...]:
    movetext = COMMENT_RE.sub(" ", movetext)
    moves = []
    for tok in movetext.split():
        tok = MOVE_NUM_RE.sub("", tok)
        if not tok or tok in RESULT_TOKENS or tok.startswith("$"):
            continue
        moves.append(tok)
        if len(moves) >= max_plies:
            break
    return tuple(moves)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--depth", type=int, default=10)
    args = parser.parse_args()

    entries = load_entries(DEFAULT_CORPUS_PATH)
    dead = compute_dead_ends(entries, args.depth)
    print(f"{len(dead)} dead-end prefixes to search for in KingBase games.")

    by_length: dict[int, set] = defaultdict(set)
    for prefix in dead:
        by_length[len(prefix)].add(prefix)
    lengths = sorted(by_length)

    rep = {}
    for e in entries:
        if e.moves in dead and e.moves not in rep:
            rep[e.moves] = (e.eco, e.name)

    continuation_counts: dict[tuple[str, ...], Counter] = defaultdict(Counter)
    games_scanned = 0
    games_matched = 0

    t0 = time.time()
    with zipfile.ZipFile(args.zip) as zf:
        pgn_names = [n for n in zf.namelist() if n.endswith(".pgn")]
        for name in pgn_names:
            print(f"Scanning {name}...")
            with zf.open(name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace").read()
            for movetext in iter_game_movetexts(text):
                moves = extract_moves(movetext, args.depth)
                games_scanned += 1
                if len(moves) < args.depth:
                    continue
                for L in lengths:
                    prefix = moves[:L]
                    if prefix in by_length[L]:
                        continuation_counts[prefix][moves] += 1
                        games_matched += 1
            print(
                f"  ...{games_scanned} games scanned so far, "
                f"{games_matched} matched a dead-end prefix, "
                f"{len(continuation_counts)}/{len(dead)} dead-ends found, "
                f"[{time.time() - t0:.0f}s elapsed]"
            )

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["eco", "name", "pgn", "weight"])
        for prefix, weight in dead.items():
            counts = continuation_counts.get(prefix)
            if not counts:
                continue
            full_moves, n = counts.most_common(1)[0]
            eco, name = rep.get(prefix, ("", "real-game continuation"))
            pgn_parts = []
            for i, mv in enumerate(full_moves):
                if i % 2 == 0:
                    pgn_parts.append(f"{i // 2 + 1}.")
                pgn_parts.append(mv)
            writer.writerow([eco, f"{name} (KingBase continuation, n={n})", " ".join(pgn_parts), weight])

    print(f"\nDone in {time.time() - t0:.0f}s. Extended {len(continuation_counts)}/{len(dead)} dead ends.")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
