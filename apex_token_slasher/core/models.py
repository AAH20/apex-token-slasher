"""Core domain models for Apex Token Slasher.

Defines schemas for chunks, budgets, pruning statistics, and gating verdicts.
Zero external dependencies: 100% pure Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class PruningStrategy(str, Enum):
    """Pruning aggression strategies."""
    CONSERVATIVE = "conservative"  # Drops only comments, unused imports & exact dupes (~30-40% savings)
    BALANCED = "balanced"          # AST reachability + entropy filtering + dead-code elimination (~60-75% savings)
    AGGRESSIVE = "aggressive"      # Strict submodular knapsack to exact token ceiling (~80-90% savings)


class ChunkKind(str, Enum):
    """Categories of context chunks."""
    SOURCE_CODE = "source_code"
    DOCSTRING = "docstring"
    COMMENT = "comment"
    TEST_LOG = "test_log"
    STACK_TRACE = "stack_trace"
    DIFF = "diff"
    CONVERSATION = "conversation"
    MEMORY = "memory"
    SYSTEM_INSTRUCTION = "system_instruction"


@dataclass(frozen=True)
class TokenChunk:
    """An atomic unit of context available for pruning or retention."""
    chunk_id: str
    content: str
    kind: ChunkKind
    file_path: Optional[str] = None
    symbol_name: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    estimated_tokens: int = 0
    entropy: float = 0.0
    pid: float = 0.0  # Propositional Information Density
    merkle_hash: str = ""
    dependencies: Set[str] = field(default_factory=set)
    is_pinned: bool = False  # Always retained if True

    def __post_init__(self) -> None:
        if self.estimated_tokens <= 0 and self.content:
            # Conservative token heuristic: ~3.8 chars per token for code/English
            estimated = max(1, int(len(self.content) / 3.8))
            object.__setattr__(self, "estimated_tokens", estimated)


@dataclass
class BudgetSpec:
    """Token budget constraints and pruning targets."""
    max_tokens: int = 8000
    reserve_tokens: int = 500
    strategy: PruningStrategy = PruningStrategy.BALANCED
    pinned_symbols: Set[str] = field(default_factory=set)
    min_entropy: float = 2.0  # Bits per token threshold
    min_pid: float = 0.15     # Propositional density threshold
    enable_merkle_dedup: bool = True
    enable_ast_slice: bool = True
    enable_entropy_filter: bool = True


@dataclass
class PruningStats:
    """Fine-grained breakdown of token reduction."""
    initial_tokens: int = 0
    final_tokens: int = 0
    tokens_saved: int = 0
    savings_ratio: float = 0.0
    tokens_dropped_by_ast: int = 0
    tokens_dropped_by_entropy: int = 0
    tokens_dropped_by_merkle: int = 0
    tokens_dropped_by_knapsack: int = 0
    retained_chunks_count: int = 0
    dropped_chunks_count: int = 0
    elapsed_microseconds: float = 0.0

    def compute_ratios(self) -> None:
        if self.initial_tokens > 0:
            self.tokens_saved = max(0, self.initial_tokens - self.final_tokens)
            self.savings_ratio = self.tokens_saved / self.initial_tokens


class GatingAction(str, Enum):
    """Routing action decided by Laya / Clef fast gate."""
    BYPASS = "bypass"                # Under budget, no pruning needed
    MERKLE_ONLY = "merkle_only"      # Minor repeats, deduplicate hashes only
    AST_PRUNE = "ast_prune"          # Code heavy, run call-graph slicing
    FULL_SLASH = "full_slash"        # Massive context, execute all 4 optimization tiers


@dataclass
class GatingVerdict:
    """Verdict output from Clef/Laya fast-path gate."""
    action: GatingAction
    confidence: float
    gate_latency_us: float
    reasons: List[str] = field(default_factory=list)
    router_backend: str = "clef_hotpath"  # "clef_hotpath", "laya_sidecar", "heuristic"


@dataclass
class SlashedContext:
    """Complete output of the token slashing pipeline."""
    rendered_text: str
    retained_chunks: List[TokenChunk]
    dropped_chunks: List[TokenChunk]
    stats: PruningStats
    gating_verdict: GatingVerdict
    merkle_root: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
