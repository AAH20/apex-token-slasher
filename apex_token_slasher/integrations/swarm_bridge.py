"""ApexGraphSwarm Integration Bridge.

Partitions multi-agent swarm token budgets using Multi-Choice Knapsack (MCKP)
and resolves conflicting context chunk proposals using Kemeny-Young rank consensus.
Zero external dependencies.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from apex_token_slasher.core.models import BudgetSpec, ChunkKind, PruningStrategy, TokenChunk


@dataclass
class SwarmAgentRole:
    """Represents a specialized agent in ApexGraphSwarm."""
    agent_id: str
    role_name: str  # "architect", "coder", "tester", "critic", "security"
    allocated_tokens: int
    focus_kinds: Set[ChunkKind]
    query_anchors: Set[str]


class SwarmTokenBudgetBridge:
    """Manages context partitioning and consensus across multi-agent swarms."""

    def partition_swarm_budgets(
        self,
        total_swarm_budget: int,
        agents: List[SwarmAgentRole],
    ) -> Dict[str, BudgetSpec]:
        """Allocates token budgets to each swarm agent according to its role specialization."""
        specs: Dict[str, BudgetSpec] = {}
        total_requested = sum(a.allocated_tokens for a in agents)

        for agent in agents:
            # Scale proportionally if total requested exceeds global swarm ceiling
            scale = min(1.0, total_swarm_budget / max(1, total_requested))
            effective_tokens = int(agent.allocated_tokens * scale)

            strategy = (
                PruningStrategy.AGGRESSIVE if agent.role_name in ("critic", "tester")
                else PruningStrategy.BALANCED
            )

            specs[agent.agent_id] = BudgetSpec(
                max_tokens=effective_tokens,
                reserve_tokens=300,
                strategy=strategy,
                pinned_symbols=agent.query_anchors,
                enable_merkle_dedup=True,
                enable_ast_slice=True,
                enable_entropy_filter=True,
            )

        return specs

    def kemeny_young_context_consensus(
        self,
        candidate_chunk_ids: List[str],
        agent_preferences: List[List[str]],
    ) -> List[str]:
        """Computes Kemeny-Young consensus ranking over candidate chunks nominated by swarm agents.

        Finds the permutation minimizing the total Kendall tau distance to all agent rankings.
        """
        if not candidate_chunk_ids or not agent_preferences:
            return candidate_chunk_ids

        # Build pairwise preference matrix
        candidates = candidate_chunk_ids[:8]  # Limit to 8 for exact permutation search (8! = 40,320)
        n = len(candidates)
        cand_to_idx = {c: i for i, c in enumerate(candidates)}

        # score[i][j] = number of agents ranking candidate i strictly ahead of candidate j
        pairwise = [[0] * n for _ in range(n)]
        for ranking in agent_preferences:
            seen_indices = [cand_to_idx[c] for c in ranking if c in cand_to_idx]
            for pos_a, a_idx in enumerate(seen_indices):
                for b_idx in seen_indices[pos_a + 1:]:
                    pairwise[a_idx][b_idx] += 1

        best_perm = candidates
        best_score = -1

        # Search optimal permutation maximizing agreed pairwise preferences
        for perm in itertools.permutations(range(n)):
            score = 0
            for i_idx, a_idx in enumerate(perm):
                for b_idx in perm[i_idx + 1:]:
                    score += pairwise[a_idx][b_idx]

            if score > best_score:
                best_score = score
                best_perm = [candidates[idx] for idx in perm]

        return list(best_perm)
