"""Command-line interface for Apex Token Slasher.

Provides subcommands: prune, proxy, benchmark, and verify.
Zero external dependencies.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List

from apex_token_slasher.core.models import BudgetSpec, PruningStrategy
from apex_token_slasher.pipeline import SlasherPipeline


def cmd_prune(args: argparse.Namespace) -> int:
    """Prunes a file or code snippet according to budget constraints."""
    target_path = Path(args.target)
    if not target_path.exists():
        print(f"Error: Target '{args.target}' does not exist.", file=sys.stderr)
        return 1

    content = target_path.read_text(encoding="utf-8")
    strategy = PruningStrategy(args.strategy)
    entries = set(args.entry.split(",")) if args.entry else set()

    budget = BudgetSpec(
        max_tokens=args.budget,
        strategy=strategy,
        pinned_symbols=entries,
    )

    pipeline = SlasherPipeline()
    result = pipeline.slash_context(
        raw_text=content,
        budget=budget,
        file_path=str(target_path),
        entry_points=entries,
    )

    stats = result.stats
    print("=" * 60)
    print("  Apex Token Slasher — Pruning Telemetry")
    print("=" * 60)
    print(f"  Target File:       {target_path}")
    print(f"  Initial Tokens:    {stats.initial_tokens:,}")
    print(f"  Final Tokens:      {stats.final_tokens:,}")
    print(f"  Tokens Slashed:    {stats.tokens_saved:,} ({stats.savings_ratio:.1%})")
    print(f"  Gate Decision:     {result.gating_verdict.action.value} ({result.gating_verdict.gate_latency_us:.1f}µs)")
    print(f"  Pipeline Latency:  {stats.elapsed_microseconds:.1f} µs ({stats.elapsed_microseconds / 1000.0:.2f} ms)")
    print(f"  Merkle Root Hash:  {result.merkle_root}")
    print("=" * 60)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(result.rendered_text, encoding="utf-8")
        print(f"[*] Compressed output written to {out_path}")
    else:
        print("\n--- Slashed Output Preview (first 25 lines) ---")
        preview = "\n".join(result.rendered_text.splitlines()[:25])
        print(preview)
        if len(result.rendered_text.splitlines()) > 25:
            print("... [truncated preview]")

    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Runs high-precision microsecond benchmarks across all Token Slasher subsystems."""
    from benchmarks.benchmark_telemetry import run_benchmark
    run_benchmark()
    return 0


def cmd_proxy(args: argparse.Namespace) -> int:
    """Runs the local transparent HTTP token slashing proxy."""
    from apex_token_slasher.proxy.http_proxy import run_slasher_proxy
    run_slasher_proxy(port=args.port, upstream_url=args.upstream)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Verifies pipeline integrity and mathematical properties."""
    print("[*] Running Apex Token Slasher verification suite...")
    pipeline = SlasherPipeline()

    test_code = """
def alpha():
    return beta()

def beta():
    return 42

def gamma_dead():
    return "never called"
"""
    budget = BudgetSpec(max_tokens=25, pinned_symbols={"alpha"})
    result = pipeline.slash_context(test_code, budget=budget, entry_points={"alpha"})
    assert "def alpha" in result.rendered_text, "Verification failed: alpha missing"
    assert "def beta" in result.rendered_text, "Verification failed: beta missing"
    assert "gamma_dead" not in result.rendered_text, "Verification failed: gamma_dead should be pruned"
    assert result.stats.savings_ratio > 0.15, "Verification failed: savings ratio too low"

    print("[+] All verification checks PASSED successfully.")
    return 0


def main() -> int:
    """CLI main entry point."""
    parser = argparse.ArgumentParser(
        prog="slasher",
        description="Apex Token Slasher — Deterministic Context Compression & Submodular Call-Graph Pruner",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: prune
    prune_parser = subparsers.add_parser("prune", help="Prune a file or code repository")
    prune_parser.add_argument("target", help="Path to file to prune")
    prune_parser.add_argument("--budget", type=int, default=4000, help="Max token budget ceiling (default: 4000)")
    prune_parser.add_argument(
        "--strategy",
        choices=["conservative", "balanced", "aggressive"],
        default="balanced",
        help="Pruning aggression strategy (default: balanced)",
    )
    prune_parser.add_argument("--entry", help="Comma-separated entrypoint symbols (e.g. main,process_event)")
    prune_parser.add_argument("--output", "-o", help="Output file path (default: stdout)")

    # Subcommand: benchmark
    subparsers.add_parser("benchmark", help="Run microsecond benchmark telemetry suite")

    # Subcommand: proxy
    proxy_parser = subparsers.add_parser("proxy", help="Run local transparent HTTP proxy")
    proxy_parser.add_argument("--port", type=int, default=8080, help="Proxy port (default: 8080)")
    proxy_parser.add_argument("--upstream", default="https://api.openai.com", help="Upstream API base URL")

    # Subcommand: verify
    subparsers.add_parser("verify", help="Run integrity self-tests")

    args = parser.parse_args()
    if args.subcommand == "prune":
        return cmd_prune(args)
    elif args.subcommand == "benchmark":
        return cmd_benchmark(args)
    elif args.subcommand == "proxy":
        return cmd_proxy(args)
    elif args.subcommand == "verify":
        return cmd_verify(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
