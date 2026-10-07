"""Master Token Slasher Execution Pipeline.

Orchestrates Laya/Clef gating, AST slicing, entropy filtering, Merkle deduplication,
and submodular knapsack selection into a unified sub-2ms engine.
Zero external dependencies.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set

from apex_token_slasher.core.ast_slicer import AstCallGraphSlicer
from apex_token_slasher.core.entropy_filter import EntropyFilter
from apex_token_slasher.core.merkle_cache import MerkleAstCache
from apex_token_slasher.core.models import (
    BudgetSpec,
    ChunkKind,
    GatingAction,
    PruningStats,
    PruningStrategy,
    SlashedContext,
    TokenChunk,
)
from apex_token_slasher.core.submodular_knapsack import SubmodularContextKnapsack
from apex_token_slasher.integrations.cognee_bridge import CogneeGraphBridge
from apex_token_slasher.integrations.hindsight_distiller import HindsightMemoryDistiller
from apex_token_slasher.integrations.laya_clef_gate import LayaClefFastGate
from apex_token_slasher.integrations.nerve_supervisor import NerveSupervisorBridge


class SlasherPipeline:
    """End-to-end token reduction pipeline executing AST, entropy, and knapsack optimizations."""

    def __init__(
        self,
        strip_docstrings: bool = False,
        preserve_class_skeletons: bool = True,
        enable_nerve: bool = True,
    ) -> None:
        self.fast_gate = LayaClefFastGate()
        self.ast_slicer = AstCallGraphSlicer(
            strip_docstrings=strip_docstrings,
            preserve_class_skeletons=preserve_class_skeletons,
        )
        self.entropy_filter = EntropyFilter()
        self.knapsack = SubmodularContextKnapsack()
        self.merkle_cache = MerkleAstCache()
        self.nerve_supervisor = NerveSupervisorBridge() if enable_nerve else None
        self.cognee_bridge = CogneeGraphBridge()
        self.hindsight_distiller = HindsightMemoryDistiller()

    def advance_turn(self) -> None:
        """Advances session turn counter in the Merkle cache."""
        self.merkle_cache.advance_turn()

    def slash_context(
        self,
        raw_text: str,
        budget: Optional[BudgetSpec] = None,
        file_path: Optional[str] = None,
        entry_points: Optional[Set[str]] = None,
        query_terms: Optional[Set[str]] = None,
        extra_memories: Optional[List[str]] = None,
        task_id: str = "default_task",
    ) -> SlashedContext:
        """Executes the full token reduction pipeline on raw text/code."""
        t_start = time.perf_counter_ns()
        active_budget = budget or BudgetSpec()
        entries = set(entry_points or active_budget.pinned_symbols)
        queries = set(query_terms or set())

        # Step 1: Laya / Clef Fast-Path Gating (<50µs)
        verdict = self.fast_gate.evaluate(
            text=raw_text,
            turn_number=self.merkle_cache.current_turn,
            target_max_tokens=active_budget.max_tokens,
        )

        initial_tokens = max(1, int(len(raw_text) / 3.8))
        stats = PruningStats(initial_tokens=initial_tokens)

        # Fast bypass if verdict is BYPASS
        if verdict.action == GatingAction.BYPASS:
            t_end = time.perf_counter_ns()
            stats.final_tokens = initial_tokens
            stats.retained_chunks_count = 1
            stats.elapsed_microseconds = (t_end - t_start) / 1000.0
            stats.compute_ratios()

            chunk = TokenChunk(
                chunk_id="raw:bypass",
                content=raw_text,
                kind=ChunkKind.SOURCE_CODE,
                file_path=file_path,
                estimated_tokens=initial_tokens,
                is_pinned=True,
            )
            return SlashedContext(
                rendered_text=raw_text,
                retained_chunks=[chunk],
                dropped_chunks=[],
                stats=stats,
                gating_verdict=verdict,
                merkle_root=self.merkle_cache.compute_chunk_hash(chunk),
            )

        # Step 2: AST Slicing (if Python source code)
        candidates: List[TokenChunk] = []
        dropped_by_ast: List[TokenChunk] = []

        is_python = file_path.endswith(".py") if file_path else ("def " in raw_text or "class " in raw_text)

        if is_python and active_budget.enable_ast_slice:
            retained_ast, dropped_ast = self.ast_slicer.slice_to_chunks(
                code=raw_text,
                file_path=file_path or "inline_snippet.py",
                entry_points=entries,
            )
            candidates.extend(retained_ast)
            dropped_by_ast.extend(dropped_ast)
            stats.tokens_dropped_by_ast = sum(c.estimated_tokens for c in dropped_ast)
        else:
            # Non-python or disabled: wrap as single chunk
            chunk = TokenChunk(
                chunk_id=f"{file_path or 'text'}:main",
                content=raw_text,
                kind=ChunkKind.SOURCE_CODE,
                file_path=file_path,
                estimated_tokens=initial_tokens,
            )
            candidates.append(chunk)

        # Inject Hindsight memory chunk if provided
        if extra_memories:
            mem_chunk = self.hindsight_distiller.distill_to_chunk(extra_memories)
            candidates.append(mem_chunk)

        # Step 3: Merkle Differential Deduplication
        dropped_by_merkle: List[TokenChunk] = []
        if active_budget.enable_merkle_dedup:
            retained_merkle, dup_merkle, saved_merkle = self.merkle_cache.deduplicate_chunks(
                chunks=candidates,
                replace_with_tombstone=True,
            )
            candidates = retained_merkle
            dropped_by_merkle = dup_merkle
            stats.tokens_dropped_by_merkle = saved_merkle

        # Step 4: Shannon Entropy & PID Filtering
        filtered_candidates: List[TokenChunk] = []
        dropped_by_entropy: List[TokenChunk] = []

        if active_budget.enable_entropy_filter:
            for c in candidates:
                passes, updated_chunk = self.entropy_filter.filter_chunk(
                    chunk=c,
                    min_entropy=active_budget.min_entropy,
                    min_pid=active_budget.min_pid,
                )
                if passes:
                    filtered_candidates.append(updated_chunk)
                else:
                    dropped_by_entropy.append(updated_chunk)
            stats.tokens_dropped_by_entropy = sum(c.estimated_tokens for c in dropped_by_entropy)
            candidates = filtered_candidates

        # Step 5: Submodular Context Knapsack Selection
        effective_limit = max(100, active_budget.max_tokens - active_budget.reserve_tokens)
        retained_final, dropped_by_knapsack = self.knapsack.solve(
            chunks=candidates,
            max_tokens=effective_limit,
            query_terms=queries | entries,
        )
        stats.tokens_dropped_by_knapsack = sum(c.estimated_tokens for c in dropped_by_knapsack)

        # Step 6: Render output & finalize stats
        rendered_parts: List[str] = [c.content for c in retained_final]
        rendered_text = "\n\n".join(rendered_parts)

        final_tokens = sum(c.estimated_tokens for c in retained_final)
        stats.final_tokens = final_tokens
        stats.retained_chunks_count = len(retained_final)
        all_dropped = dropped_by_ast + dropped_by_merkle + dropped_by_entropy + dropped_by_knapsack
        stats.dropped_chunks_count = len(all_dropped)

        t_end = time.perf_counter_ns()
        stats.elapsed_microseconds = (t_end - t_start) / 1000.0
        stats.compute_ratios()

        # Compute Merkle root of retained context
        chunk_hashes = [c.merkle_hash or self.merkle_cache.compute_chunk_hash(c) for c in retained_final]
        merkle_root = self.merkle_cache.compute_merkle_root(chunk_hashes)

        # Step 7: Record receipt in Nerve supervisor
        if self.nerve_supervisor:
            self.nerve_supervisor.record_slashed_event(
                task_id=task_id,
                turn_number=self.merkle_cache.current_turn,
                stats=stats,
                merkle_root=merkle_root,
            )

        return SlashedContext(
            rendered_text=rendered_text,
            retained_chunks=retained_final,
            dropped_chunks=all_dropped,
            stats=stats,
            gating_verdict=verdict,
            merkle_root=merkle_root,
            metadata={"strategy": active_budget.strategy.value},
        )
