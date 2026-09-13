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

Opener off-book search: the corpus-only restriction above throws away
exactly the kind of high-information "probe" guess that doesn't need to be
a plausible answer itself (see ANALYSIS.md section 8) -- confirmed to
matter in practice at Expert depth, where a legal-but-unnamed sequence
found by the tree-search beam search (tree_probe.py) has HIGHER true
entropy than the best real opening in the corpus. When `tree_probe_beam_width`
is set, `opening_guess()` runs that search too and uses whichever of the
two (corpus-best or tree-probe-best) has higher true entropy -- so the
solver stays corpus-only when that happens to win (as it does at Normal
depth) and switches to the off-book guess only when it's actually better
(Expert depth). This only affects the turn-1 opener; later turns still
search the corpus-restricted guess pool / remaining answers as before.
"""
from __future__ import annotations

from .entropy import entropy, pattern_distribution
from .match import compare_sequences
from .tree_probe import find_best_legal_probe_tree


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
        tree_probe_beam_width: int | None = None,
    ):
        self.guess_pool = guess_pool
        self.answer_pool = answer_pool
        self.max_guesses = max_guesses
        self.full_search_turns = full_search_turns
        self.tree_probe_beam_width = tree_probe_beam_width
        self._opener_cache: tuple[tuple[str, ...], float] | None = None
        self._opener_is_probe: bool | None = None
        self._corpus_opener_cache: tuple[tuple[str, ...], float] | None = None
        self._tree_report = None

    def opening_guess(self) -> tuple[tuple[str, ...], float]:
        if self._opener_cache is None:
            corpus_guess, corpus_h = best_guess(self.guess_pool, self.answer_pool)
            self._corpus_opener_cache = (corpus_guess, corpus_h)
            self._opener_cache = (corpus_guess, corpus_h)
            self._opener_is_probe = False
            if self.tree_probe_beam_width:
                depth = len(next(iter(self.answer_pool)))
                self._tree_report = find_best_legal_probe_tree(
                    self.answer_pool, depth, beam_width=self.tree_probe_beam_width
                )
                if self._tree_report.best and self._tree_report.best.true_entropy > corpus_h:
                    self._opener_cache = (
                        self._tree_report.best.moves,
                        self._tree_report.best.true_entropy,
                    )
                    self._opener_is_probe = True
        return self._opener_cache

    def corpus_only_opener(self) -> tuple[tuple[str, ...], float]:
        """The best opener restricted to real named openings, ignoring any
        off-book tree-probe search -- for comparison against opening_guess()."""
        self.opening_guess()
        return self._corpus_opener_cache

    def opener_is_off_book_probe(self) -> bool:
        """True if opening_guess() picked the tree-probe result over the
        corpus-restricted one. Only meaningful after opening_guess() has
        been called at least once."""
        self.opening_guess()
        return bool(self._opener_is_probe)

    def tree_probe_report(self):
        """The TreeProbeReport computed during opening_guess() (None if
        tree_probe_beam_width wasn't set, or opening_guess() hasn't run yet)."""
        return self._tree_report

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
        """
        Play one game against `secret`. Returns the list of guesses made.

        If `secret` isn't actually in this solver's answer pool (it can
        legitimately be tested against any secret, not just ones drawn from
        its own pool -- e.g. a real live puzzle our corpus doesn't cover),
        the remaining-candidates set can be filtered down to nothing without
        ever having guessed correctly. When that happens there's no viable
        next guess, so we stop rather than crash; the caller can tell this
        happened because the last guess (if any) won't equal `secret`.
        """
        remaining = dict(self.answer_pool)
        guesses_made: list[tuple[str, ...]] = []
        for turn in range(1, self.max_guesses + 1):
            guess, _ = self.choose_guess(turn, remaining)
            if guess is None:
                break
            guesses_made.append(guess)
            if guess == secret:
                return guesses_made
            pattern = compare_sequences(guess, secret)
            remaining = filter_answers(guess, pattern, remaining)
        return guesses_made
