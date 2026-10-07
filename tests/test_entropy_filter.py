"""Unit tests for EntropyFilter."""

import unittest
from apex_token_slasher.core.entropy_filter import EntropyFilter
from apex_token_slasher.core.models import ChunkKind, TokenChunk


class TestEntropyFilter(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = EntropyFilter()

    def test_shannon_entropy_calculation(self) -> None:
        low_entropy = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        high_entropy = "def calculate_eigenvalues(matrix: List[List[float]]) -> float: return 42.0"
        h_low = self.filter.calculate_shannon_entropy(low_entropy)
        h_high = self.filter.calculate_shannon_entropy(high_entropy)
        self.assertLess(h_low, 1.0)
        self.assertGreater(h_high, 3.5)

    def test_pid_calculation(self) -> None:
        technical_text = "Benchmark p50 latency is 106.63us with 9378 ops/sec at line 42 in module.py"
        fluff_text = "Our platform is remarkably seamless and innovative and leverages game-changing synergies"
        pid_tech = self.filter.calculate_pid(technical_text)
        pid_fluff = self.filter.calculate_pid(fluff_text)
        self.assertGreater(pid_tech, 0.30)
        self.assertLess(pid_fluff, 0.05)

    def test_decorative_comment_filtering(self) -> None:
        banner_chunk = TokenChunk(
            chunk_id="comment:1",
            content="# --------------------------------------------------\n# Copyright 2026",
            kind=ChunkKind.COMMENT,
        )
        code_comment = TokenChunk(
            chunk_id="comment:2",
            content="# Critical: must run before mutex release at line 89",
            kind=ChunkKind.COMMENT,
        )
        passes_banner, _ = self.filter.filter_chunk(banner_chunk)
        passes_code, _ = self.filter.filter_chunk(code_comment)
        self.assertFalse(passes_banner)
        self.assertTrue(passes_code)

    def test_log_condensation(self) -> None:
        repeated_log = (
            "2026-10-07 [INFO] Worker health check passed\n"
            "2026-10-07 [INFO] Worker health check passed\n"
            "2026-10-07 [INFO] Worker health check passed\n"
            "2026-10-07 [ERROR] Connection timeout at line 10"
        )
        condensed = self.filter.condense_log_or_trace(repeated_log)
        self.assertIn("repeated 3 times", condensed)
        self.assertIn("Connection timeout", condensed)


if __name__ == "__main__":
    unittest.main()
