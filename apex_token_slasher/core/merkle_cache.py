"""Hierarchical Merkle AST Differential Cache.

Tracks transmitted AST nodes across multi-turn sessions, identifies identical subtrees,
and replaces repeated code blocks with cryptographic Merkle reference tokens.
Zero external dependencies.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional, Set, Tuple

from apex_token_slasher.core.models import ChunkKind, TokenChunk


class MerkleAstCache:
    """Computes Merkle tree hashes and handles cross-turn differential deduplication."""

    def __init__(self) -> None:
        # Maps merkle_hash -> (chunk_id, transmission_turn, estimated_tokens)
        self.seen_hashes: Dict[str, Tuple[str, int, int]] = {}
        self.current_turn: int = 1

    def advance_turn(self) -> None:
        """Increments the conversation turn counter."""
        self.current_turn += 1

    def compute_chunk_hash(self, chunk: TokenChunk) -> str:
        """Computes deterministic SHA-256 hash for an AST chunk."""
        h = hashlib.sha256()
        h.update(chunk.kind.value.encode("utf-8"))
        h.update(b":")
        h.update((chunk.symbol_name or "").encode("utf-8"))
        h.update(b":")
        h.update(chunk.content.strip().encode("utf-8"))
        return h.hexdigest()[:16]  # 16-char hex prefix is collision-resistant for single sessions

    def compute_merkle_root(self, chunk_hashes: List[str]) -> str:
        """Computes the root hash of a list of chunk hashes forming a Merkle tree."""
        if not chunk_hashes:
            return hashlib.sha256(b"empty").hexdigest()[:16]

        current_level = sorted(chunk_hashes)
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                h = hashlib.sha256()
                h.update(current_level[i].encode("utf-8"))
                if i + 1 < len(current_level):
                    h.update(current_level[i + 1].encode("utf-8"))
                else:
                    h.update(current_level[i].encode("utf-8"))
                next_level.append(h.hexdigest()[:16])
            current_level = next_level

        return current_level[0]

    def deduplicate_chunks(
        self,
        chunks: List[TokenChunk],
        replace_with_tombstone: bool = True,
    ) -> Tuple[List[TokenChunk], List[TokenChunk], int]:
        """Identifies chunks previously transmitted and compresses or drops them.

        Returns (retained_chunks, duplicate_chunks, tokens_saved).
        """
        retained: List[TokenChunk] = []
        duplicates: List[TokenChunk] = []
        tokens_saved = 0

        for chunk in chunks:
            chunk_hash = chunk.merkle_hash or self.compute_chunk_hash(chunk)

            # Check if seen in an earlier turn
            if chunk_hash in self.seen_hashes:
                orig_id, orig_turn, orig_tokens = self.seen_hashes[chunk_hash]

                if replace_with_tombstone and chunk.kind == ChunkKind.SOURCE_CODE:
                    # Replace large chunk with minimal Merkle tombstone
                    sym_label = f"::{chunk.symbol_name}" if chunk.symbol_name else ""
                    path_label = chunk.file_path or "unnamed"
                    tombstone_text = (
                        f"# [MERKLE_REF: {chunk_hash} | {path_label}{sym_label} "
                        f"unchanged from turn {orig_turn} ({chunk.estimated_tokens} tokens omitted)]"
                    )
                    tombstone_chunk = TokenChunk(
                        chunk_id=f"{chunk.chunk_id}:merkle_ref",
                        content=tombstone_text,
                        kind=ChunkKind.COMMENT,
                        file_path=chunk.file_path,
                        symbol_name=chunk.symbol_name,
                        estimated_tokens=max(5, int(len(tombstone_text) / 3.8)),
                        merkle_hash=chunk_hash,
                        is_pinned=chunk.is_pinned,
                    )
                    retained.append(tombstone_chunk)
                    tokens_saved += max(0, chunk.estimated_tokens - tombstone_chunk.estimated_tokens)
                    duplicates.append(chunk)
                else:
                    # Drop completely
                    tokens_saved += chunk.estimated_tokens
                    duplicates.append(chunk)
            else:
                # First time seeing this chunk in the session
                self.seen_hashes[chunk_hash] = (chunk.chunk_id, self.current_turn, chunk.estimated_tokens)
                # Assign hash if missing
                if not chunk.merkle_hash:
                    chunk = TokenChunk(
                        chunk_id=chunk.chunk_id,
                        content=chunk.content,
                        kind=chunk.kind,
                        file_path=chunk.file_path,
                        symbol_name=chunk.symbol_name,
                        line_start=chunk.line_start,
                        line_end=chunk.line_end,
                        estimated_tokens=chunk.estimated_tokens,
                        entropy=chunk.entropy,
                        pid=chunk.pid,
                        merkle_hash=chunk_hash,
                        dependencies=chunk.dependencies,
                        is_pinned=chunk.is_pinned,
                    )
                retained.append(chunk)

        return retained, duplicates, tokens_saved
