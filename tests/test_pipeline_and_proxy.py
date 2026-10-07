"""Unit tests for SlasherPipeline and TokenSlasherInterceptor."""

import json
import unittest
from apex_token_slasher.core.models import BudgetSpec, PruningStrategy
from apex_token_slasher.pipeline import SlasherPipeline
from apex_token_slasher.proxy.interceptor import TokenSlasherInterceptor


class TestPipelineAndProxy(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = SlasherPipeline(enable_nerve=False)
        self.interceptor = TokenSlasherInterceptor(pipeline=self.pipeline)

    def test_end_to_end_slashing_pipeline(self) -> None:
        source_code = """
import os
import sys

def target_function():
    return active_helper()

def active_helper():
    return 100

def unused_unreached_routine():
    # -----------------------------
    # Dead boilerplate code
    # -----------------------------
    return "dead" * 200
""" * 10

        budget = BudgetSpec(
            max_tokens=300,
            strategy=PruningStrategy.BALANCED,
            pinned_symbols={"target_function"},
        )
        result = self.pipeline.slash_context(
            raw_text=source_code,
            budget=budget,
            entry_points={"target_function"},
        )

        self.assertLessEqual(result.stats.final_tokens, 300)
        self.assertGreater(result.stats.savings_ratio, 0.20)
        self.assertIn("target_function", result.rendered_text)
        self.assertIn("active_helper", result.rendered_text)
        self.assertNotIn("unused_unreached_routine", result.rendered_text)

    def test_interceptor_compresses_openai_payload(self) -> None:
        large_code = "def entrypoint(): return 42\n" + ("def dead_code(): pass\n" * 200)
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a code reviewer."},
                {"role": "user", "content": large_code},
            ],
            "temperature": 0.2,
        }
        raw_bytes = json.dumps(payload).encode("utf-8")
        budget = BudgetSpec(max_tokens=500, pinned_symbols={"entrypoint"})

        compressed_bytes, slashed = self.interceptor.process_openai_payload(raw_bytes, budget=budget)
        compressed_data = json.loads(compressed_bytes.decode("utf-8"))

        compressed_user_msg = compressed_data["messages"][1]["content"]
        self.assertLess(len(compressed_user_msg), len(large_code))
        self.assertIn("entrypoint", compressed_user_msg)
        self.assertGreater(slashed.stats.savings_ratio, 0.30)


if __name__ == "__main__":
    unittest.main()
