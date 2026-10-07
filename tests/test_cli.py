"""Unit tests for the CLI module."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestCli(unittest.TestCase):
    def test_cli_verify(self) -> None:
        cmd = [sys.executable, "-m", "apex_token_slasher.cli", "verify"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("PASSED", res.stdout)

    def test_cli_prune(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("""
def live():
    return 1

def dead_1():
    return 2

def dead_2():
    return 3
""")
            temp_path = f.name

        try:
            cmd = [
                sys.executable,
                "-m",
                "apex_token_slasher.cli",
                "prune",
                temp_path,
                "--budget",
                "50",
                "--entry",
                "live",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            self.assertIn("Tokens Slashed", res.stdout)
            self.assertIn("live", res.stdout)
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
