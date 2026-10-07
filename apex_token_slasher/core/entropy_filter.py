"""Shannon Token Entropy & Propositional Information Density (PID) Filter.

Quantifies information density, filters repetitive boilerplate, collapses repeating log traces,
and strips decorative comments.
Zero external dependencies.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import List, Tuple

from apex_token_slasher.core.models import ChunkKind, TokenChunk


class EntropyFilter:
    """Calculates information metrics and prunes low-entropy or repetitive content."""

    # Regex patterns for empirical technical tokens (PID)
    EMPIRICAL_TOKEN_REGEX = re.compile(
        r"(?:[0-9]+(?:\.[0-9]+)?(?:ms|us|s|kb|mb|gb|ghz|mhz|%|px|fps)?|"  # Numbers & units
        r"0x[0-9a-fA-F]+|"                                                  # Hex addresses
        r"https?://\S+|"                                                    # URLs
        r"line\s+[0-9]+|"                                                   # Line numbers
        r"[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*|"                  # Qualified symbols
        r"(?:def|class|async|await|return|raise|yield|import)\b)"           # Code keywords
    )

    # Decorative comments to discard
    DECORATIVE_COMMENT_REGEX = re.compile(
        r"^[\s#/*=-]{5,}$|"                                                # # ---------------------
        r"^\s*#\s*(?:TODO|FIXME|NOTE|Copyright|Licensed under).*$|"        # License boilerplate
        r"^\s*<!--.*?-->\s*$"                                               # Empty HTML comments
    )

    def calculate_shannon_entropy(self, text: str) -> float:
        """Calculates Shannon entropy in bits per character."""
        if not text:
            return 0.0

        length = len(text)
        counts = Counter(text)
        entropy = 0.0
        for count in counts.values():
            prob = count / length
            entropy -= prob * math.log2(prob)
        return entropy

    def calculate_pid(self, text: str) -> float:
        """Calculates Propositional Information Density (PID).

        PID = |empirical_tokens| / |total_words|
        """
        words = text.split()
        if not words:
            return 0.0

        empirical_matches = len(self.EMPIRICAL_TOKEN_REGEX.findall(text))
        return min(1.0, empirical_matches / len(words))

    def filter_chunk(self, chunk: TokenChunk, min_entropy: float = 2.0, min_pid: float = 0.10) -> Tuple[bool, TokenChunk]:
        """Evaluates whether chunk passes information density thresholds.

        Returns (is_retained, updated_chunk).
        """
        if chunk.is_pinned or chunk.kind == ChunkKind.SYSTEM_INSTRUCTION:
            # Pinned chunks always pass
            return True, chunk

        # Compute metrics
        entropy = self.calculate_shannon_entropy(chunk.content)
        pid = self.calculate_pid(chunk.content)

        # Update chunk metadata with metrics
        updated_chunk = TokenChunk(
            chunk_id=chunk.chunk_id,
            content=chunk.content,
            kind=chunk.kind,
            file_path=chunk.file_path,
            symbol_name=chunk.symbol_name,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            estimated_tokens=chunk.estimated_tokens,
            entropy=entropy,
            pid=pid,
            merkle_hash=chunk.merkle_hash,
            dependencies=chunk.dependencies,
            is_pinned=chunk.is_pinned,
        )

        # Filter out decorative comments
        if chunk.kind == ChunkKind.COMMENT:
            comment_lines = [l.strip() for l in chunk.content.splitlines() if l.strip()]
            if comment_lines and all(self.DECORATIVE_COMMENT_REGEX.match(l) for l in comment_lines):
                return False, updated_chunk

        # Low-entropy or near-zero PID check
        if entropy < min_entropy and pid < min_pid and len(chunk.content) > 60:
            return False, updated_chunk

        return True, updated_chunk

    def condense_log_or_trace(self, text: str) -> str:
        """Deduplicates repeating log lines and collapses uninformative trace frames."""
        lines = text.splitlines()
        if not lines:
            return text

        condensed_lines: List[str] = []
        prev_line: str = ""
        repeat_count: int = 1

        for line in lines:
            stripped = line.strip()
            # Check for stack trace framework frames to shorten
            if "site-packages" in line or "/usr/lib/python" in line:
                if "line" in line:
                    continue  # Skip framework internals

            if stripped == prev_line:
                repeat_count += 1
            else:
                if repeat_count > 1:
                    condensed_lines.append(f"    ... [repeated {repeat_count} times]")
                condensed_lines.append(line)
                prev_line = stripped
                repeat_count = 1

        if repeat_count > 1:
            condensed_lines.append(f"    ... [repeated {repeat_count} times]")

        return "\n".join(condensed_lines)
