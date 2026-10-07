"""Unit tests for AstCallGraphSlicer."""

import unittest
from apex_token_slasher.core.ast_slicer import AstCallGraphSlicer


class TestAstSlicer(unittest.TestCase):
    def setUp(self) -> None:
        self.slicer = AstCallGraphSlicer(preserve_class_skeletons=True)

    def test_parses_symbols_and_imports(self) -> None:
        code = """
import os
import sys

def helper():
    return 10

def main():
    return helper() + 5
"""
        symbols = self.slicer.parse_and_index(code)
        self.assertIn("__imports__", symbols)
        self.assertIn("helper", symbols)
        self.assertIn("main", symbols)
        self.assertIn("helper", symbols["main"].dependencies)

    def test_reachability_prunes_dead_code(self) -> None:
        code = """
import math

def used_helper():
    return 42

def dead_function():
    return 999

def target_entry():
    return used_helper()
"""
        symbols = self.slicer.parse_and_index(code)
        reachable = self.slicer.slice_reachable(symbols, {"target_entry"})

        self.assertIn("target_entry", reachable)
        self.assertIn("used_helper", reachable)
        self.assertIn("__imports__", reachable)
        self.assertNotIn("dead_function", reachable)

    def test_slice_to_chunks_partitioning(self) -> None:
        code = """
class Worker:
    def active_task(self):
        return True

    def unused_routine(self):
        pass

def main():
    w = Worker()
    return w.active_task()
"""
        retained, dropped = self.slicer.slice_to_chunks(code, "worker.py", {"main"})
        retained_names = {c.symbol_name for c in retained}
        dropped_names = {c.symbol_name for c in dropped}

        self.assertIn("main", retained_names)
        self.assertIn("Worker", retained_names)
        self.assertIn("Worker.active_task", retained_names)
        self.assertIn("Worker.unused_routine", dropped_names)


if __name__ == "__main__":
    unittest.main()
