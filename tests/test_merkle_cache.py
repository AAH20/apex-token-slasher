"""Unit tests for MerkleAstCache."""

import unittest
from apex_token_slasher.core.merkle_cache import MerkleAstCache
from apex_token_slasher.core.models import ChunkKind, TokenChunk


class TestMerkleCache(unittest.TestCase):
    def setUp(self) -> None:
        self.cache = MerkleAstCache()

    def test_deterministic_hash_generation(self) -> None:
        chunk = TokenChunk(
            chunk_id="chunk:1",
            content="def calculate_checksum(): return 42",
            kind=ChunkKind.SOURCE_CODE,
            symbol_name="calculate_checksum",
        )
        h1 = self.cache.compute_chunk_hash(chunk)
        h2 = self.cache.compute_chunk_hash(chunk)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 16)

    def test_merkle_root_computation(self) -> None:
        hashes = ["a1b2c3d4e5f60718", "1234567890abcdef", "fedcba0987654321"]
        root1 = self.cache.compute_merkle_root(hashes)
        root2 = self.cache.compute_merkle_root(hashes)
        self.assertEqual(root1, root2)
        self.assertEqual(len(root1), 16)

    def test_cross_turn_deduplication(self) -> None:
        chunk = TokenChunk(
            chunk_id="c_large",
            content="class BigEngine:\n" + ("    def step(self): pass\n" * 40),
            kind=ChunkKind.SOURCE_CODE,
            file_path="engine.py",
            symbol_name="BigEngine",
        )
        # Turn 1: chunk is new
        retained_t1, dups_t1, saved_t1 = self.cache.deduplicate_chunks([chunk])
        self.assertEqual(len(retained_t1), 1)
        self.assertEqual(len(dups_t1), 0)
        self.assertEqual(saved_t1, 0)

        # Advance to Turn 2: chunk is repeated
        self.cache.advance_turn()
        retained_t2, dups_t2, saved_t2 = self.cache.deduplicate_chunks([chunk], replace_with_tombstone=True)
        self.assertEqual(len(retained_t2), 1)
        self.assertEqual(len(dups_t2), 1)
        self.assertGreater(saved_t2, 0)
        self.assertIn("MERKLE_REF", retained_t2[0].content)


if __name__ == "__main__":
    unittest.main()
