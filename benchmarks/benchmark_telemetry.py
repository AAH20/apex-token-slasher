"""Precision Microsecond Benchmark Telemetry for Apex Token Slasher.

Zero external dependencies.
"""

from __future__ import annotations

import time
from typing import Callable, List, Tuple

from apex_token_slasher.core.ast_slicer import AstCallGraphSlicer
from apex_token_slasher.core.entropy_filter import EntropyFilter
from apex_token_slasher.core.merkle_cache import MerkleAstCache
from apex_token_slasher.core.models import BudgetSpec, ChunkKind, TokenChunk
from apex_token_slasher.core.submodular_knapsack import SubmodularContextKnapsack
from apex_token_slasher.integrations.cognee_bridge import CogneeGraphBridge
from apex_token_slasher.integrations.hindsight_distiller import HindsightMemoryDistiller
from apex_token_slasher.integrations.laya_clef_gate import LayaClefFastGate
from apex_token_slasher.integrations.swarm_bridge import SwarmAgentRole, SwarmTokenBudgetBridge
from apex_token_slasher.pipeline import SlasherPipeline


def run_benchmark() -> None:
    sample_code = """
import os
import sys
import math
from typing import List, Dict, Optional

class DataPipeline:
    def __init__(self, name: str):
        self.name = name

    def execute_transform(self, data: List[int]) -> int:
        return sum(x * 2 for x in data)

    def dead_helper_method(self) -> None:
        pass

def public_entrypoint(x: int) -> int:
    pipeline = DataPipeline("prod")
    return pipeline.execute_transform([x, x + 1, x + 2])

def unused_background_task() -> str:
    # --------------------------------------------------
    # Unused background logging routine
    # --------------------------------------------------
    return "unused"
""" * 5  # ~500 lines of typical Python module

    pipeline = SlasherPipeline(enable_nerve=False)
    fast_gate = LayaClefFastGate()
    ast_slicer = AstCallGraphSlicer()
    entropy_filter = EntropyFilter()
    merkle_cache = MerkleAstCache()
    knapsack = SubmodularContextKnapsack()
    cognee = CogneeGraphBridge()
    cognee.register_entities([
        {"id": "DataPipeline", "name": "DataPipeline", "type": "class", "relationships": ["execute_transform"]},
        {"id": "public_entrypoint", "name": "public_entrypoint", "type": "function", "relationships": []},
    ])
    hindsight = HindsightMemoryDistiller()
    swarm = SwarmTokenBudgetBridge()

    precomputed_chunks, _ = ast_slicer.slice_to_chunks(sample_code, "pipeline.py", {"public_entrypoint"})
    budget = BudgetSpec(max_tokens=600, pinned_symbols={"public_entrypoint"})

    benchmarks: List[Tuple[str, Callable[[], None], int]] = [
        ("1. Laya / Clef Fast-Path Gate", lambda: fast_gate.evaluate(sample_code), 500),
        ("2. AST Slicer (Parse & Reach)", lambda: ast_slicer.slice_to_chunks(sample_code, "pipeline.py", {"public_entrypoint"}), 100),
        ("3. Shannon Entropy & PID Filter", lambda: entropy_filter.calculate_pid(sample_code), 300),
        ("4. Merkle SHA-256 Tree Root", lambda: merkle_cache.compute_merkle_root([c.chunk_id for c in precomputed_chunks]), 500),
        ("5. Submodular Knapsack Optimizer", lambda: knapsack.solve(precomputed_chunks, 600), 500),
        ("6. Cognee Subgraph Projector", lambda: cognee.extract_ast_entry_points("DataPipeline execute_transform"), 500),
        ("7. Hindsight Memory Distiller", lambda: hindsight.distill_to_chunk(["In session 1 the user requested Python only", "Port 8080 active"]), 500),
        ("8. Swarm Kemeny-Young Consensus", lambda: swarm.kemeny_young_context_consensus(["a.py", "b.py", "c.py", "d.py"], [["a.py", "b.py", "c.py", "d.py"], ["b.py", "a.py", "c.py", "d.py"]]), 500),
        ("9. Full End-to-End Pipeline", lambda: pipeline.slash_context(sample_code, budget, file_path="pipeline.py", entry_points={"public_entrypoint"}), 100),
    ]

    print("=" * 76)
    print("  Apex Token Slasher — Subsystem Benchmark Telemetry")
    print("=" * 76)
    print(f"  {'Subsystem / Operation':<36} {'p50 (µs)':>10} {'p99 (µs)':>10} {'Ops/sec':>14}")
    print("  " + "-" * 72)

    for name, fn, iters in benchmarks:
        timings: List[float] = []
        for _ in range(iters):
            t0 = time.perf_counter_ns()
            fn()
            t1 = time.perf_counter_ns()
            timings.append((t1 - t0) / 1000.0)

        timings.sort()
        p50 = timings[len(timings) // 2]
        p99 = timings[int(len(timings) * 0.99)]
        ops_sec = int(1_000_000.0 / p50) if p50 > 0 else 0
        print(f"  {name:<36} {p50:>10.2f} {p99:>10.2f} {ops_sec:>14,}")

    print("=" * 76)


if __name__ == "__main__":
    run_benchmark()
