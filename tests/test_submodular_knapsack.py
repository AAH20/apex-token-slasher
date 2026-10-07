"""Unit tests for SubmodularContextKnapsack."""

import unittest
from apex_token_slasher.core.models import ChunkKind, TokenChunk
from apex_token_slasher.core.submodular_knapsack import SubmodularContextKnapsack


class TestSubmodularKnapsack(unittest.TestCase):
    def setUp(self) -> None:
        self.knapsack = SubmodularContextKnapsack()

    def test_respects_token_budget_ceiling(self) -> None:
        chunks = [
            TokenChunk(chunk_id=f"c_{i}", content=f"function body {i} " * 10, kind=ChunkKind.SOURCE_CODE)
            for i in range(10)
        ]
        # Each chunk is ~42 tokens; budget is 150 tokens
        retained, dropped = self.knapsack.solve(chunks, max_tokens=150)
        total_retained_tokens = sum(c.estimated_tokens for c in retained)

        self.assertLessEqual(total_retained_tokens, 150)
        self.assertGreater(len(retained), 0)
        self.assertGreater(len(dropped), 0)

    def test_pinned_chunk_always_selected(self) -> None:
        normal_chunk = TokenChunk(
            chunk_id="normal",
            content="regular code snippet " * 20,
            kind=ChunkKind.SOURCE_CODE,
            is_pinned=False,
        )
        pinned_chunk = TokenChunk(
            chunk_id="pinned",
            content="critical system invariant " * 20,
            kind=ChunkKind.SYSTEM_INSTRUCTION,
            is_pinned=True,
        )
        # Very tight budget fitting only 1 chunk
        retained, dropped = self.knapsack.solve([normal_chunk, pinned_chunk], max_tokens=70)
        retained_ids = [c.chunk_id for c in retained]

        self.assertIn("pinned", retained_ids)

    def test_redundancy_penalty_prioritizes_diverse_chunks(self) -> None:
        duplicate_a = TokenChunk(
            chunk_id="dup_a",
            content="def helper_alpha(): return 100",
            kind=ChunkKind.SOURCE_CODE,
        )
        duplicate_b = TokenChunk(
            chunk_id="dup_b",
            content="def helper_alpha(): return 100",
            kind=ChunkKind.SOURCE_CODE,
        )
        diverse_c = TokenChunk(
            chunk_id="diverse_c",
            content="class DatabaseConnectionPool: pass",
            kind=ChunkKind.SOURCE_CODE,
        )
        retained, dropped = self.knapsack.solve([duplicate_a, duplicate_b, diverse_c], max_tokens=25)
        retained_ids = [c.chunk_id for c in retained]

        # Should retain diverse_c and one of the duplicates, not both duplicates
        self.assertIn("diverse_c", retained_ids)


if __name__ == "__main__":
    unittest.main()
