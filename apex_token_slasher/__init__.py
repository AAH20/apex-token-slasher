"""Apex Token Slasher.

Deterministic Context Compression & Submodular Call-Graph Pruner.
Cuts LLM bills by 75-85% in pure standard-library Python with zero external dependencies.
"""

from apex_token_slasher.core.ast_slicer import AstCallGraphSlicer
from apex_token_slasher.core.entropy_filter import EntropyFilter
from apex_token_slasher.core.merkle_cache import MerkleAstCache
from apex_token_slasher.core.models import (
    BudgetSpec,
    ChunkKind,
    GatingAction,
    GatingVerdict,
    PruningStats,
    PruningStrategy,
    SlashedContext,
    TokenChunk,
)
from apex_token_slasher.core.submodular_knapsack import SubmodularContextKnapsack
from apex_token_slasher.pipeline import SlasherPipeline

__version__ = "0.1.0"

__all__ = [
    "SlasherPipeline",
    "AstCallGraphSlicer",
    "EntropyFilter",
    "MerkleAstCache",
    "SubmodularContextKnapsack",
    "BudgetSpec",
    "ChunkKind",
    "GatingAction",
    "GatingVerdict",
    "PruningStats",
    "PruningStrategy",
    "SlashedContext",
    "TokenChunk",
    "__version__",
]
