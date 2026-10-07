"""Hindsight Long-Term Memory Distiller.

Distills verbose conversational memory blocks from Hindsight into high-entropy,
canonical factual assertions, eliminating conversational preambles and redundant notes.
Zero external dependencies.
"""

from __future__ import annotations

import re
from typing import List

from apex_token_slasher.core.models import ChunkKind, TokenChunk


class HindsightMemoryDistiller:
    """Compresses conversational memory blocks into concise, propositionally dense memory chunks."""

    # Conversational preambles to strip
    PREAMBLE_PATTERNS = [
        re.compile(r"^In session \d+.*?the user (?:mentioned|stated|requested|preferred) that\s*", re.IGNORECASE),
        re.compile(r"^The agent observed that\s*", re.IGNORECASE),
        re.compile(r"^Remember that\s*", re.IGNORECASE),
        re.compile(r"^Note:\s*", re.IGNORECASE),
    ]

    def distill_fact(self, raw_memory: str) -> str:
        """Strips conversational boilerplate and extracts core factual assertion."""
        cleaned = raw_memory.strip()
        for pat in self.PREAMBLE_PATTERNS:
            cleaned = pat.sub("", cleaned).strip()

        if cleaned:
            # Capitalize first letter
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    def distill_to_chunk(self, memories: List[str], bank_name: str = "default") -> TokenChunk:
        """Transforms a list of Hindsight memory entries into a single compressed TokenChunk."""
        seen = set()
        distilled_facts: List[str] = []

        for m in memories:
            fact = self.distill_fact(m)
            if fact and fact not in seen:
                seen.add(fact)
                distilled_facts.append(f"• {fact}")

        header = f"# [HINDSIGHT_MEMORY_BANK: {bank_name}]"
        body = "\n".join(distilled_facts) if distilled_facts else "• (no active constraints)"
        content = f"{header}\n{body}"

        return TokenChunk(
            chunk_id=f"hindsight:{bank_name}",
            content=content,
            kind=ChunkKind.MEMORY,
            estimated_tokens=max(5, int(len(content) / 3.8)),
            is_pinned=True,  # Crucial user memories remain pinned
        )
