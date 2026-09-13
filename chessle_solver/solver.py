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
entropy than the best real opening in the corpus.

Turn 1 is guess-independent of any particular secret and of the prior
(v1/v2 both converged on the same winning sequence per depth), so a wide,
slow beam search (beam=300, several minutes) only ever needs to be run
once, offline, per depth -- not on every Solver construction. Its results
are hardcoded below (HARDCODED_OPENERS). `opening_guess()` still compares
it against the current corpus-only opener's *true* entropy (cheap) and
only uses it when it actually wins, so this never silently regresses if
the answer pool changes (e.g. a new depth, or corpus enrichment shifts
which guess is best). If a depth has no hardcoded entry, or a caller wants
a fresh search instead, `tree_probe_beam_width` runs the same wide search
live instead, exactly as before.

For turns after the first, the same idea applies at a much smaller scale:
`subsequent_beam_width` (default 10, intentionally small since this now
runs on every turn of every simulated game) runs the tree-search probe
against the *remaining* candidates and keeps it only if it beats the
corpus-restricted guess for that turn.
"""
from __future__ import annotations

from .entropy import entropy, pattern_distribution
from .match import compare_sequences
from .tree_probe import find_best_legal_probe_tree

# Best off-book turn-1 guesses found via a wide (beam=300) tree-search probe
# against the KingBase-enriched corpus (see ANALYSIS.md section 8b). Both
# the uniform and popularity-weighted priors converged on the same winning
# sequence at each depth -- only the resulting entropy differs by prior,
# which opening_guess() computes fresh against whatever answer_pool it's
# given, so these tuples alone are enough to reuse the result cheaply.
HARDCODED_OPENERS: dict[int, tuple[str, ...]] = {
    6: ("d4", "e5", "Nf3", "Nf6", "Nc3", "d5"),
    10: ("e4", "d5", "Nf3", "e6", "Nc3", "Nf6", "d4", "c5", "Bc4", "Nc6"),
}


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
        subsequent_beam_width: int | None = 10,
        hardcoded_opener: tuple[str, ...] | None | bool = True,
    ):
        self.guess_pool = guess_pool
        self.answer_pool = answer_pool
        self.max_guesses = max_guesses
        self.full_search_turns = full_search_turns
        self.tree_probe_beam_width = tree_probe_beam_width
        self.subsequent_beam_width = subsequent_beam_width
        if hardcoded_opener is True:
            depth = len(next(iter(answer_pool)))
            hardcoded_opener = HARDCODED_OPENERS.get(depth)
        elif hardcoded_opener is False:
            hardcoded_opener = None
        self.hardcoded_opener = hardcoded_opener
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

            if self.hardcoded_opener is not None:
                h = entropy(self.hardcoded_opener, self.answer_pool)
                if h > corpus_h:
                    self._opener_cache = (self.hardcoded_opener, h)
                    self._opener_is_probe = True
            elif self.tree_probe_beam_width:
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
        corpus_guess, corpus_h = best_guess(candidates, remaining)

        if self.subsequent_beam_width:
            depth = len(next(iter(remaining)))
            report = find_best_legal_probe_tree(
                remaining, depth, beam_width=self.subsequent_beam_width
            )
            if report.best and report.best.true_entropy > corpus_h:
                return report.best.moves, report.best.true_entropy

        return corpus_guess, corpus_h

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
