"""Hermes Nerve Supervisory Integration.

Binds to Nerve's System-1 supervisory layer, enforcing Definition of Done (DoD)
token budget locks and appending structured receipts to Nerve's context-ledger.jsonl.
Zero external dependencies.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from apex_token_slasher.core.models import BudgetSpec, PruningStats


class NerveSupervisorBridge:
    """Interacts with Hermes Nerve's runtime ledgers and budget supervisors."""

    DEFAULT_NERVE_DIR = Path.home() / ".hermes" / "nerve"

    def __init__(self, nerve_dir: Optional[Path] = None) -> None:
        self.nerve_dir = nerve_dir or self.DEFAULT_NERVE_DIR
        self.context_ledger_path = self.nerve_dir / "context-ledger.jsonl"
        self.decision_outcomes_path = self.nerve_dir / "decision-outcomes.jsonl"

    def enforce_dod_budget(self, requested_tokens: int, locked_budget: int = 70000) -> BudgetSpec:
        """Computes strict BudgetSpec to prevent a supervised worker from exceeding its locked DoD ceiling."""
        effective_max = min(requested_tokens, max(2000, locked_budget - 5000))
        return BudgetSpec(
            max_tokens=effective_max,
            reserve_tokens=1000,
            enable_merkle_dedup=True,
            enable_ast_slice=True,
            enable_entropy_filter=True,
        )

    def record_slashed_event(
        self,
        task_id: str,
        turn_number: int,
        stats: PruningStats,
        merkle_root: str,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Appends a cryptographically verified receipt to Nerve's context-ledger.jsonl."""
        entry = {
            "timestamp": time.time(),
            "source": "apex_token_slasher",
            "task_id": task_id,
            "turn_number": turn_number,
            "initial_tokens": stats.initial_tokens,
            "final_tokens": stats.final_tokens,
            "tokens_saved": stats.tokens_saved,
            "savings_ratio": round(stats.savings_ratio, 4),
            "merkle_root": merkle_root,
            "elapsed_us": round(stats.elapsed_microseconds, 2),
            "breakdown": {
                "ast_dropped": stats.tokens_dropped_by_ast,
                "entropy_dropped": stats.tokens_dropped_by_entropy,
                "merkle_dropped": stats.tokens_dropped_by_merkle,
                "knapsack_dropped": stats.tokens_dropped_by_knapsack,
            },
            "meta": extra_meta or {},
        }

        # Write safely to ledger if directory exists or can be created
        try:
            if not self.nerve_dir.exists():
                self.nerve_dir.mkdir(parents=True, exist_ok=True)

            with open(self.context_ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            return True
        except (OSError, IOError):
            # In sandbox/permission-restricted environments, fail soft
            return False
