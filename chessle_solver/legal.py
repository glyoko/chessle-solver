"""Legality checking for a candidate move sequence, via python-chess."""
from __future__ import annotations

import chess


def is_legal_sequence(moves: tuple[str, ...]) -> bool:
    board = chess.Board()
    for san in moves:
        try:
            board.push_san(san)
        except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            return False
    return True
