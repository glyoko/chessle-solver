"""
The actual Chessle-playing bot, structured the same way as the video's
Wordle bot:

  - filter_answers: apply one guess/pattern observation to shrink the pool.
  - best_guess:     pick the guess that maximizes expected information
                     (entropy) against the current, re-weighted pool.
  - Solver.play:     repeat until solved or out of guesses.

Performance note: Chessle's *true* guess space is "any legal chess move at
each ply," which is unbounded and not worth brute-forcing. Guesses are
restricted to the prefixes present in the opening corpus (see corpus.py) --
the same simplification Wordle-solving code makes by only ever considering
words from its own dictionary rather than every possible letter string.
For turn 1 we search that entire guess pool (it's guess-independent of the
secret, so it's computed once and reused for every simulated game). For
later turns we search only the *remaining candidate answers* rather than
the full guess pool, purely to keep runtime tractable -- entropy is still
computed correctly over the full remaining-answer distribution, we're just
narrowing which candidate guesses get considered.
"""
from __future__ import annotations

from .entropy import entropy, pattern_distribution
from .match import compare_sequences


def filter_answers(
    guess: tuple[str, ...],
    pattern: tuple[str, ...],
    answers: dict[tuple[str, ...], float],
) -> dict[tuple[str, ...], float]:
    return {
        answer: weight
        for answer, weight in answers.items()
        if compare_sequences(guess, answer) == pattern
    }


def best_guess(
    candidate_guesses,
    answers: dict[tuple[str, ...], float],
) -> tuple[tuple[str, ...], float]:
    """Return (guess, its entropy) maximizing expected information."""
    best = None
    best_h = -1.0
    for guess in candidate_guesses:
        h = entropy(guess, answers)
        if h > best_h:
            best_h = h
            best = guess
    return best, best_h


class Solver:
    def __init__(
        self,
        guess_pool: list[tuple[str, ...]],
        answer_pool: dict[tuple[str, ...], float],
        max_guesses: int = 6,
        full_search_turns: int = 1,
    ):
        self.guess_pool = guess_pool
        self.answer_pool = answer_pool
        self.max_guesses = max_guesses
        self.full_search_turns = full_search_turns
        self._opener_cache: tuple[tuple[str, ...], float] | None = None

    def opening_guess(self) -> tuple[tuple[str, ...], float]:
        if self._opener_cache is None:
            self._opener_cache = best_guess(self.guess_pool, self.answer_pool)
        return self._opener_cache

    def choose_guess(
        self, turn: int, remaining: dict[tuple[str, ...], float]
    ) -> tuple[tuple[str, ...], float]:
        if len(remaining) == 1:
            (only,) = remaining.keys()
            return only, 0.0
        if turn == 1:
            return self.opening_guess()
        candidates = self.guess_pool if turn <= self.full_search_turns else remaining.keys()
        return best_guess(candidates, remaining)

    def play(self, secret: tuple[str, ...]) -> list[tuple[str, ...]]:
        """Play one game against `secret`. Returns the list of guesses made."""
        remaining = dict(self.answer_pool)
        guesses_made: list[tuple[str, ...]] = []
        for turn in range(1, self.max_guesses + 1):
            guess, _ = self.choose_guess(turn, remaining)
            guesses_made.append(guess)
            if guess == secret:
                return guesses_made
            pattern = compare_sequences(guess, secret)
            remaining = filter_answers(guess, pattern, remaining)
        return guesses_made
