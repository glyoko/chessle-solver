from .corpus import (
    DEFAULT_CORPUS_PATH,
    DEFAULT_EXTENSIONS_PATH,
    OpeningEntry,
    build_prefix_pool,
    load_all_entries,
    load_entries,
)
from .entropy import entropy, max_possible_entropy, pattern_distribution
from .legal import is_legal_sequence
from .match import compare_sequences
from .probe import ProbeResult, ProbeSearchReport, find_best_legal_probe
from .simulate import SimulationResult, simulate, weighted_average
from .solver import Solver, best_guess, filter_answers
from .tree_probe import TreeProbeReport, TreeProbeResult, find_best_legal_probe_tree

__all__ = [
    "DEFAULT_CORPUS_PATH",
    "DEFAULT_EXTENSIONS_PATH",
    "OpeningEntry",
    "build_prefix_pool",
    "load_all_entries",
    "load_entries",
    "entropy",
    "max_possible_entropy",
    "pattern_distribution",
    "compare_sequences",
    "is_legal_sequence",
    "ProbeResult",
    "ProbeSearchReport",
    "find_best_legal_probe",
    "SimulationResult",
    "simulate",
    "weighted_average",
    "Solver",
    "best_guess",
    "filter_answers",
    "TreeProbeReport",
    "TreeProbeResult",
    "find_best_legal_probe_tree",
]
