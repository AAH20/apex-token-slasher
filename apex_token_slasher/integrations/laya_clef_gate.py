"""Laya & Cloudflare Clef Fast-Path Gating Engine.

Executes sub-50µs non-autoregressive decision classification to route incoming prompts
to the optimal pruning strategy (Bypass, Merkle Dedup, AST Slice, or Full Slash).
Zero external dependencies.
"""

from __future__ import annotations

import time
from typing import List, Tuple

from apex_token_slasher.core.models import GatingAction, GatingVerdict


class LayaClefFastGate:
    """Sub-50µs non-autoregressive decision gate for context routing."""

    def __init__(
        self,
        bypass_token_threshold: int = 1500,
        full_slash_token_threshold: int = 8000,
        merkle_match_threshold: float = 0.40,
    ) -> None:
        self.bypass_threshold = bypass_token_threshold
        self.full_slash_threshold = full_slash_token_threshold
        self.merkle_match_threshold = merkle_match_threshold

    def evaluate(
        self,
        text: str,
        turn_number: int = 1,
        known_hashes_ratio: float = 0.0,
        target_max_tokens: Optional[int] = None,
    ) -> GatingVerdict:
        """Evaluates incoming text and returns a deterministic routing verdict in <50µs."""
        t_start = time.perf_counter_ns()
        reasons: List[str] = []

        # Fast heuristic token estimate: ~3.8 chars per token
        char_count = len(text)
        estimated_tokens = int(char_count / 3.8)

        # 1. Under-budget bypass check
        is_under_budget = (
            estimated_tokens <= target_max_tokens
            if target_max_tokens is not None
            else estimated_tokens < self.bypass_threshold
        )
        if is_under_budget:
            t_end = time.perf_counter_ns()
            elapsed_us = (t_end - t_start) / 1000.0
            threshold_label = target_max_tokens if target_max_tokens is not None else self.bypass_threshold
            return GatingVerdict(
                action=GatingAction.BYPASS,
                confidence=0.99,
                gate_latency_us=elapsed_us,
                reasons=[f"Tokens ({estimated_tokens}) under ceiling ({threshold_label})"],
                router_backend="clef_hotpath",
            )

        # 2. Multi-turn high Merkle match check
        if turn_number > 1 and known_hashes_ratio >= self.merkle_match_threshold:
            t_end = time.perf_counter_ns()
            elapsed_us = (t_end - t_start) / 1000.0
            return GatingVerdict(
                action=GatingAction.MERKLE_ONLY,
                confidence=0.95,
                gate_latency_us=elapsed_us,
                reasons=[
                    f"Turn {turn_number}: {known_hashes_ratio:.1%} known hashes match Merkle cache"
                ],
                router_backend="laya_sidecar",
            )

        # 3. Detect code dominance (presence of def, class, import, indentation)
        code_markers = ("def ", "class ", "import ", "from ", "async def ", "return ", "self.")
        marker_hits = sum(1 for m in code_markers if m in text)
        is_code_heavy = marker_hits >= 2

        # 4. Full slash vs AST slice decision
        if estimated_tokens >= self.full_slash_threshold:
            action = GatingAction.FULL_SLASH
            reasons.append(f"Tokens ({estimated_tokens}) exceed full slash limit ({self.full_slash_threshold})")
            confidence = 0.98
        elif is_code_heavy:
            action = GatingAction.AST_PRUNE
            reasons.append(f"Detected code-heavy context ({marker_hits} code markers matched)")
            confidence = 0.92
        else:
            action = GatingAction.FULL_SLASH
            reasons.append(f"General text context of {estimated_tokens} tokens")
            confidence = 0.88

        t_end = time.perf_counter_ns()
        elapsed_us = (t_end - t_start) / 1000.0

        return GatingVerdict(
            action=action,
            confidence=confidence,
            gate_latency_us=elapsed_us,
            reasons=reasons,
            router_backend="clef_hotpath",
        )
